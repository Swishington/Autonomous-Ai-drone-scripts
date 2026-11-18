"""Kart Rush - a top-down kart racer built for console-style controllers.

Run:  python kart_racer.py
See README.md in this folder for the full control layout.
"""

import json
import math
import os
import random

import pygame

from characters import load_roster
from input_manager import InputManager

SCREEN_W, SCREEN_H = 1280, 720
FPS = 60
BIG_LAPS = 3
LITTLE_LAPS = 2
TRACK_WIDTH = 180
CURB_WIDTH = 12
WORLD_W, WORLD_H = 3200, 2300
SAVE_FILE = os.path.join(os.path.expanduser("~"), ".kart_rush_best.json")

# Hand-placed control points of the circuit (smoothed with a Catmull-Rom spline).
TRACK_POINTS = [
    (420, 1500), (400, 900), (520, 480), (900, 330), (1250, 450), (1420, 800),
    (1750, 950), (2050, 650), (2300, 380), (2750, 420), (2930, 800), (2850, 1250),
    (2500, 1400), (2350, 1700), (2700, 1900), (2550, 2120), (1900, 2080),
    (1500, 1750), (1150, 1950), (700, 2050), (450, 1850),
]
BOOST_PAD_FRACTIONS = [0.12, 0.47, 0.83]

# Physics tuning
MAX_SPEED = 540.0
ACCEL = 430.0
BRAKE = 800.0
REVERSE_MAX = 170.0
TURN_RATE = 2.7
DRIFT_TURN_RATE = 3.5
GRIP = 11.0
DRIFT_GRIP = 2.4
GRASS_SPEED_FACTOR = 0.45
BOOST_SPEED_FACTOR = 1.35
KART_RADIUS = 22

# Little Racer (toddler mode) tuning
LITTLE_PLAYER_SKILL = 0.78      # top speed vs. Big Racer
LITTLE_ASSIST = 0.55            # how much the game steers for her
LITTLE_INPUT = 0.9              # how much her stick counts
WALL_BOUNCE = 0.7               # how bouncy the walls are
WRONG_WAY_SECONDS = 2.0         # going the wrong way this long -> kart turns itself around
AUTO_TURN_RATE = 3.0            # rad/s while turning around
SPARKLE_COOLDOWN = 1.2


def catmull_rom_loop(points, samples_per_segment=24):
    out = []
    n = len(points)
    for i in range(n):
        p0, p1, p2, p3 = points[i - 1], points[i], points[(i + 1) % n], points[(i + 2) % n]
        for s in range(samples_per_segment):
            t = s / samples_per_segment
            t2, t3 = t * t, t * t * t
            x = 0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    return out


def resample_loop(points, spacing=12.0):
    """Evenly space points along the closed loop so index == distance travelled."""
    out = [points[0]]
    carry = 0.0
    n = len(points)
    for i in range(n):
        ax, ay = points[i]
        bx, by = points[(i + 1) % n]
        seg = math.hypot(bx - ax, by - ay)
        d = spacing - carry
        while d <= seg:
            t = d / seg
            out.append((ax + (bx - ax) * t, ay + (by - ay) * t))
            d += spacing
        carry = seg - (d - spacing)
    return out[:-1]


def angle_diff(a, b):
    return (a - b + math.pi) % (2 * math.pi) - math.pi


def clamp(v, lo=-1.0, hi=1.0):
    return max(lo, min(hi, v))


def draw_star(surf, color, cx, cy, r):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    pygame.draw.polygon(surf, color, pts)


class Track:
    def __init__(self):
        self.center = resample_loop(catmull_rom_loop(TRACK_POINTS))
        self.n = len(self.center)
        self.tangents = []
        for i in range(self.n):
            ax, ay = self.center[i - 1]
            bx, by = self.center[(i + 1) % self.n]
            self.tangents.append(math.atan2(by - ay, bx - ax))
        self.boost_pads = [int(f * self.n) for f in BOOST_PAD_FRACTIONS]
        rng = random.Random(7)
        self.obstacles = []
        kinds = ["tree", "tree", "lollipop", "gumdrop", "mushroom"]
        while len(self.obstacles) < 100:
            x, y = rng.uniform(60, WORLD_W - 60), rng.uniform(60, WORLD_H - 60)
            if self.distance_to_center(x, y)[0] > TRACK_WIDTH / 2 + 75:
                self.obstacles.append((x, y, rng.randint(22, 38), rng.choice(kinds)))
        self.surface = self._render(rng)
        self.minimap = self._render_minimap()

    def point(self, i):
        return self.center[i % self.n]

    def normal(self, i):
        a = self.tangents[i % self.n]
        return math.cos(a + math.pi / 2), math.sin(a + math.pi / 2)

    def distance_to_center(self, x, y, hint=None, window=40):
        """Distance to the centreline and nearest index (searching near `hint` if given)."""
        indices = range(self.n) if hint is None else (i % self.n for i in range(hint - window, hint + window))
        best_d, best_i = float("inf"), 0
        for i in indices:
            cx, cy = self.center[i]
            d = (cx - x) ** 2 + (cy - y) ** 2
            if d < best_d:
                best_d, best_i = d, i
        return math.sqrt(best_d), best_i

    def _render(self, rng):
        surf = pygame.Surface((WORLD_W, WORLD_H))
        surf.fill((90, 175, 75))
        for _ in range(5000):
            shade = rng.choice([(80, 162, 68), (100, 186, 84), (86, 168, 72)])
            pygame.draw.circle(surf, shade, (rng.randrange(WORLD_W), rng.randrange(WORLD_H)), rng.randint(2, 6))
        for _ in range(700):  # little flowers
            x, y = rng.randrange(WORLD_W), rng.randrange(WORLD_H)
            c = rng.choice([(255, 255, 255), (255, 170, 210), (255, 230, 90), (190, 160, 255)])
            for k in range(5):
                a = k * 2 * math.pi / 5
                pygame.draw.circle(surf, c, (x + math.cos(a) * 3, y + math.sin(a) * 3), 2)
            pygame.draw.circle(surf, (255, 200, 40), (x, y), 2)
        half = TRACK_WIDTH // 2
        for i, (x, y) in enumerate(self.center):
            color = (255, 90, 150) if (i // 4) % 2 == 0 else (250, 250, 250)
            pygame.draw.circle(surf, color, (int(x), int(y)), half + CURB_WIDTH)
        for x, y in self.center:
            pygame.draw.circle(surf, (95, 95, 108), (int(x), int(y)), half)
        for i in range(0, self.n, 6):  # dashed centre line
            if (i // 6) % 2 == 0:
                a, b = self.center[i], self.center[(i + 3) % self.n]
                pygame.draw.line(surf, (215, 215, 215), a, b, 3)
        self._draw_start_line(surf)
        for idx in self.boost_pads:
            self._draw_boost_pad(surf, idx)
        for ob in self.obstacles:
            self._draw_obstacle(surf, *ob)
        return surf

    @staticmethod
    def _draw_obstacle(surf, x, y, r, kind):
        x, y = int(x), int(y)
        pygame.draw.circle(surf, (50, 110, 45), (x + 6, y + 6), r)  # shadow
        if kind == "tree":
            pygame.draw.circle(surf, (30, 120, 45), (x, y), r)
            pygame.draw.circle(surf, (60, 155, 65), (x - r // 4, y - r // 4), r // 2)
        elif kind == "lollipop":
            colors = [(255, 90, 140), (255, 255, 255), (120, 200, 255), (255, 255, 255)]
            for i in range(8):
                a0 = i * math.pi / 4
                pts = [(x, y)] + [(x + math.cos(a0 + t * math.pi / 16) * r, y + math.sin(a0 + t * math.pi / 16) * r)
                                  for t in range(5)]
                pygame.draw.polygon(surf, colors[i % 4], pts)
            pygame.draw.circle(surf, (230, 70, 120), (x, y), r, 3)
        elif kind == "gumdrop":
            c = random.Random(x * 31 + y).choice([(255, 80, 120), (120, 220, 120), (255, 200, 60), (160, 120, 255)])
            pygame.draw.circle(surf, c, (x, y), r)
            pygame.draw.circle(surf, tuple(min(255, v + 60) for v in c), (x - r // 3, y - r // 3), r // 3)
            rng = random.Random(x + y * 7)
            for _ in range(8):
                pygame.draw.circle(surf, (255, 255, 255), (x + rng.randint(-r // 2, r // 2), y + rng.randint(-r // 2, r // 2)), 2)
        else:  # mushroom
            pygame.draw.circle(surf, (225, 40, 50), (x, y), r)
            for dx, dy, sr in ((-r // 3, -r // 3, r // 4), (r // 3, -r // 5, r // 5), (0, r // 3, r // 4), (-r // 2, r // 4, r // 6)):
                pygame.draw.circle(surf, (255, 255, 255), (x + dx, y + dy), sr)

    def _draw_start_line(self, surf):
        x, y = self.center[0]
        nx, ny = self.normal(0)
        a = self.tangents[0]
        tx, ty = math.cos(a), math.sin(a)
        cells, size = 12, TRACK_WIDTH / 12
        for row in range(2):
            for c in range(cells):
                off = -TRACK_WIDTH / 2 + (c + 0.5) * size
                cx, cy = x + nx * off + tx * (row - 0.5) * size, y + ny * off + ty * (row - 0.5) * size
                color = (20, 20, 20) if (c + row) % 2 else (250, 250, 250)
                rect = pygame.Rect(0, 0, size + 1, size + 1)
                rect.center = (cx, cy)
                pygame.draw.rect(surf, color, rect)

    def _draw_boost_pad(self, surf, idx):
        x, y = self.center[idx]
        a = self.tangents[idx]
        tx, ty = math.cos(a), math.sin(a)
        nx, ny = self.normal(idx)
        for k in range(3):
            base = (x + tx * (k * 22 - 22), y + ty * (k * 22 - 22))
            tip = (base[0] + tx * 20, base[1] + ty * 20)
            left = (base[0] + nx * 30, base[1] + ny * 30)
            right = (base[0] - nx * 30, base[1] - ny * 30)
            pygame.draw.polygon(surf, (255, 210, 0), [left, tip, right])
            pygame.draw.polygon(surf, (255, 140, 0), [left, tip, right], 3)

    def _render_minimap(self):
        scale = 220 / WORLD_W
        self.minimap_scale = scale
        mm = pygame.Surface((int(WORLD_W * scale), int(WORLD_H * scale)), pygame.SRCALPHA)
        mm.fill((0, 0, 0, 120))
        pts = [(x * scale, y * scale) for x, y in self.center]
        pygame.draw.lines(mm, (230, 230, 230), True, pts, 5)
        return mm


class Kart:
    def __init__(self, character, x, y, heading, is_player=False, skill=1.0, lane=0.0):
        self.character = character
        self.name = character.name
        self.color = character.body
        self.x, self.y = x, y
        self.heading = heading
        self.vx = self.vy = 0.0
        self.is_player = is_player
        self.skill = skill
        self.lane = lane
        self.idx = 0
        self.laps = -1          # crossing the start line the first time starts lap 1
        self.passed_half = True
        self.finished_time = None
        self.on_grass = False
        self.drifting = False
        self.drift_charge = 0.0
        self.boost_timer = 0.0
        self.last_pad = None
        self.lap_start = 0.0
        self.lap_times = []
        # Little Racer helpers
        self.wrong_way_timer = 0.0
        self.auto_turning = False
        self.sparkle_cooldown = 0.0

    @property
    def forward_speed(self):
        return self.vx * math.cos(self.heading) + self.vy * math.sin(self.heading)

    def progress(self, n):
        return self.laps * n + self.idx

    def update(self, dt, steer, throttle, brake, drift, track, walls=False):
        """Advance physics. Returns True if the kart bounced off a wall."""
        fx, fy = math.cos(self.heading), math.sin(self.heading)
        rx, ry = -fy, fx
        fwd = self.vx * fx + self.vy * fy
        lat = self.vx * rx + self.vy * ry

        top = MAX_SPEED * self.skill
        if self.boost_timer > 0:
            top *= BOOST_SPEED_FACTOR
            self.boost_timer -= dt
            throttle = 1.0
        if self.on_grass:
            top *= GRASS_SPEED_FACTOR

        if throttle > 0:
            fwd += ACCEL * throttle * (1.6 if self.boost_timer > 0 else 1.0) * dt
        if brake > 0:
            fwd -= (BRAKE if fwd > 0 else ACCEL * 0.6) * brake * dt
        if throttle == 0 and brake == 0:
            fwd *= math.exp(-0.9 * dt)
        if fwd > top:
            fwd = max(top, fwd - 900 * dt)
        fwd = max(-REVERSE_MAX, fwd)

        self.drifting = drift and fwd > 220 and abs(steer) > 0.3 and not self.on_grass
        if self.drifting:
            self.drift_charge += dt
        else:
            if self.drift_charge > 0.7:
                self.boost_timer = max(self.boost_timer, 0.5 + min(self.drift_charge, 2.0) * 0.4)
            self.drift_charge = 0.0

        turn = DRIFT_TURN_RATE if self.drifting else TURN_RATE
        grip_factor = min(1.0, abs(fwd) / 160.0) * (1 if fwd >= 0 else -1)
        self.heading += steer * turn * grip_factor * dt
        lat *= math.exp(-(DRIFT_GRIP if self.drifting else GRIP) * dt)

        fx, fy = math.cos(self.heading), math.sin(self.heading)
        rx, ry = -fy, fx
        self.vx = fx * fwd + rx * lat
        self.vy = fy * fwd + ry * lat
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.x = max(KART_RADIUS, min(WORLD_W - KART_RADIUS, self.x))
        self.y = max(KART_RADIUS, min(WORLD_H - KART_RADIUS, self.y))

        dist, self.idx = track.distance_to_center(self.x, self.y, self.idx)
        bounced = False
        limit = TRACK_WIDTH / 2 + CURB_WIDTH - KART_RADIUS * 0.5
        if walls and dist > limit:
            cx, cy = track.point(self.idx)
            nx, ny = (self.x - cx) / dist, (self.y - cy) / dist
            self.x, self.y = cx + nx * limit, cy + ny * limit
            vn = self.vx * nx + self.vy * ny
            if vn > 0:
                self.vx -= (1 + WALL_BOUNCE) * vn * nx
                self.vy -= (1 + WALL_BOUNCE) * vn * ny
                bounced = vn > 40
            # Nudge the nose back along the road so she isn't stuck against the wall.
            self.heading += angle_diff(track.tangents[self.idx], self.heading) * 0.25
        self.on_grass = (not walls) and dist > TRACK_WIDTH / 2 + CURB_WIDTH

        # Boost pads
        pad_hit = None
        for p in track.boost_pads:
            px, py = track.point(p)
            if (px - self.x) ** 2 + (py - self.y) ** 2 < 55 ** 2:
                pad_hit = p
        if pad_hit is not None and pad_hit != self.last_pad:
            self.boost_timer = max(self.boost_timer, 1.1)
        self.last_pad = pad_hit
        return bounced

    def update_lap(self, prev_idx, n, race_time):
        """Returns True if a lap was just completed."""
        if n * 0.4 < self.idx < n * 0.6:
            self.passed_half = True
        if prev_idx > n * 0.9 and self.idx < n * 0.1 and self.passed_half:
            self.passed_half = False
            self.laps += 1
            if self.laps > 0:
                self.lap_times.append(race_time - self.lap_start)
            self.lap_start = race_time
            return True
        return False

    def draw(self, screen, cam_x, cam_y, t):
        ch = self.character
        cx, cy = self.x - cam_x, self.y - cam_y
        shadow = pygame.Surface((52, 52), pygame.SRCALPHA)
        pygame.draw.circle(shadow, (0, 0, 0, 70), (26, 26), 25)
        screen.blit(shadow, (cx - 22, cy - 20))
        if self.boost_timer > 0:
            bx, by = cx - math.cos(self.heading) * 32, cy - math.sin(self.heading) * 32
            pygame.draw.circle(screen, ch.trail[0], (bx, by), random.randint(7, 11))
            pygame.draw.circle(screen, (255, 255, 230), (bx, by), 4)
        img = pygame.transform.rotate(ch.kart, -math.degrees(self.heading))
        screen.blit(img, img.get_rect(center=(cx, cy)))
        if ch.style == "rider":
            bob = math.sin(t * 9 + self.x * 0.01) * 2 * min(1.0, abs(self.forward_speed) / 200)
            screen.blit(ch.avatar_race, ch.avatar_race.get_rect(center=(cx, cy - 16 + bob)))


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "size", "star")

    def __init__(self, x, y, vx, vy, life, color, size, star=False):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.color, self.size, self.star = color, size, star


def ordinal(n):
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


def fmt_time(t):
    if t is None:
        return "--:--.--"
    return f"{int(t // 60):02d}:{t % 60:05.2f}"


class Game:
    def __init__(self, headless=False):
        pygame.init()
        flags = 0 if headless else pygame.SCALED | pygame.RESIZABLE
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), flags)
        pygame.display.set_caption("Kart Rush")
        self.clock = pygame.time.Clock()
        self.font_huge = pygame.font.Font(None, 130)
        self.font_big = pygame.font.Font(None, 100)
        self.font_med = pygame.font.Font(None, 48)
        self.font = pygame.font.Font(None, 32)
        self.font_small = pygame.font.Font(None, 24)
        self.input = InputManager()
        self.track = Track()
        self.roster = load_roster()
        self.best_lap = self._load_best()
        self.little = True          # Little Racer (toddler) mode
        self.mode_index = 0         # title menu selection
        self.char_index = 0         # character select selection
        self.state = "title"
        self.running = True
        self.time = 0.0
        self.particles = []
        self.new_race()

    @property
    def laps(self):
        return LITTLE_LAPS if self.little else BIG_LAPS

    def _load_best(self):
        try:
            with open(SAVE_FILE) as f:
                return json.load(f).get("best_lap")
        except (OSError, ValueError):
            return None

    def _save_best(self):
        try:
            with open(SAVE_FILE, "w") as f:
                json.dump({"best_lap": self.best_lap}, f)
        except OSError:
            pass

    def new_race(self):
        t = self.track
        player_char = self.roster[self.char_index]
        rivals = random.sample([c for c in self.roster if c is not player_char], 3)
        if self.little:
            skills = [0.72, 0.68, 0.64]
        else:
            skills = [0.97, 0.93, 0.89]
        self.karts = []
        # 2x2 starting grid just behind the start line; player starts at the back.
        grid = [(-16, 48), (-16, -48), (-8, 48), (-8, -48)]
        entries = [(rivals[0], skills[0], False), (rivals[1], skills[1], False),
                   (rivals[2], skills[2], False), (player_char, LITTLE_PLAYER_SKILL if self.little else 1.0, True)]
        for (idx, off), (ch, skill, is_player) in zip(grid, entries):
            px, py = t.point(idx)
            nx, ny = t.normal(idx)
            kart = Kart(ch, px + nx * off, py + ny * off, t.tangents[idx % t.n],
                        is_player=is_player, skill=skill, lane=random.uniform(-40, 40))
            kart.idx = idx % t.n
            self.karts.append(kart)
        self.player = next(k for k in self.karts if k.is_player)
        self.base_skills = {k: k.skill for k in self.karts}
        self.race_time = 0.0
        self.countdown = 3.5
        self.finish_order = []
        self.message = ""
        self.message_timer = 0.0
        self.particles = []

    # --- AI -----------------------------------------------------------------
    def ai_drive(self, kart, lane=None):
        """Steer/throttle/brake that follows the racing line."""
        t = self.track
        speed = max(kart.forward_speed, 0)
        look = 8 + int(speed / 45)
        lane = kart.lane if lane is None else lane
        tx, ty = t.point(kart.idx + look)
        nx, ny = t.normal(kart.idx + look)
        tx, ty = tx + nx * lane, ty + ny * lane
        desired = math.atan2(ty - kart.y, tx - kart.x)
        steer = clamp(angle_diff(desired, kart.heading) * 2.2)
        # Look further ahead to slow down for sharp corners
        curve = abs(angle_diff(t.tangents[(kart.idx + look * 2) % t.n], t.tangents[kart.idx]))
        throttle, brake = 1.0, 0.0
        if curve > 1.1 and speed > 380:
            throttle, brake = 0.0, 0.5
        elif curve > 0.7 and speed > 450:
            throttle = 0.3
        return steer, throttle, brake

    def rubber_band(self, kart):
        """Rivals speed up a little when behind the player and ease off when ahead."""
        n = self.track.n
        gap = self.player.progress(n) - kart.progress(n)
        base = self.base_skills[kart]
        # Little Racer rivals barely speed up, so she gets to win often.
        catch_up = 0.03 if self.little else 0.08
        kart.skill = clamp(base + 0.0003 * clamp(gap, -300, 300), base - 0.1, base + catch_up)

    # --- Little Racer helpers ---------------------------------------------------------
    def little_controls(self, kart, inp, dt):
        """Toddler mode: auto-go, steering help, turn-around and sparkle boost."""
        tangent = self.track.tangents[kart.idx]
        off = angle_diff(tangent, kart.heading)
        slow = abs(kart.forward_speed) < 60
        if abs(off) > 1.8 or (slow and abs(off) > 0.9):
            kart.wrong_way_timer += dt
        else:
            kart.wrong_way_timer = max(0.0, kart.wrong_way_timer - dt * 2)
        if kart.wrong_way_timer > WRONG_WAY_SECONDS and not kart.auto_turning:
            kart.auto_turning = True
            self.flash("Turning around!", 1.5)
            self.input.rumble(0.2, 0.4, 150)

        if kart.auto_turning:
            kart.heading += clamp(off, -AUTO_TURN_RATE * dt, AUTO_TURN_RATE * dt)
            if abs(off) < 0.25:
                kart.auto_turning = False
                kart.wrong_way_timer = 0.0
            steer = 0.0
        else:
            assist, _, _ = self.ai_drive(kart, lane=0.0)
            steer = clamp(assist * LITTLE_ASSIST + inp.steer * LITTLE_INPUT)

        kart.sparkle_cooldown -= dt
        if "boost" in inp.pressed and kart.sparkle_cooldown <= 0:
            kart.sparkle_cooldown = SPARKLE_COOLDOWN
            kart.boost_timer = max(kart.boost_timer, 0.9)
            self.burst(kart.x, kart.y, kart.character.trail, 26, star=True)
            self.input.rumble(0.4, 0.8, 180)
        # The kart always keeps moving; the gas just makes it a bit faster. No brakes.
        throttle = max(0.75, inp.throttle)
        return steer, throttle, 0.0, False

    # --- particles ----------------------------------------------------------------
    def burst(self, x, y, colors, count, star=False, speed=220):
        for _ in range(count):
            a = random.uniform(0, 2 * math.pi)
            v = random.uniform(speed * 0.3, speed)
            self.particles.append(Particle(x, y, math.cos(a) * v, math.sin(a) * v, random.uniform(0.5, 1.0),
                                           random.choice(colors), random.uniform(4, 9), star))

    def emit_trails(self, dt):
        for k in self.karts:
            if k.boost_timer > 0 or k.drifting:
                if random.random() < 0.7:
                    bx = k.x - math.cos(k.heading) * 28 + random.uniform(-6, 6)
                    by = k.y - math.sin(k.heading) * 28 + random.uniform(-6, 6)
                    color = k.character.trail[int(self.time * 12) % len(k.character.trail)]
                    if k.drifting and k.boost_timer <= 0:
                        color = (80, 180, 255) if k.drift_charge < 0.7 else (255, 140, 40)
                    self.particles.append(Particle(bx, by, random.uniform(-30, 30), random.uniform(-30, 30),
                                                   0.6, color, random.uniform(4, 8), star=k.boost_timer > 0))
        for p in self.particles:
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vx *= 0.94
            p.vy *= 0.94
            p.life -= dt
        self.particles = [p for p in self.particles if p.life > 0]

    def draw_particles(self, cam_x, cam_y, screen_space=False):
        for p in self.particles:
            x, y = (p.x, p.y) if screen_space else (p.x - cam_x, p.y - cam_y)
            size = p.size * (0.4 + 0.6 * p.life / p.max_life)
            if p.star:
                draw_star(self.screen, p.color, x, y, size * 1.4)
            else:
                pygame.draw.circle(self.screen, p.color, (x, y), size)

    # --- simulation -----------------------------------------------------------
    def collide_karts(self):
        for i, a in enumerate(self.karts):
            for b in self.karts[i + 1:]:
                dx, dy = b.x - a.x, b.y - a.y
                d = math.hypot(dx, dy)
                if 0 < d < KART_RADIUS * 2:
                    push = (KART_RADIUS * 2 - d) / 2
                    ux, uy = dx / d, dy / d
                    a.x -= ux * push; a.y -= uy * push
                    b.x += ux * push; b.y += uy * push
                    rel = (b.vx - a.vx) * ux + (b.vy - a.vy) * uy
                    if rel < 0:
                        a.vx += ux * rel * 0.8; a.vy += uy * rel * 0.8
                        b.vx -= ux * rel * 0.8; b.vy -= uy * rel * 0.8
                        if a.is_player or b.is_player:
                            self.input.rumble(0.6, 0.3, 120)

    def collide_obstacles(self, kart):
        for tx, ty, r, _ in self.track.obstacles:
            dx, dy = kart.x - tx, kart.y - ty
            d = math.hypot(dx, dy)
            if 0 < d < r + KART_RADIUS:
                ux, uy = dx / d, dy / d
                kart.x, kart.y = tx + ux * (r + KART_RADIUS), ty + uy * (r + KART_RADIUS)
                vn = kart.vx * ux + kart.vy * uy
                if vn < 0:
                    kart.vx -= 1.5 * vn * ux; kart.vy -= 1.5 * vn * uy
                    kart.vx *= 0.5; kart.vy *= 0.5
                    if kart.is_player:
                        self.input.rumble(1.0, 0.8, 250)

    def flash(self, text, seconds=1.5):
        self.message, self.message_timer = text, seconds

    def update_race(self, dt, inp):
        self.emit_trails(dt)
        if self.countdown > 0:
            prev = self.countdown
            self.countdown -= dt
            if math.ceil(prev) != math.ceil(self.countdown) and self.countdown > 0:
                self.input.rumble(0.2, 0.2, 80)
            if self.countdown <= 0:
                self.input.rumble(0.5, 0.5, 200)
                self.flash("GO!", 1.0)
            return
        self.race_time += dt
        for kart in self.karts:
            prev_idx = kart.idx
            if kart.finished_time is not None:  # cruise after the finish line
                steer, throttle, brake = self.ai_drive(kart)
                throttle, drift = throttle * 0.5, False
            elif kart.is_player and self.little:
                steer, throttle, brake, drift = self.little_controls(kart, inp, dt)
            elif kart.is_player:
                steer, throttle, brake, drift = inp.steer, inp.throttle, inp.brake, inp.drift
            else:
                self.rubber_band(kart)
                steer, throttle, brake = self.ai_drive(kart)
                drift = False
            boost_before = kart.boost_timer
            bounced = kart.update(dt, steer, throttle, brake, drift, self.track, walls=self.little)
            if kart.is_player:
                if kart.boost_timer > boost_before + 0.2:
                    self.input.rumble(0.3, 0.9, 200)
                if bounced:
                    self.input.rumble(0.5, 0.2, 120)
                    self.burst(kart.x, kart.y, [(255, 255, 255), (255, 230, 120)], 8, star=True, speed=120)
            self.collide_obstacles(kart)
            if kart.update_lap(prev_idx, self.track.n, self.race_time) and kart.finished_time is None:
                self.on_lap(kart)
        self.collide_karts()
        self.message_timer -= dt

    def on_lap(self, kart):
        if kart.is_player and kart.lap_times:
            lap = kart.lap_times[-1]
            if not self.little and (self.best_lap is None or lap < self.best_lap):
                self.best_lap = lap
                self._save_best()
                self.flash(f"NEW BEST LAP  {fmt_time(lap)}", 2.0)
            elif kart.laps < self.laps:
                self.flash("Yay! One more lap!" if self.little else f"Lap {kart.laps}  {fmt_time(lap)}", 1.8)
            if not self.little and kart.laps == self.laps - 1:
                self.flash("FINAL LAP!", 1.8)
        if kart.laps >= self.laps:
            kart.finished_time = self.race_time
            self.finish_order.append(kart)
            if kart.is_player:
                self.state = "finished"
                self.input.rumble(0.7, 0.7, 500)
                if self.little:
                    confetti = [(255, 110, 170), (255, 200, 80), (120, 210, 255), (180, 130, 255), (140, 230, 120)]
                    for _ in range(4):
                        self.burst(kart.x + random.uniform(-200, 200), kart.y + random.uniform(-150, 150),
                                   confetti, 30, star=True, speed=300)

    def standings(self):
        n = self.track.n
        finished = list(self.finish_order)
        rest = sorted((k for k in self.karts if k not in finished), key=lambda k: k.progress(n), reverse=True)
        return finished + rest

    # --- drawing ----------------------------------------------------------------
    def camera(self):
        p = self.player
        lead = 0.25
        cx = p.x + p.vx * lead - SCREEN_W / 2
        cy = p.y + p.vy * lead - SCREEN_H / 2
        return max(0, min(WORLD_W - SCREEN_W, cx)), max(0, min(WORLD_H - SCREEN_H, cy))

    def text(self, font, s, pos, color=(255, 255, 255), anchor="topleft", shadow=True):
        if shadow:
            img = font.render(s, True, (0, 0, 0))
            self.screen.blit(img, img.get_rect(**{anchor: (pos[0] + 2, pos[1] + 2)}))
        img = font.render(s, True, color)
        r = img.get_rect(**{anchor: pos})
        self.screen.blit(img, r)
        return r

    def draw_world(self):
        cam_x, cam_y = self.camera()
        self.screen.blit(self.track.surface, (0, 0), pygame.Rect(cam_x, cam_y, SCREEN_W, SCREEN_H))
        self.draw_particles(cam_x, cam_y)
        for k in sorted(self.karts, key=lambda k: (k.is_player, k.y)):
            k.draw(self.screen, cam_x, cam_y, self.time)

    def draw_hud(self):
        p = self.player
        place = self.standings().index(p) + 1
        lap = min(self.laps, max(1, p.laps + 1))
        if self.little:
            panel = pygame.Surface((330, 120), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 110))
            self.screen.blit(panel, (16, 16))
            self.screen.blit(pygame.transform.smoothscale(p.character.avatar_full, (96, 96)), (26, 28))
            self.text(self.font_med, ordinal(place), (135, 30), (255, 220, 60))
            self.text(self.font_med, f"Lap {lap}/{self.laps}", (135, 76))
            if p.sparkle_cooldown <= 0 and self.state == "race":
                self.text(self.font, "Press a button for sparkles!", (SCREEN_W / 2, SCREEN_H - 40), (255, 230, 255), anchor="center")
        else:
            panel = pygame.Surface((300, 150), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 120))
            self.screen.blit(panel, (16, 16))
            self.text(self.font_med, ordinal(place), (30, 26), (255, 220, 60))
            self.text(self.font_small, f"of {len(self.karts)}", (30 + self.font_med.size(ordinal(place))[0] + 8, 44))
            self.text(self.font, f"Lap {lap}/{self.laps}", (170, 30))
            self.text(self.font, f"Time  {fmt_time(self.race_time)}", (30, 80))
            cur = self.race_time - p.lap_start if p.laps >= 0 else 0.0
            self.text(self.font_small, f"Lap   {fmt_time(cur)}", (30, 112))
            self.text(self.font_small, f"Best  {fmt_time(self.best_lap)}", (30, 136))

            speed = abs(p.forward_speed)
            frac = min(1.0, speed / (MAX_SPEED * BOOST_SPEED_FACTOR))
            bar = pygame.Rect(SCREEN_W - 296, SCREEN_H - 60, 260, 22)
            pygame.draw.rect(self.screen, (0, 0, 0), bar.inflate(6, 6), border_radius=6)
            fill = bar.copy()
            fill.width = int(bar.width * frac)
            pygame.draw.rect(self.screen, (255, 170, 40) if p.boost_timer > 0 else (80, 200, 255), fill, border_radius=4)
            self.text(self.font, f"{int(speed / 5)} km/h", (bar.right, bar.top - 8), anchor="bottomright")
            if p.drifting:
                ready = p.drift_charge >= 0.7
                self.text(self.font, "DRIFT BOOST READY" if ready else "DRIFT!", (bar.left, bar.top - 8),
                          (255, 140, 40) if ready else (80, 180, 255), anchor="bottomleft")
            tangent = self.track.tangents[p.idx]
            if self.countdown <= 0 and abs(angle_diff(p.heading, tangent)) > 2.2 and speed > 60:
                self.text(self.font_med, "WRONG WAY!", (SCREEN_W / 2, 140), (255, 80, 80), anchor="center")
            elif p.on_grass and speed > 50:
                self.text(self.font, "Off track - get back on the road!", (SCREEN_W / 2, 140), (255, 230, 150), anchor="center")
            self.text(self.font_small, self.input.device_name, (16, SCREEN_H - 30), (220, 220, 220))

        mm = self.track.minimap
        mx, my = SCREEN_W - mm.get_width() - 16, 16
        self.screen.blit(mm, (mx, my))
        s = self.track.minimap_scale
        for k in self.karts:
            pygame.draw.circle(self.screen, (0, 0, 0), (mx + k.x * s, my + k.y * s), 7 if k.is_player else 5)
            pygame.draw.circle(self.screen, k.color, (mx + k.x * s, my + k.y * s), 6 if k.is_player else 4)

        if self.countdown > 0:
            n = math.ceil(self.countdown)
            label = str(n) if n <= 3 else "Ready?"
            self.text(self.font_huge, label, (SCREEN_W / 2, SCREEN_H / 2 - 90), (255, 230, 60), anchor="center")
        elif self.message_timer > 0:
            self.text(self.font_med, self.message, (SCREEN_W / 2, SCREEN_H / 2 - 130), (255, 255, 255), anchor="center")

    def overlay(self, alpha=160):
        s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        s.fill((20, 0, 40, alpha))
        self.screen.blit(s, (0, 0))

    def draw_title(self):
        self.overlay(140)
        cx = SCREEN_W / 2
        self.text(self.font_huge, "KART RUSH", (cx, 90), (255, 210, 60), anchor="center")
        options = [
            ("Little Racer", "Goes by itself - just steer! Bouncy walls and sparkles",
             [self.roster[0], self.roster[2]], (255, 140, 200)),
            ("Big Racer", "Full control: gas, brake and drift boosts. Beat everyone!",
             [self.roster[7], self.roster[9]], (110, 180, 255)),
        ]
        for i, (title, desc, icons, color) in enumerate(options):
            selected = i == self.mode_index
            rect = pygame.Rect(0, 0, 820, 130)
            rect.center = (cx, 230 + i * 160)
            if selected:
                rect.inflate_ip(24 + math.sin(self.time * 6) * 6, 12)
            box = pygame.Surface(rect.size, pygame.SRCALPHA)
            box.fill((*color, 230 if selected else 120))
            self.screen.blit(box, rect)
            pygame.draw.rect(self.screen, (255, 255, 255) if selected else (0, 0, 0), rect, 5 if selected else 2, border_radius=8)
            for k, ch in enumerate(icons):
                self.screen.blit(pygame.transform.smoothscale(ch.avatar_full, (100, 100)), (rect.left + 15 + k * 80, rect.top + 15))
            self.text(self.font_big if selected else self.font_med, title, (rect.left + 200, rect.top + 18))
            self.text(self.font, desc, (rect.left + 200, rect.bottom - 40), (255, 255, 255))
        self.text(self.font, "Up / Down to choose   ·   A / Cross or Enter to pick", (cx, 560), anchor="center")
        self.text(self.font_small, "Big Racer: steer = left stick · gas = RT/A · brake = LT/B · drift = RB/X · pause = Start",
                  (cx, 610), (230, 230, 230), anchor="center")
        self.text(self.font_small, f"Input: {self.input.device_name}   ·   F11 fullscreen", (cx, SCREEN_H - 40),
                  (200, 200, 200), anchor="center")

    def draw_select(self):
        self.overlay(170)
        cx = SCREEN_W / 2
        self.text(self.font_big, "Choose your racer!", (cx, 70), (255, 230, 90), anchor="center")
        cols, card_w, card_h, gap = 5, 210, 230, 20
        left = cx - (cols * card_w + (cols - 1) * gap) / 2
        for i, ch in enumerate(self.roster):
            col, row = i % cols, i // cols
            rect = pygame.Rect(left + col * (card_w + gap), 130 + row * (card_h + gap), card_w, card_h)
            selected = i == self.char_index
            box = pygame.Surface(rect.size, pygame.SRCALPHA)
            box.fill((*ch.body, 235 if selected else 110))
            self.screen.blit(box, rect)
            pygame.draw.rect(self.screen, (255, 255, 255) if selected else (30, 30, 30), rect, 6 if selected else 2, border_radius=10)
            size = 170 if selected else 140
            bob = math.sin(self.time * 7) * 6 if selected else 0
            img = pygame.transform.smoothscale(ch.avatar_full, (size, size))
            self.screen.blit(img, img.get_rect(center=(rect.centerx, rect.top + 95 + bob)))
            self.text(self.font_med if selected else self.font, ch.name, (rect.centerx, rect.bottom - 26), anchor="center")
        mode = "Little Racer" if self.little else "Big Racer"
        self.text(self.font, f"{mode}  ·  Stick / D-pad to choose  ·  A / Enter to race  ·  B / Backspace back",
                  (cx, SCREEN_H - 40), anchor="center")

    def draw_pause(self):
        self.overlay()
        cx, cy = SCREEN_W / 2, SCREEN_H / 2
        self.text(self.font_big, "PAUSED", (cx, cy - 100), anchor="center")
        self.text(self.font, "A / Enter  -  keep racing", (cx, cy), anchor="center")
        self.text(self.font, "Y / R  -  restart race", (cx, cy + 40), anchor="center")
        self.text(self.font, "B / Backspace  -  back to title", (cx, cy + 80), anchor="center")

    def draw_results(self):
        self.overlay(130)
        cx = SCREEN_W / 2
        place = self.finish_order.index(self.player) + 1
        if self.little:
            title = "Hooray! You did it!"
            sub = "You won!" if place == 1 else f"You came {ordinal(place)}!"
            for k in range(5):
                draw_star(self.screen, (255, 220, 60), cx - 200 + k * 100, 175 + math.sin(self.time * 5 + k) * 8, 34)
        else:
            title = "YOU WIN!" if place == 1 else f"You finished {ordinal(place)}"
            sub = None
        self.text(self.font_big, title, (cx, 90), (255, 210, 60), anchor="center")
        if sub:
            self.text(self.font_med, sub, (cx, 240), anchor="center")
        y = 300 if self.little else 210
        for i, k in enumerate(self.standings()):
            color = (255, 255, 120) if k.is_player else (255, 255, 255)
            self.text(self.font_med, ordinal(i + 1), (cx - 280, y), color, anchor="midleft")
            self.screen.blit(pygame.transform.smoothscale(k.character.avatar_full, (52, 52)), (cx - 200, y - 26))
            self.text(self.font_med, k.name, (cx - 130, y), color, anchor="midleft")
            if not self.little:
                self.text(self.font_med, fmt_time(k.finished_time) if k.finished_time else "racing...",
                          (cx + 280, y), color, anchor="midright")
            y += 58
        if not self.little:
            laps = "   ".join(fmt_time(t) for t in self.player.lap_times)
            self.text(self.font, f"Your laps:  {laps}", (cx, y + 15), anchor="center")
            self.text(self.font, f"Best lap ever:  {fmt_time(self.best_lap)}", (cx, y + 52), anchor="center")
        self.text(self.font_med, "A / Enter  race again    ·    B  menu", (cx, SCREEN_H - 60), anchor="center")
        self.draw_particles(*self.camera())  # confetti on top of the results

    # --- main loop ----------------------------------------------------------------
    def step(self, dt):
        self.time += dt
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                pygame.display.toggle_fullscreen()
            self.input.handle_event(event)
        inp = self.input.poll()
        pressed = inp.pressed

        if self.state == "title":
            if pressed & {"up", "down", "left", "right"}:
                self.mode_index = 1 - self.mode_index
            elif "confirm" in pressed:
                self.little = self.mode_index == 0
                self.state = "select"
        elif self.state == "select":
            cols = 5
            if "left" in pressed:
                self.char_index = (self.char_index - 1) % len(self.roster)
            elif "right" in pressed:
                self.char_index = (self.char_index + 1) % len(self.roster)
            elif "up" in pressed or "down" in pressed:
                self.char_index = (self.char_index + cols) % len(self.roster)
            elif "confirm" in pressed:
                self.new_race()
                self.state = "race"
            elif "back" in pressed:
                self.state = "title"
        elif self.state == "race":
            if "pause" in pressed:
                self.state = "paused"
            else:
                self.update_race(dt, inp)
        elif self.state == "paused":
            if "confirm" in pressed or "pause" in pressed:
                self.state = "race"
            elif "restart" in pressed:
                self.new_race()
                self.state = "race"
            elif "back" in pressed:
                self.state = "title"
        elif self.state == "finished":
            self.update_race(dt, inp)  # let the rivals cross the line in the background
            if "confirm" in pressed or "restart" in pressed:
                self.new_race()
                self.state = "race"
            elif "back" in pressed:
                self.state = "select"

        self.draw_world()
        if self.state == "title":
            self.draw_title()
        elif self.state == "select":
            self.draw_select()
        else:
            self.draw_hud()
            if self.state == "paused":
                self.draw_pause()
            elif self.state == "finished":
                self.draw_results()

    def run(self):
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 1 / 30)
            self.step(dt)
            pygame.display.flip()
        pygame.quit()


if __name__ == "__main__":
    Game().run()
