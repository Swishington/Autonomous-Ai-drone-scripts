"""Kart Rush - a top-down kart racer built for console-style controllers.

Run:  python kart_racer.py
See README.md in this folder for the full control layout.
"""

import json
import math
import os
import random

import pygame

from input_manager import InputManager

SCREEN_W, SCREEN_H = 1280, 720
FPS = 60
LAPS = 3
TRACK_WIDTH = 170
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

KART_COLORS = [(230, 60, 50), (50, 120, 230), (250, 200, 40), (60, 190, 90)]
KART_NAMES = ["You", "Blue Bolt", "Sunny", "Leafy"]

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
KART_RADIUS = 18


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
        self.trees = []
        while len(self.trees) < 90:
            x, y = rng.uniform(60, WORLD_W - 60), rng.uniform(60, WORLD_H - 60)
            if self.distance_to_center(x, y)[0] > TRACK_WIDTH / 2 + 70:
                self.trees.append((x, y, rng.randint(22, 38)))
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
        surf.fill((70, 150, 60))
        for _ in range(5000):
            shade = rng.choice([(62, 138, 54), (80, 162, 68), (66, 145, 58)])
            pygame.draw.circle(surf, shade, (rng.randrange(WORLD_W), rng.randrange(WORLD_H)), rng.randint(2, 6))
        half = TRACK_WIDTH // 2
        for i, (x, y) in enumerate(self.center):
            color = (225, 40, 40) if (i // 4) % 2 == 0 else (245, 245, 245)
            pygame.draw.circle(surf, color, (int(x), int(y)), half + CURB_WIDTH)
        for x, y in self.center:
            pygame.draw.circle(surf, (85, 85, 92), (int(x), int(y)), half)
        for i in range(0, self.n, 6):  # dashed centre line
            if (i // 6) % 2 == 0:
                a, b = self.center[i], self.center[(i + 3) % self.n]
                pygame.draw.line(surf, (200, 200, 200), a, b, 3)
        self._draw_start_line(surf)
        for idx in self.boost_pads:
            self._draw_boost_pad(surf, idx)
        for x, y, r in self.trees:
            pygame.draw.circle(surf, (40, 90, 35), (int(x) + 6, int(y) + 6), r)  # shadow
            pygame.draw.circle(surf, (30, 110, 40), (int(x), int(y)), r)
            pygame.draw.circle(surf, (50, 140, 55), (int(x) - r // 4, int(y) - r // 4), r // 2)
        return surf

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
    def __init__(self, name, color, x, y, heading, is_player=False, skill=1.0, lane=0.0):
        self.name = name
        self.color = color
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
        self.sprite = self._make_sprite()

    def _make_sprite(self):
        s = pygame.Surface((44, 30), pygame.SRCALPHA)
        for wx, wy in ((6, 2), (30, 2), (6, 22), (30, 22)):
            pygame.draw.rect(s, (25, 25, 25), (wx, wy, 10, 6), border_radius=2)
        pygame.draw.rect(s, self.color, (4, 6, 36, 18), border_radius=6)
        pygame.draw.polygon(s, tuple(min(255, c + 40) for c in self.color), [(32, 8), (43, 15), (32, 22)])
        pygame.draw.circle(s, (240, 240, 240), (20, 15), 6)
        pygame.draw.circle(s, (30, 30, 60), (22, 15), 3)
        return s

    @property
    def forward_speed(self):
        return self.vx * math.cos(self.heading) + self.vy * math.sin(self.heading)

    @property
    def progress(self):
        return self.laps * 100000 + self.idx

    def update(self, dt, steer, throttle, brake, drift, track):
        fx, fy = math.cos(self.heading), math.sin(self.heading)
        rx, ry = -fy, fx
        fwd = self.vx * fx + self.vy * fy
        lat = self.vx * rx + self.vy * ry

        dist, self.idx = track.distance_to_center(self.x, self.y, self.idx)
        self.on_grass = dist > TRACK_WIDTH / 2 + CURB_WIDTH
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

        # Boost pads
        pad_hit = None
        for p in track.boost_pads:
            px, py = track.point(p)
            if (px - self.x) ** 2 + (py - self.y) ** 2 < 55 ** 2:
                pad_hit = p
        if pad_hit is not None and pad_hit != self.last_pad:
            self.boost_timer = max(self.boost_timer, 1.1)
        self.last_pad = pad_hit

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

    def draw(self, screen, cam_x, cam_y):
        img = pygame.transform.rotate(self.sprite, -math.degrees(self.heading))
        cx, cy = self.x - cam_x, self.y - cam_y
        shadow = pygame.Surface((40, 40), pygame.SRCALPHA)
        pygame.draw.circle(shadow, (0, 0, 0, 70), (20, 20), 19)
        screen.blit(shadow, (cx - 16, cy - 16))
        if self.drifting:
            color = (80, 180, 255) if self.drift_charge < 0.7 else (255, 140, 40)
            bx, by = cx - math.cos(self.heading) * 20, cy - math.sin(self.heading) * 20
            for _ in range(3):
                pygame.draw.circle(screen, color, (bx + random.uniform(-8, 8), by + random.uniform(-8, 8)), random.randint(2, 5))
        if self.boost_timer > 0:
            bx, by = cx - math.cos(self.heading) * 26, cy - math.sin(self.heading) * 26
            pygame.draw.circle(screen, (255, 200, 60), (bx, by), random.randint(6, 10))
            pygame.draw.circle(screen, (255, 255, 200), (bx, by), 4)
        screen.blit(img, img.get_rect(center=(cx, cy)))


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
        self.font_big = pygame.font.Font(None, 110)
        self.font_med = pygame.font.Font(None, 48)
        self.font = pygame.font.Font(None, 32)
        self.font_small = pygame.font.Font(None, 24)
        self.input = InputManager()
        self.track = Track()
        self.best_lap = self._load_best()
        self.state = "menu"
        self.running = True
        self.new_race()

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
        self.karts = []
        # 2x2 starting grid just behind the start line; player starts at the back.
        grid = [(-16, 45), (-16, -45), (-8, 45), (-8, -45)]
        order = [1, 2, 3, 0]  # rivals take the front slots
        skills = {1: 0.97, 2: 0.93, 3: 0.89}
        for slot, ki in zip(grid, order):
            idx, off = slot
            px, py = t.point(idx)
            nx, ny = t.normal(idx)
            kart = Kart(KART_NAMES[ki], KART_COLORS[ki], px + nx * off, py + ny * off, t.tangents[idx % t.n],
                        is_player=(ki == 0), skill=skills.get(ki, 1.0), lane=random.uniform(-40, 40))
            kart.idx = idx % t.n
            self.karts.append(kart)
        self.player = next(k for k in self.karts if k.is_player)
        self.race_time = 0.0
        self.countdown = 3.5
        self.finish_order = []
        self.message = ""
        self.message_timer = 0.0

    # --- AI -----------------------------------------------------------------
    def ai_controls(self, kart):
        t = self.track
        speed = max(kart.forward_speed, 0)
        look = 8 + int(speed / 45)
        tx, ty = t.point(kart.idx + look)
        nx, ny = t.normal(kart.idx + look)
        tx, ty = tx + nx * kart.lane, ty + ny * kart.lane
        desired = math.atan2(ty - kart.y, tx - kart.x)
        diff = angle_diff(desired, kart.heading)
        steer = max(-1.0, min(1.0, diff * 2.2))
        # Look further ahead to slow down for sharp corners
        curve = abs(angle_diff(t.tangents[(kart.idx + look * 2) % t.n], t.tangents[kart.idx]))
        throttle, brake = 1.0, 0.0
        if curve > 1.1 and speed > 380:
            throttle, brake = 0.0, 0.5
        elif curve > 0.7 and speed > 450:
            throttle = 0.3
        # Gentle rubber-banding keeps the race close.
        n = t.n
        gap = (self.player.laps * n + self.player.idx) - (kart.laps * n + kart.idx)
        kart.skill = max(0.85, min(1.02, kart.skill + 0.00002 * max(-400, min(400, gap))))
        return steer, throttle, brake, False

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

    def collide_trees(self, kart):
        for tx, ty, r in self.track.trees:
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
        racing = self.countdown <= 0
        if not racing:
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
            if kart.finished_time is not None:
                steer, throttle, brake, drift = self.ai_controls(kart)
                throttle *= 0.5
            elif kart.is_player:
                steer, throttle, brake, drift = inp.steer, inp.throttle, inp.brake, inp.drift
            else:
                steer, throttle, brake, drift = self.ai_controls(kart)
            boost_before = kart.boost_timer
            kart.update(dt, steer, throttle, brake, drift, self.track)
            if kart.is_player and kart.boost_timer > boost_before + 0.2:
                self.input.rumble(0.3, 0.9, 200)
            self.collide_trees(kart)
            if kart.update_lap(prev_idx, self.track.n, self.race_time) and kart.finished_time is None:
                if kart.lap_times and kart.is_player:
                    lap = kart.lap_times[-1]
                    if self.best_lap is None or lap < self.best_lap:
                        self.best_lap = lap
                        self._save_best()
                        self.flash(f"NEW BEST LAP  {fmt_time(lap)}", 2.0)
                    elif kart.laps < LAPS:
                        self.flash(f"Lap {kart.laps}  {fmt_time(lap)}", 1.5)
                    if kart.laps == LAPS - 1:
                        self.flash("FINAL LAP!", 1.8)
                if kart.laps >= LAPS:
                    kart.finished_time = self.race_time
                    self.finish_order.append(kart)
                    if kart.is_player:
                        self.state = "finished"
                        self.input.rumble(0.7, 0.7, 500)
        self.collide_karts()
        self.message_timer -= dt

    def standings(self):
        finished = list(self.finish_order)
        rest = sorted((k for k in self.karts if k not in finished), key=lambda k: k.progress, reverse=True)
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
            r = img.get_rect(**{anchor: (pos[0] + 2, pos[1] + 2)})
            self.screen.blit(img, r)
        img = font.render(s, True, color)
        r = img.get_rect(**{anchor: pos})
        self.screen.blit(img, r)
        return r

    def draw_world(self):
        cam_x, cam_y = self.camera()
        self.screen.blit(self.track.surface, (0, 0), pygame.Rect(cam_x, cam_y, SCREEN_W, SCREEN_H))
        for k in sorted(self.karts, key=lambda k: k.is_player):
            k.draw(self.screen, cam_x, cam_y)

    def draw_hud(self):
        p = self.player
        place = self.standings().index(p) + 1
        panel = pygame.Surface((300, 150), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 120))
        self.screen.blit(panel, (16, 16))
        self.text(self.font_med, ordinal(place), (30, 26), (255, 220, 60))
        self.text(self.font_small, f"of {len(self.karts)}", (30 + self.font_med.size(ordinal(place))[0] + 8, 44))
        lap = min(LAPS, max(1, p.laps + 1))
        self.text(self.font, f"Lap {lap}/{LAPS}", (170, 30))
        self.text(self.font, f"Time  {fmt_time(self.race_time)}", (30, 80))
        cur = self.race_time - p.lap_start if p.laps >= 0 else 0.0
        self.text(self.font_small, f"Lap   {fmt_time(cur)}", (30, 112))
        self.text(self.font_small, f"Best  {fmt_time(self.best_lap)}", (30, 136))

        # Speedometer
        speed = abs(p.forward_speed)
        frac = min(1.0, speed / (MAX_SPEED * BOOST_SPEED_FACTOR))
        bar = pygame.Rect(SCREEN_W - 296, SCREEN_H - 60, 260, 22)
        pygame.draw.rect(self.screen, (0, 0, 0), bar.inflate(6, 6), border_radius=6)
        fill = bar.copy(); fill.width = int(bar.width * frac)
        color = (255, 170, 40) if p.boost_timer > 0 else (80, 200, 255)
        pygame.draw.rect(self.screen, color, fill, border_radius=4)
        self.text(self.font, f"{int(speed / 5)} km/h", (bar.right, bar.top - 8), anchor="bottomright")
        if p.drifting:
            charge = min(1.0, p.drift_charge / 0.7)
            c = (255, 140, 40) if charge >= 1 else (80, 180, 255)
            self.text(self.font, "DRIFT!" if charge < 1 else "DRIFT BOOST READY", (bar.left, bar.top - 8), c, anchor="bottomleft")

        # Minimap
        mm = self.track.minimap
        mx, my = SCREEN_W - mm.get_width() - 16, 16
        self.screen.blit(mm, (mx, my))
        s = self.track.minimap_scale
        for k in self.karts:
            pygame.draw.circle(self.screen, (0, 0, 0), (mx + k.x * s, my + k.y * s), 6 if k.is_player else 5)
            pygame.draw.circle(self.screen, k.color, (mx + k.x * s, my + k.y * s), 5 if k.is_player else 4)

        # Wrong way warning
        tangent = self.track.tangents[p.idx]
        if self.countdown <= 0 and abs(angle_diff(p.heading, tangent)) > 2.2 and speed > 60:
            self.text(self.font_med, "WRONG WAY!", (SCREEN_W / 2, 140), (255, 80, 80), anchor="center")
        elif p.on_grass and speed > 50:
            self.text(self.font, "Off track - get back on the road!", (SCREEN_W / 2, 140), (255, 230, 150), anchor="center")

        self.text(self.font_small, self.input.device_name, (16, SCREEN_H - 30), (220, 220, 220))

        if self.countdown > 0:
            n = math.ceil(self.countdown)
            label = str(n) if n <= 3 else "Ready"
            self.text(self.font_big, label, (SCREEN_W / 2, SCREEN_H / 2 - 80), (255, 230, 60), anchor="center")
        elif self.message_timer > 0:
            self.text(self.font_med, self.message, (SCREEN_W / 2, SCREEN_H / 2 - 120), (255, 255, 255), anchor="center")

    def overlay(self, alpha=160):
        s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        s.fill((0, 0, 20, alpha))
        self.screen.blit(s, (0, 0))

    def draw_menu(self):
        self.overlay(150)
        cx = SCREEN_W / 2
        self.text(self.font_big, "KART RUSH", (cx, 120), (255, 210, 60), anchor="center")
        self.text(self.font, f"{LAPS} laps  ·  4 racers  ·  beat the field!", (cx, 190), anchor="center")
        rows = [
            ("Steer", "Left stick / D-pad", "Arrows / A D"),
            ("Accelerate", "RT  (or A / Cross)", "Up / W"),
            ("Brake / Reverse", "LT  (or B / Circle)", "Down / S"),
            ("Drift (hold in a turn)", "RB / LB / X", "Space / Shift"),
            ("Pause", "Start / Options", "Esc"),
        ]
        y = 260
        self.text(self.font, "Controller", (cx - 40, y), (150, 200, 255), anchor="midleft")
        self.text(self.font, "Keyboard", (cx + 260, y), (150, 200, 255), anchor="midleft")
        for action, pad, key in rows:
            y += 40
            self.text(self.font, action, (cx - 70, y), anchor="midright")
            self.text(self.font, pad, (cx - 40, y), (230, 230, 230), anchor="midleft")
            self.text(self.font, key, (cx + 260, y), (230, 230, 230), anchor="midleft")
        self.text(self.font_small, "Hold drift through a corner until the sparks turn orange, then let go for a speed boost.",
                  (cx, y + 55), (255, 200, 140), anchor="center")
        blink = (pygame.time.get_ticks() // 500) % 2 == 0
        if blink:
            self.text(self.font_med, "Press A / Cross or Enter to race", (cx, SCREEN_H - 120), anchor="center")
        self.text(self.font_small, f"Input: {self.input.device_name}   ·   F11 fullscreen", (cx, SCREEN_H - 50), (200, 200, 200), anchor="center")

    def draw_pause(self):
        self.overlay()
        cx, cy = SCREEN_W / 2, SCREEN_H / 2
        self.text(self.font_big, "PAUSED", (cx, cy - 100), anchor="center")
        self.text(self.font, "A / Enter  -  resume", (cx, cy), anchor="center")
        self.text(self.font, "Y / R  -  restart race", (cx, cy + 40), anchor="center")
        self.text(self.font, "B / Backspace  -  back to title", (cx, cy + 80), anchor="center")

    def draw_results(self):
        self.overlay()
        cx = SCREEN_W / 2
        place = self.finish_order.index(self.player) + 1
        title = "YOU WIN!" if place == 1 else f"You finished {ordinal(place)}"
        self.text(self.font_big, title, (cx, 120), (255, 210, 60), anchor="center")
        y = 220
        for i, k in enumerate(self.standings()):
            color = (255, 255, 120) if k.is_player else (255, 255, 255)
            self.text(self.font_med, ordinal(i + 1), (cx - 260, y), color, anchor="midleft")
            pygame.draw.circle(self.screen, k.color, (cx - 170, y), 12)
            self.text(self.font_med, k.name, (cx - 140, y), color, anchor="midleft")
            self.text(self.font_med, fmt_time(k.finished_time) if k.finished_time else "racing...", (cx + 260, y), color, anchor="midright")
            y += 55
        laps = "   ".join(fmt_time(t) for t in self.player.lap_times)
        self.text(self.font, f"Your laps:  {laps}", (cx, y + 20), anchor="center")
        self.text(self.font, f"Best lap ever:  {fmt_time(self.best_lap)}", (cx, y + 60), anchor="center")
        self.text(self.font_med, "A / Enter  race again    ·    B  title", (cx, SCREEN_H - 80), anchor="center")

    # --- main loop ----------------------------------------------------------------
    def step(self, dt):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                pygame.display.toggle_fullscreen()
            self.input.handle_event(event)
        inp = self.input.poll()

        if self.state == "menu":
            if "confirm" in inp.pressed:
                self.new_race()
                self.state = "race"
        elif self.state == "race":
            if "pause" in inp.pressed:
                self.state = "paused"
            else:
                self.update_race(dt, inp)
        elif self.state == "paused":
            if "confirm" in inp.pressed or "pause" in inp.pressed:
                self.state = "race"
            elif "restart" in inp.pressed:
                self.new_race()
                self.state = "race"
            elif "back" in inp.pressed:
                self.state = "menu"
        elif self.state == "finished":
            self.update_race(dt, inp)  # let the rivals cross the line in the background
            if "confirm" in inp.pressed or "restart" in inp.pressed:
                self.new_race()
                self.state = "race"
            elif "back" in inp.pressed:
                self.state = "menu"

        self.draw_world()
        if self.state == "menu":
            self.draw_menu()
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
