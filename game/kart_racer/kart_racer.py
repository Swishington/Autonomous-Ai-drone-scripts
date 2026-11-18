"""Kart Rush - a top-down kart racer built for console-style controllers.

Run:  python kart_racer.py
See README.md in this folder for the full control layout.
"""

import argparse
import json
import math
import os
import random

import pygame

from characters import load_roster
from input_manager import EMPTY_FRAME, InputManager

SCREEN_W, SCREEN_H = 1280, 720
FPS = 60
MAX_HUMANS = 4
MAX_RACERS = 8
DIFFICULTIES = ["Easy", "Medium", "Hard"]
AI_SKILL = [0.70, 0.88, 1.00]       # rival top speed for each difficulty
AI_CATCH_UP = [0.03, 0.05, 0.08]    # how much rivals speed up when behind
PLAYER_COLORS = [(255, 80, 80), (70, 150, 255), (80, 210, 90), (255, 200, 40)]
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
FINISH_GRACE_SECONDS = 45     # race ends this long after the first human finishes


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
        self.minimap, self.minimap_scale = self._render_minimap(220)
        self.minimap_big, self.minimap_big_scale = self._render_minimap(560)

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

    def _render_minimap(self, width):
        scale = width / WORLD_W
        mm = pygame.Surface((int(WORLD_W * scale), int(WORLD_H * scale)), pygame.SRCALPHA)
        mm.fill((0, 0, 0, 120))
        pts = [(x * scale, y * scale) for x, y in self.center]
        pygame.draw.lines(mm, (230, 230, 230), True, pts, max(4, int(width / 45)))
        return mm, scale


class Player:
    """A human in the lobby: which device they use, who they picked, which mode."""

    def __init__(self, slot, device, char_index):
        self.slot = slot
        self.device = device
        self.char_index = char_index
        self.little = False
        self.ready = False

    @property
    def color(self):
        return PLAYER_COLORS[self.slot]

    @property
    def label(self):
        return f"P{self.slot + 1}"


class Kart:
    def __init__(self, character, x, y, heading, player=None, skill=1.0, lane=0.0):
        self.character = character
        self.name = character.name
        self.color = character.body
        self.player = player
        self.little = bool(player and player.little)
        self.x, self.y = x, y
        self.heading = heading
        self.vx = self.vy = 0.0
        self.skill = skill
        self.base_skill = skill
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
        self.message = ""
        self.message_timer = 0.0
        # Little Racer helpers
        self.wrong_way_timer = 0.0
        self.auto_turning = False
        self.sparkle_cooldown = 0.0
        self.last_rumble = -1.0
        self.img = character.kart
        self.tag = None
        if player is not None:
            font = pygame.font.Font(None, 24)
            text = font.render(player.label, True, (255, 255, 255))
            self.tag = pygame.Surface((text.get_width() + 10, text.get_height() + 4), pygame.SRCALPHA)
            pygame.draw.rect(self.tag, player.color, self.tag.get_rect(), border_radius=6)
            pygame.draw.rect(self.tag, (0, 0, 0), self.tag.get_rect(), 2, border_radius=6)
            self.tag.blit(text, (5, 3))

    @property
    def is_human(self):
        return self.player is not None

    @property
    def forward_speed(self):
        return self.vx * math.cos(self.heading) + self.vy * math.sin(self.heading)

    def progress(self, n):
        return self.laps * n + self.idx

    def say(self, text, seconds=1.5):
        self.message, self.message_timer = text, seconds

    def update(self, dt, steer, throttle, brake, drift, track):
        """Advance physics. Returns True if the kart bounced off a wall."""
        walls = self.little
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
        self.message_timer -= dt
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

    def prepare_sprite(self):
        """Rotate once per frame; every split-screen view reuses the result."""
        self.img = pygame.transform.rotate(self.character.kart, -math.degrees(self.heading))

    def draw(self, surf, cam_x, cam_y, t, show_tag):
        ch = self.character
        cx, cy = self.x - cam_x, self.y - cam_y
        if not (-80 < cx < surf.get_width() + 80 and -80 < cy < surf.get_height() + 80):
            return
        shadow = pygame.Surface((52, 52), pygame.SRCALPHA)
        pygame.draw.circle(shadow, (0, 0, 0, 70), (26, 26), 25)
        surf.blit(shadow, (cx - 22, cy - 20))
        if self.boost_timer > 0:
            bx, by = cx - math.cos(self.heading) * 32, cy - math.sin(self.heading) * 32
            pygame.draw.circle(surf, ch.trail[0], (bx, by), random.randint(7, 11))
            pygame.draw.circle(surf, (255, 255, 230), (bx, by), 4)
        surf.blit(self.img, self.img.get_rect(center=(cx, cy)))
        top = cy - 18
        if ch.style == "rider":
            bob = math.sin(t * 9 + self.x * 0.01) * 2 * min(1.0, abs(self.forward_speed) / 200)
            surf.blit(ch.avatar_race, ch.avatar_race.get_rect(center=(cx, cy - 16 + bob)))
            top = cy - 44
        if show_tag and self.tag is not None:
            surf.blit(self.tag, self.tag.get_rect(midbottom=(cx, top)))


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


def view_rects(n):
    """Split-screen layout: 1 = full screen, 2 = side by side, 3-4 = quarters."""
    w, h, g = SCREEN_W, SCREEN_H, 4
    if n <= 1:
        return [pygame.Rect(0, 0, w, h)]
    if n == 2:
        hw = w // 2 - g // 2
        return [pygame.Rect(0, 0, hw, h), pygame.Rect(w - hw, 0, hw, h)]
    hw, hh = w // 2 - g // 2, h // 2 - g // 2
    quads = [pygame.Rect(0, 0, hw, hh), pygame.Rect(w - hw, 0, hw, hh),
             pygame.Rect(0, h - hh, hw, hh), pygame.Rect(w - hw, h - hh, hw, hh)]
    return quads[:n]


class Game:
    def __init__(self, headless=False, fullscreen=False):
        pygame.init()
        flags = 0 if headless else pygame.SCALED | (pygame.FULLSCREEN if fullscreen else pygame.RESIZABLE)
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), flags)
        pygame.mouse.set_visible(headless or not fullscreen)
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
        self.players = []
        self.ai_count = 3
        self.ai_difficulty = 1
        self.laps = 3
        self.settings_row = 0
        self.settings_touched = False
        self.state = "lobby"
        self.running = True
        self.time = 0.0
        self.particles = []
        self.banner = ""
        self.banner_timer = 0.0
        self.results_since = 0.0
        self.new_race(preview=True)

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

    # --- race setup -----------------------------------------------------------
    def new_race(self, preview=False):
        """Build the grid: humans at the front, then AI racers using unpicked characters."""
        t = self.track
        humans = [] if preview else list(self.players)
        ai_count = 3 if preview else self.ai_count
        taken = {p.char_index for p in humans}
        free = [c for i, c in enumerate(self.roster) if i not in taken]
        ai_chars = random.sample(free, min(ai_count, len(free)))
        entries = [(self.roster[p.char_index], p) for p in humans] + [(c, None) for c in ai_chars]

        self.karts = []
        for i, (ch, player) in enumerate(entries):
            idx = -8 - 8 * (i // 2)
            off = 48 if i % 2 == 0 else -48
            px, py = t.point(idx)
            nx, ny = t.normal(idx)
            if player is not None:
                skill = LITTLE_PLAYER_SKILL if player.little else 1.0
            else:
                ai_i = i - len(humans)
                skill = AI_SKILL[self.ai_difficulty] - 0.025 * (ai_i % 4) + random.uniform(-0.01, 0.01)
            kart = Kart(ch, px + nx * off, py + ny * off, t.tangents[idx % t.n],
                        player=player, skill=skill, lane=random.uniform(-40, 40))
            kart.idx = idx % t.n
            self.karts.append(kart)
        self.humans = [k for k in self.karts if k.is_human]
        self.race_time = 0.0
        self.countdown = 3.5
        self.finish_order = []
        self.banner_timer = 0.0
        self.particles = []
        self.standings_cache = list(self.karts)

    def rumble(self, kart, low, high, ms):
        # At most one rumble per player every quarter second, so bumping along a wall isn't a constant buzz.
        if kart.is_human and self.time - kart.last_rumble > 0.25:
            kart.last_rumble = self.time
            self.input.rumble(kart.player.device, low, high, ms)

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
        """Rivals speed up a little when behind the humans and ease off when ahead."""
        if not self.humans:
            return
        n = self.track.n
        target = sum(h.progress(n) for h in self.humans) / len(self.humans)
        gap = target - kart.progress(n)
        base = kart.base_skill
        kart.skill = clamp(base + 0.0003 * clamp(gap, -300, 300), base - 0.1, base + AI_CATCH_UP[self.ai_difficulty])

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
            kart.say("Turning around!", 1.5)
            self.rumble(kart, 0.2, 0.4, 150)

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
            self.rumble(kart, 0.4, 0.8, 180)
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

    def draw_particles(self, surf, cam_x, cam_y):
        w, h = surf.get_size()
        for p in self.particles:
            x, y = p.x - cam_x, p.y - cam_y
            if not (-20 < x < w + 20 and -20 < y < h + 20):
                continue
            size = p.size * (0.4 + 0.6 * p.life / p.max_life)
            if p.star:
                draw_star(surf, p.color, x, y, size * 1.4)
            else:
                pygame.draw.circle(surf, p.color, (x, y), size)

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
                        self.rumble(a, 0.6, 0.3, 120)
                        self.rumble(b, 0.6, 0.3, 120)

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
                    self.rumble(kart, 1.0, 0.8, 250)

    def update_race(self, dt, frames):
        self.emit_trails(dt)
        self.banner_timer -= dt
        if self.countdown > 0:
            prev = self.countdown
            self.countdown -= dt
            for h in self.humans:
                if math.ceil(prev) != math.ceil(self.countdown) and self.countdown > 0:
                    self.rumble(h, 0.2, 0.2, 80)
                if self.countdown <= 0:
                    self.rumble(h, 0.5, 0.5, 200)
            if self.countdown <= 0:
                self.banner, self.banner_timer = "GO!", 1.0
            return
        self.race_time += dt
        for kart in self.karts:
            prev_idx = kart.idx
            inp = frames.get(kart.player.device, EMPTY_FRAME) if kart.is_human else EMPTY_FRAME
            if kart.finished_time is not None:  # cruise after the finish line
                steer, throttle, brake = self.ai_drive(kart)
                throttle, drift = throttle * 0.5, False
            elif kart.is_human and kart.little:
                steer, throttle, brake, drift = self.little_controls(kart, inp, dt)
            elif kart.is_human:
                steer, throttle, brake, drift = inp.steer, inp.throttle, inp.brake, inp.drift
            else:
                self.rubber_band(kart)
                steer, throttle, brake = self.ai_drive(kart)
                drift = False
            boost_before = kart.boost_timer
            bounced = kart.update(dt, steer, throttle, brake, drift, self.track)
            if kart.is_human:
                if kart.boost_timer > boost_before + 0.2:
                    self.rumble(kart, 0.3, 0.9, 200)
                if bounced:
                    self.rumble(kart, 0.5, 0.2, 120)
                    self.burst(kart.x, kart.y, [(255, 255, 255), (255, 230, 120)], 8, star=True, speed=120)
            self.collide_obstacles(kart)
            if kart.update_lap(prev_idx, self.track.n, self.race_time) and kart.finished_time is None:
                self.on_lap(kart)
        self.collide_karts()
        self.standings_cache = self.standings()
        done = [h.finished_time for h in self.humans if h.finished_time is not None]
        all_done = len(done) == len(self.humans)
        if self.state == "race" and self.humans and (all_done or (done and self.race_time - min(done) > FINISH_GRACE_SECONDS)):
            self.state = "results"
            self.results_since = self.time

    def on_lap(self, kart):
        if kart.is_human and kart.lap_times:
            lap = kart.lap_times[-1]
            if not kart.little and (self.best_lap is None or lap < self.best_lap):
                self.best_lap = lap
                self._save_best()
                kart.say(f"NEW BEST LAP  {fmt_time(lap)}", 2.0)
            elif kart.laps < self.laps:
                kart.say("Yay! Keep going!" if kart.little else f"Lap {kart.laps}  {fmt_time(lap)}", 1.8)
            if not kart.little and kart.laps == self.laps - 1:
                kart.say("FINAL LAP!", 1.8)
        if kart.laps >= self.laps:
            kart.finished_time = self.race_time
            self.finish_order.append(kart)
            if kart.is_human:
                self.rumble(kart, 0.7, 0.7, 500)
                confetti = [(255, 110, 170), (255, 200, 80), (120, 210, 255), (180, 130, 255), (140, 230, 120)]
                for _ in range(3):
                    self.burst(kart.x + random.uniform(-150, 150), kart.y + random.uniform(-100, 100),
                               confetti, 25, star=True, speed=300)

    def standings(self):
        n = self.track.n
        finished = list(self.finish_order)
        rest = sorted((k for k in self.karts if k not in finished), key=lambda k: k.progress(n), reverse=True)
        return finished + rest

    # --- drawing helpers --------------------------------------------------------------
    @staticmethod
    def text(surf, font, s, pos, color=(255, 255, 255), anchor="topleft", shadow=True):
        if shadow:
            img = font.render(s, True, (0, 0, 0))
            surf.blit(img, img.get_rect(**{anchor: (pos[0] + 2, pos[1] + 2)}))
        img = font.render(s, True, color)
        r = img.get_rect(**{anchor: pos})
        surf.blit(img, r)
        return r

    def overlay(self, surf, alpha=160):
        s = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        s.fill((20, 0, 40, alpha))
        surf.blit(s, (0, 0))

    @staticmethod
    def camera(kart, w, h):
        cx = kart.x + kart.vx * 0.25 - w / 2
        cy = kart.y + kart.vy * 0.25 - h / 2
        return max(0, min(WORLD_W - w, cx)), max(0, min(WORLD_H - h, cy))

    def draw_world(self, surf, focus):
        w, h = surf.get_size()
        cam_x, cam_y = self.camera(focus, w, h)
        surf.blit(self.track.surface, (0, 0), pygame.Rect(cam_x, cam_y, w, h))
        self.draw_particles(surf, cam_x, cam_y)
        show_tags = len(self.humans) > 1
        for k in sorted(self.karts, key=lambda k: (k is focus, k.y)):
            k.draw(surf, cam_x, cam_y, self.time, show_tags)
        return cam_x, cam_y

    def draw_minimap(self, surf, pos, big=False):
        mm = self.track.minimap_big if big else self.track.minimap
        s = self.track.minimap_big_scale if big else self.track.minimap_scale
        surf.blit(mm, pos)
        mx, my = pos
        for k in self.karts:
            r = (9 if big else 6) if k.is_human else (6 if big else 4)
            pygame.draw.circle(surf, (0, 0, 0), (mx + k.x * s, my + k.y * s), r + 1)
            pygame.draw.circle(surf, k.player.color if k.is_human else k.color, (mx + k.x * s, my + k.y * s), r)

    # --- per-player view ------------------------------------------------------------
    def draw_view(self, surf, kart, right_side=False):
        """One player's camera + HUD. Views on the right half mirror the HUD so the centre stays clear."""
        self.draw_world(surf, kart)
        w, h = surf.get_size()
        compact = h < 500
        big, med, norm, small = ((self.font_med, self.font, self.font_small, self.font_small) if compact
                                 else (self.font_big, self.font_med, self.font, self.font_small))
        place = self.standings_cache.index(kart) + 1
        lap = min(self.laps, max(1, kart.laps + 1))
        multi = len(self.humans) > 1

        # Top-left panel
        avatar = 56 if compact else 90
        panel = pygame.Surface((avatar + (150 if compact else 250), avatar + 16), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 120))
        if multi:
            pygame.draw.rect(panel, kart.player.color, panel.get_rect(), 4)
        px = w - panel.get_width() - 8 if right_side else 8
        surf.blit(panel, (px, 8))
        surf.blit(pygame.transform.smoothscale(kart.character.avatar_full, (avatar, avatar)), (px + 8, 16))
        tx = px + 16 + avatar
        label = f"{kart.player.label}  {ordinal(place)}" if multi else ordinal(place)
        self.text(surf, med, label, (tx, 14), (255, 220, 60))
        self.text(surf, norm, f"Lap {lap}/{self.laps}", (tx, 14 + med.get_height()))
        if not kart.little and not compact:
            self.text(surf, small, f"Time {fmt_time(self.race_time)}   Best {fmt_time(self.best_lap)}", (tx, 14 + med.get_height() + 28))

        speed = abs(kart.forward_speed)
        if not kart.little:
            bw = 160 if compact else 240
            bar_x = w - bw - 20 if (right_side or not multi) else 20
            bar = pygame.Rect(bar_x, h - 34, bw, 16 if compact else 20)
            pygame.draw.rect(surf, (0, 0, 0), bar.inflate(6, 6), border_radius=6)
            fill = bar.copy()
            fill.width = int(bar.width * min(1.0, speed / (MAX_SPEED * BOOST_SPEED_FACTOR)))
            pygame.draw.rect(surf, (255, 170, 40) if kart.boost_timer > 0 else (80, 200, 255), fill, border_radius=4)
            self.text(surf, small, f"{int(speed / 5)} km/h", (bar.left, bar.top - 4), anchor="bottomleft")
            if kart.drifting:
                ready = kart.drift_charge >= 0.7
                self.text(surf, norm, "BOOST READY" if ready else "DRIFT!", (bar.right, bar.top - 4),
                          (255, 140, 40) if ready else (80, 180, 255), anchor="bottomright")
        elif kart.sparkle_cooldown <= 0 and kart.finished_time is None and self.countdown <= 0:
            self.text(surf, small, "Press a button for sparkles!", (w / 2, h - 22), (255, 230, 255), anchor="center")

        msg_y = h * 0.3
        if kart.finished_time is not None:
            self.text(surf, big, f"Finished {ordinal(self.finish_order.index(kart) + 1)}!", (w / 2, h / 2 - 30),
                      (255, 220, 60), anchor="center")
            if any(hk.finished_time is None for hk in self.humans):
                self.text(surf, norm, "Waiting for the others...", (w / 2, h / 2 + 20), anchor="center")
        elif kart.message_timer > 0:
            self.text(surf, med, kart.message, (w / 2, msg_y), anchor="center")
        elif self.finish_order and any(h.finished_time is not None for h in self.humans):
            first = min(h.finished_time for h in self.humans if h.finished_time is not None)
            left = FINISH_GRACE_SECONDS - (self.race_time - first)
            if left < 15:
                self.text(surf, med, f"Hurry! {int(left) + 1}", (w / 2, msg_y), (255, 200, 80), anchor="center")
        elif not kart.little and self.countdown <= 0:
            if abs(angle_diff(kart.heading, self.track.tangents[kart.idx])) > 2.2 and speed > 60:
                self.text(surf, med, "WRONG WAY!", (w / 2, msg_y), (255, 80, 80), anchor="center")
            elif kart.on_grass and speed > 50:
                self.text(surf, norm, "Off track!", (w / 2, msg_y), (255, 230, 150), anchor="center")

        if not self.input.is_connected(kart.player.device):
            self.text(surf, norm, "Controller unplugged - plug one in!", (w / 2, h - 60), (255, 120, 120), anchor="center")
        if not multi:
            self.draw_minimap(surf, (w - self.track.minimap.get_width() - 12, 12))
            self.text(surf, small, self.input.device_name(kart.player.device), (12, h - 26), (220, 220, 220))

    def draw_standings_panel(self, surf):
        """Fills the spare quarter in 3-player split-screen."""
        surf.fill((35, 25, 60))
        w, h = surf.get_size()
        mm = self.track.minimap_big
        scale = min((w * 0.55) / mm.get_width(), (h - 20) / mm.get_height())
        small = pygame.transform.smoothscale(mm, (int(mm.get_width() * scale), int(mm.get_height() * scale)))
        surf.blit(small, (w - small.get_width() - 10, (h - small.get_height()) // 2))
        s = self.track.minimap_big_scale * scale
        ox, oy = w - small.get_width() - 10, (h - small.get_height()) // 2
        for k in self.karts:
            col = k.player.color if k.is_human else k.color
            pygame.draw.circle(surf, (0, 0, 0), (ox + k.x * s, oy + k.y * s), 7)
            pygame.draw.circle(surf, col, (ox + k.x * s, oy + k.y * s), 6)
        y = 14
        for i, k in enumerate(self.standings_cache):
            surf.blit(pygame.transform.smoothscale(k.character.avatar_full, (34, 34)), (50, y))
            self.text(surf, self.font_small, ordinal(i + 1), (12, y + 9))
            name = f"{k.player.label} {k.name}" if k.is_human else k.name
            self.text(surf, self.font_small, name, (90, y + 9), k.player.color if k.is_human else (255, 255, 255))
            y += 40

    def draw_race(self):
        views = view_rects(len(self.humans))
        self.screen.fill((10, 10, 20))
        for k in self.karts:
            k.prepare_sprite()
        for rect, kart in zip(views, self.humans):
            self.draw_view(self.screen.subsurface(rect), kart, right_side=rect.left > 0)
        n = len(self.humans)
        if n == 3:
            hw, hh = views[0].size
            self.draw_standings_panel(self.screen.subsurface(pygame.Rect(SCREEN_W - hw, SCREEN_H - hh, hw, hh)))
        elif n in (2, 4):
            mm = self.track.minimap
            y = SCREEN_H - mm.get_height() - 8 if n == 2 else SCREEN_H // 2 - mm.get_height() // 2
            pos = (SCREEN_W // 2 - mm.get_width() // 2, y)
            self.draw_minimap(self.screen, pos)
        if self.countdown > 0:
            c = math.ceil(self.countdown)
            self.text(self.screen, self.font_huge, str(c) if c <= 3 else "Ready?", (SCREEN_W / 2, SCREEN_H / 2),
                      (255, 230, 60), anchor="center")
        elif self.banner_timer > 0:
            self.text(self.screen, self.font_huge, self.banner, (SCREEN_W / 2, SCREEN_H / 2), (255, 255, 255), anchor="center")

    # --- menus ------------------------------------------------------------------
    def draw_menu_background(self):
        k = self.karts[0]
        self.screen.blit(self.track.surface, (0, 0), pygame.Rect(*self.camera(k, SCREEN_W, SCREEN_H), SCREEN_W, SCREEN_H))

    def draw_lobby(self):
        self.draw_menu_background()
        self.overlay(self.screen, 170)
        S = self.screen
        cx = SCREEN_W / 2
        self.text(S, self.font_big, "KART RUSH", (cx, 52), (255, 210, 60), anchor="center")
        self.text(S, self.font, "Up to 4 players: press A on your controller (or Enter / Space on the keyboard) to join!",
                  (cx, 110), anchor="center")
        pw, ph, gap = 290, 500, 20
        left = cx - (4 * pw + 3 * gap) / 2
        for slot in range(MAX_HUMANS):
            rect = pygame.Rect(left + slot * (pw + gap), 145, pw, ph)
            player = next((p for p in self.players if p.slot == slot), None)
            box = pygame.Surface(rect.size, pygame.SRCALPHA)
            if player is None:
                box.fill((255, 255, 255, 30))
                S.blit(box, rect)
                pygame.draw.rect(S, (200, 200, 200), rect, 2, border_radius=12)
                self.text(S, self.font_med, f"P{slot + 1}", (rect.centerx, rect.top + 50), PLAYER_COLORS[slot], anchor="center")
                if (pygame.time.get_ticks() // 600) % 2 == 0 or slot != len(self.players):
                    self.text(S, self.font, "Press A to join", (rect.centerx, rect.centery), anchor="center")
                continue
            ch = self.roster[player.char_index]
            box.fill((*ch.body, 200))
            S.blit(box, rect)
            pygame.draw.rect(S, player.color, rect, 6, border_radius=12)
            self.text(S, self.font_med, player.label, (rect.left + 16, rect.top + 12), player.color)
            self.text(S, self.font_small, self.input.device_name(player.device)[:30], (rect.left + 16, rect.top + 52),
                      (240, 240, 240))
            bob = 0 if player.ready else math.sin(self.time * 6 + slot) * 6
            img = pygame.transform.smoothscale(ch.avatar_full, (180, 180))
            S.blit(img, img.get_rect(center=(rect.centerx, rect.top + 160 + bob)))
            self.text(S, self.font_med, ch.name, (rect.centerx, rect.top + 275), anchor="center")
            if not player.ready:
                for sx in (-1, 1):  # < > arrows
                    ax = rect.centerx + sx * 125
                    pygame.draw.polygon(S, (255, 255, 255), [(ax, rect.top + 145), (ax, rect.top + 175), (ax + sx * 16, rect.top + 160)])
            mode_rect = pygame.Rect(0, 0, pw - 40, 64)
            mode_rect.center = (rect.centerx, rect.top + 345)
            pygame.draw.rect(S, (255, 120, 190) if player.little else (80, 140, 240), mode_rect, border_radius=10)
            pygame.draw.rect(S, (255, 255, 255), mode_rect, 2, border_radius=10)
            self.text(S, self.font, "Little Racer" if player.little else "Big Racer", (mode_rect.centerx, mode_rect.top + 20), anchor="center")
            self.text(S, self.font_small, "easy - kart helps steer" if player.little else "full control + drifting",
                      (mode_rect.centerx, mode_rect.top + 46), (240, 240, 240), anchor="center")
            if player.ready:
                self.text(S, self.font_med, "READY!", (rect.centerx, rect.bottom - 70), (120, 255, 120), anchor="center")
                self.text(S, self.font_small, "B to change", (rect.centerx, rect.bottom - 32), anchor="center")
            else:
                self.text(S, self.font_small, "Left/Right: racer   Up/Down: mode", (rect.centerx, rect.bottom - 82), anchor="center")
                self.text(S, self.font_small, "A: ready   B: leave", (rect.centerx, rect.bottom - 56), anchor="center")
        if self.players and all(p.ready for p in self.players):
            self.text(S, self.font_med, "Everyone ready! Press A for race settings", (cx, SCREEN_H - 40), (120, 255, 120), anchor="center")
        else:
            self.text(S, self.font_small, "Keyboard players: Arrows + Enter (Backspace = back) or WASD + Space (Q = back)  ·  Esc pause  ·  F11 fullscreen",
                      (cx, SCREEN_H - 36), (210, 210, 210), anchor="center")

    def settings_rows(self):
        max_ai = MAX_RACERS - len(self.players)
        return [
            ("Computer racers", f"{self.ai_count}", f"0 - {max_ai}"),
            ("Computer difficulty", DIFFICULTIES[self.ai_difficulty], "Easy / Medium / Hard"),
            ("Laps", f"{self.laps}", "1 - 5"),
        ]

    def draw_settings(self):
        self.draw_menu_background()
        self.overlay(self.screen, 180)
        S = self.screen
        cx = SCREEN_W / 2
        self.text(S, self.font_big, "Race settings", (cx, 80), (255, 210, 60), anchor="center")
        for i, (label, value, hint) in enumerate(self.settings_rows()):
            rect = pygame.Rect(0, 0, 760, 90)
            rect.center = (cx, 210 + i * 110)
            selected = i == self.settings_row
            box = pygame.Surface(rect.size, pygame.SRCALPHA)
            box.fill((110, 180, 255, 210) if selected else (255, 255, 255, 40))
            S.blit(box, rect)
            pygame.draw.rect(S, (255, 255, 255) if selected else (120, 120, 120), rect, 4 if selected else 2, border_radius=10)
            self.text(S, self.font_med, label, (rect.left + 30, rect.centery), anchor="midleft")
            self.text(S, self.font_med, f"<  {value}  >" if selected else value, (rect.right - 130, rect.centery), (255, 255, 120), anchor="center")
            if selected:
                self.text(S, self.font_small, hint, (rect.right - 130, rect.bottom - 12), (230, 230, 230), anchor="center")
        total = len(self.players) + self.ai_count
        y = 560
        self.text(S, self.font, f"{total} racers:", (cx - 300, y), anchor="midright")
        x = cx - 280
        for p in self.players:
            S.blit(pygame.transform.smoothscale(self.roster[p.char_index].avatar_full, (56, 56)), (x, y - 28))
            self.text(S, self.font_small, p.label, (x + 28, y + 36), p.color, anchor="center")
            x += 66
        for _ in range(self.ai_count):
            pygame.draw.circle(S, (200, 200, 200), (x + 28, y), 24, 3)
            self.text(S, self.font, "?", (x + 28, y), anchor="center")
            self.text(S, self.font_small, "CPU", (x + 28, y + 36), (200, 200, 200), anchor="center")
            x += 66
        self.text(S, self.font_med, "Up/Down: choose   Left/Right: change   A: GO!   B: back", (cx, SCREEN_H - 40), anchor="center")

    def draw_pause(self):
        self.overlay(self.screen)
        cx, cy = SCREEN_W / 2, SCREEN_H / 2
        S = self.screen
        self.text(S, self.font_big, "PAUSED", (cx, cy - 100), anchor="center")
        self.text(S, self.font, "A / Enter  -  keep racing", (cx, cy), anchor="center")
        self.text(S, self.font, "Y / R  -  restart race", (cx, cy + 40), anchor="center")
        self.text(S, self.font, "B / Backspace  -  back to player select", (cx, cy + 80), anchor="center")
        self.text(S, self.font, "Select / View  or  X  -  quit game", (cx, cy + 120), (255, 180, 180), anchor="center")

    def draw_results(self):
        self.overlay(self.screen, 215)
        S = self.screen
        cx = SCREEN_W / 2
        winner = self.standings_cache[0]
        title = f"{winner.player.label} {winner.name} wins!" if winner.is_human else f"{winner.name} wins!"
        self.text(S, self.font_big, title, (cx, 60), (255, 210, 60), anchor="center")
        if any(k.little for k in self.humans):
            for i in range(5):
                draw_star(S, (255, 220, 60), cx - 200 + i * 100, 130 + math.sin(self.time * 5 + i) * 6, 26)
            self.text(S, self.font, "Hooray! Everyone did great!", (cx, 172), anchor="center")
        y = 215
        for i, k in enumerate(self.standings_cache):
            color = k.player.color if k.is_human else (255, 255, 255)
            self.text(S, self.font, ordinal(i + 1), (cx - 300, y), color, anchor="midleft")
            S.blit(pygame.transform.smoothscale(k.character.avatar_full, (46, 46)), (cx - 230, y - 23))
            name = f"{k.player.label}  {k.name}" if k.is_human else f"{k.name}  (CPU)"
            self.text(S, self.font, name, (cx - 170, y), color, anchor="midleft")
            self.text(S, self.font, fmt_time(k.finished_time) if k.finished_time else "racing...", (cx + 300, y),
                      color, anchor="midright")
            y += 50
        self.text(S, self.font_small, f"Best lap ever: {fmt_time(self.best_lap)}", (cx, SCREEN_H - 75), anchor="center")
        self.text(S, self.font_med, "A  race again    ·    B  player select", (cx, SCREEN_H - 38), anchor="center")

    # --- menu logic ----------------------------------------------------------------
    def update_lobby(self, frames):
        for device, f in frames.items():
            player = next((p for p in self.players if p.device == device), None)
            if player is None:
                if "confirm" in f.pressed and len(self.players) < MAX_HUMANS:
                    slot = min(set(range(MAX_HUMANS)) - {p.slot for p in self.players})
                    taken = {p.char_index for p in self.players}
                    default = next(i for i in [0, 1, 2, 7, 3, 9, 4, 10, 5, 11, 6, 8] if i not in taken)
                    self.players.append(Player(slot, device, default))
                    self.players.sort(key=lambda p: p.slot)
                    self.input.rumble(device, 0.4, 0.4, 150)
                continue
            if player.ready:
                if "back" in f.pressed:
                    player.ready = False
                elif "confirm" in f.pressed and all(p.ready for p in self.players):
                    self.enter_settings()
                    return
                continue
            n = len(self.roster)
            if "left" in f.pressed:
                player.char_index = (player.char_index - 1) % n
            elif "right" in f.pressed:
                player.char_index = (player.char_index + 1) % n
            elif "up" in f.pressed or "down" in f.pressed:
                player.little = not player.little
            elif "confirm" in f.pressed:
                player.ready = True
                self.input.rumble(device, 0.3, 0.6, 120)
            elif "back" in f.pressed:
                self.players.remove(player)

    def enter_settings(self):
        self.state = "settings"
        self.settings_row = 0
        max_ai = MAX_RACERS - len(self.players)
        if not self.settings_touched:
            self.ai_count = max(0, 4 - len(self.players))
            self.laps = 2 if all(p.little for p in self.players) else 3
        self.ai_count = min(self.ai_count, max_ai)

    def update_settings(self, pressed):
        if "up" in pressed:
            self.settings_row = (self.settings_row - 1) % 3
        elif "down" in pressed:
            self.settings_row = (self.settings_row + 1) % 3
        elif "left" in pressed or "right" in pressed:
            d = 1 if "right" in pressed else -1
            self.settings_touched = True
            if self.settings_row == 0:
                self.ai_count = max(0, min(MAX_RACERS - len(self.players), self.ai_count + d))
            elif self.settings_row == 1:
                self.ai_difficulty = max(0, min(2, self.ai_difficulty + d))
            else:
                self.laps = max(1, min(5, self.laps + d))
        elif "confirm" in pressed:
            self.new_race()
            self.state = "race"
        elif "back" in pressed:
            self.back_to_lobby()

    def back_to_lobby(self):
        for p in self.players:
            p.ready = False
        self.state = "lobby"

    def rebind_unplugged(self):
        """If someone's controller was unplugged, give them the next new pad that shows up."""
        used = {p.device for p in self.players}
        free = [d for d in self.input.pad_ids if d not in used]
        for p in self.players:
            if not self.input.is_connected(p.device) and free:
                p.device = free.pop(0)

    # --- main loop ----------------------------------------------------------------
    def step(self, dt):
        self.time += dt
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                pygame.display.toggle_fullscreen()
            self.input.handle_event(event)
        self.rebind_unplugged()
        frames = self.input.poll()
        # Menus outside the lobby can be driven by any joined player (or the keyboard).
        menu_devices = {p.device for p in self.players} | {"kb_arrows", "kb_wasd"}
        pressed = set().union(*(f.pressed for d, f in frames.items() if d in menu_devices))

        if self.state == "lobby":
            self.update_lobby(frames)
        elif self.state == "settings":
            self.update_settings(pressed)
        elif self.state == "race":
            if "pause" in pressed:
                self.state = "paused"
            else:
                self.update_race(dt, frames)
        elif self.state == "paused":
            if "confirm" in pressed or "pause" in pressed:
                self.state = "race"
            elif "restart" in pressed:
                self.new_race()
                self.state = "race"
            elif "back" in pressed:
                self.back_to_lobby()
            elif "quit" in pressed:
                self.running = False
        elif self.state == "results":
            self.update_race(dt, frames)  # the computer racers keep crossing the line
            if self.time - self.results_since < 2.0:
                pass  # ignore button mashing right as the race ends
            elif "confirm" in pressed or "restart" in pressed:
                self.new_race()
                self.state = "race"
            elif "back" in pressed:
                self.back_to_lobby()

        if self.state == "lobby":
            self.draw_lobby()
        elif self.state == "settings":
            self.draw_settings()
        else:
            self.draw_race()
            if self.state == "paused":
                self.draw_pause()
            elif self.state == "results":
                self.draw_results()

    def run(self):
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 1 / 30)
            self.step(dt)
            pygame.display.flip()
        pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kart Rush")
    parser.add_argument("--fullscreen", action="store_true", help="start in fullscreen (used by the Steam launcher)")
    args = parser.parse_args()
    Game(fullscreen=args.fullscreen).run()
