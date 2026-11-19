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

from cartoon import INK, Canvas, TextCache, blur, draw, finish, load_font, rounded_panel, soft_shadow
from characters import load_roster
from input_manager import EMPTY_FRAME, InputManager
from sound import Audio

SCREEN_W, SCREEN_H = 1280, 720
FPS = 60
MAX_HUMANS = 4
MAX_RACERS = 8
DIFFICULTIES = ["Easy", "Medium", "Hard"]
AI_SKILL = [0.58, 0.72, 0.88]       # rival top speed for each difficulty (Easy / Medium / Hard)
AI_CATCH_UP = [0.00, 0.03, 0.06]    # how much rivals speed up when behind
AI_EASE_OFF = [0.15, 0.12, 0.08]    # how much rivals slow down when ahead
LITTLE_DEFAULT_CHARACTER = 0   # roster index of the little sister's racer
PLAYER_COLORS = [(255, 80, 80), (70, 150, 255), (80, 210, 90), (255, 200, 40)]
TRACK_WIDTH = 180
CURB_WIDTH = 12
WORLD_W, WORLD_H = 3200, 2300
SAVE_DIR = os.path.expanduser("~")
AUDIO_SETTINGS = os.path.join(os.path.expanduser("~"), ".config", "kart-rush", "audio.json")

# Hand-placed control points of the circuit (smoothed with a Catmull-Rom spline).
TRACK_POINTS = [
    (420, 1500), (400, 900), (520, 480), (900, 330), (1250, 450), (1420, 800),
    (1750, 950), (2050, 650), (2300, 380), (2750, 420), (2930, 800), (2850, 1250),
    (2500, 1400), (2350, 1700), (2700, 1900), (2550, 2120), (1900, 2080),
    (1500, 1750), (1150, 1950), (700, 2050), (450, 1850),
]
BOOST_PADS = 3                  # placed automatically on the straightest stretches

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
WALL_BOUNCE = 0.25              # walls guide the kart along rather than bouncing it back
WRONG_WAY_SECONDS = 1.5         # going the wrong way this long -> magic poof, facing the right way
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
        self.boost_pads = self._place_boost_pads()
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

    def _place_boost_pads(self):
        """Put the speed arrows where the road ahead is straightest, so a boost never
        launches anyone into a bend (which felt like the arrows slowed you down)."""
        ahead = 70  # look ~840 px down the road
        turn = [sum(abs(angle_diff(self.tangents[(i + j + 1) % self.n], self.tangents[(i + j) % self.n]))
                    for j in range(-10, ahead)) for i in range(self.n)]
        pads = []
        for i in sorted(range(self.n), key=lambda i: turn[i]):
            if i < 40 or i > self.n - 40:
                continue  # keep the start line clear
            if all(min(abs(i - p), self.n - abs(i - p)) > self.n // (BOOST_PADS + 1) for p in pads):
                pads.append(i)
            if len(pads) == BOOST_PADS:
                break
        return sorted(pads)

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
        self._draw_grass(surf, rng)
        self._draw_road_shadow(surf)
        self._draw_road(surf)
        self.ground_surface = surf.copy()  # 3D mode: ground without the flat prop stickers
        for ob in self.obstacles:
            self._draw_obstacle(surf, *ob)
        return surf

    @staticmethod
    def _draw_grass(surf, rng):
        """Soft, bright lawn: big blurry colour patches, little tufts and flowers."""
        surf.fill((118, 196, 84))
        q = 4
        patches = pygame.Surface((WORLD_W // q, WORLD_H // q))
        patches.fill((118, 196, 84))  # opaque base so blurred edges don't go dark
        for _ in range(260):
            c = rng.choice([(130, 206, 92), (108, 186, 76), (124, 202, 88)])
            pygame.draw.circle(patches, c, (rng.randrange(WORLD_W // q), rng.randrange(WORLD_H // q)), rng.randint(10, 34))
        surf.blit(pygame.transform.smoothscale(blur(patches, 4), (WORLD_W, WORLD_H)), (0, 0))
        for _ in range(1400):  # grass tufts
            x, y = rng.randrange(WORLD_W), rng.randrange(WORLD_H)
            col = (88, 160, 64)
            for dx in (-4, 0, 4):
                pygame.draw.line(surf, col, (x + dx * 0.4, y + 3), (x + dx, y - 4 - (dx == 0) * 2), 2)
        for _ in range(420):  # flowers
            x, y = rng.randrange(WORLD_W), rng.randrange(WORLD_H)
            c = rng.choice([(255, 255, 255), (255, 175, 215), (255, 232, 100), (200, 170, 255)])
            for k in range(5):
                a = k * 2 * math.pi / 5
                pygame.draw.circle(surf, c, (x + math.cos(a) * 4, y + math.sin(a) * 4), 3)
            pygame.draw.circle(surf, (255, 190, 40), (x, y), 2)

    def _draw_road_shadow(self, surf):
        q = 4
        layer = pygame.Surface((WORLD_W // q, WORLD_H // q), pygame.SRCALPHA)
        r = (TRACK_WIDTH / 2 + CURB_WIDTH + 14) / q
        for x, y in self.center[::2]:
            pygame.draw.circle(layer, (30, 70, 30, 110), (x / q + 1.5, y / q + 2.5), r)
        surf.blit(pygame.transform.smoothscale(blur(layer, 3), (WORLD_W, WORLD_H)), (0, 0))

    def _draw_road(self, surf):
        """Road, curbs, centre line, start line and boost pads, supersampled in tiles."""
        tile, k = 800, 2
        half = TRACK_WIDTH / 2
        reach = half + CURB_WIDTH + 12
        for ty in range(0, WORLD_H, tile):
            for tx in range(0, WORLD_W, tile):
                pts = [(i, x, y) for i, (x, y) in enumerate(self.center)
                       if tx - reach < x < tx + tile + reach and ty - reach < y < ty + tile + reach]
                if not pts:
                    continue
                layer = pygame.Surface((tile * k, tile * k), pygame.SRCALPHA)
                T = lambda x, y: ((x - tx) * k, (y - ty) * k)  # noqa: E731
                for i, x, y in pts:
                    pygame.draw.circle(layer, INK, T(x, y), (half + CURB_WIDTH + 4) * k)
                for i, x, y in pts:
                    color = (255, 96, 156) if (i // 4) % 2 == 0 else (252, 248, 252)
                    pygame.draw.circle(layer, color, T(x, y), (half + CURB_WIDTH) * k)
                for i, x, y in pts:
                    pygame.draw.circle(layer, (64, 60, 82), T(x, y), (half + 3) * k)
                for i, x, y in pts:
                    pygame.draw.circle(layer, (92, 94, 114), T(x, y), half * k)
                for i, x, y in pts:
                    pygame.draw.circle(layer, (100, 103, 124), T(x, y), (half - 26) * k)
                for i, x, y in pts:  # rounded dashes down the middle
                    if i % 12 < 5:
                        pygame.draw.circle(layer, (236, 236, 244), T(x, y), 3.5 * k)
                self._draw_start_line(layer, T, k)
                for idx in self.boost_pads:
                    self._draw_boost_pad(layer, idx, T, k)
                surf.blit(pygame.transform.smoothscale(layer, (tile, tile)), (tx, ty))

    @staticmethod
    def _draw_obstacle(surf, x, y, r, kind):
        """Props are outlined, shaded 'stickers' with a soft drop shadow."""
        size = r * 2 + 4
        c = Canvas(size, size)
        m = size / 2
        if kind == "tree":
            for i in range(9):  # bumpy cloud-like canopy
                a = i * 2 * math.pi / 9
                draw.circle(c, (52, 150, 66), (m + math.cos(a) * r * 0.62, m + math.sin(a) * r * 0.62), r * 0.42)
            draw.circle(c, (52, 150, 66), (m, m), r * 0.7)
            draw.circle(c, (86, 186, 84), (m - r * 0.25, m - r * 0.25), r * 0.38)
            draw.circle(c, (120, 210, 104), (m - r * 0.35, m - r * 0.38), r * 0.16)
        elif kind == "lollipop":
            colors = [(255, 90, 150), (255, 255, 255), (110, 200, 255), (255, 255, 255)]
            for i in range(8):
                a0 = i * math.pi / 4 + 0.3
                draw.polygon(c, colors[i % 4], [(m, m)] + [(m + math.cos(a0 + t * math.pi / 16) * r, m + math.sin(a0 + t * math.pi / 16) * r)
                                                           for t in range(5)])
            draw.circle(c, (255, 255, 255), (m, m), r * 0.18)
        elif kind == "gumdrop":
            col = random.Random(int(x) * 31 + int(y)).choice([(255, 90, 130), (120, 220, 120), (255, 200, 70), (170, 130, 255)])
            draw.circle(c, col, (m, m), r)
            draw.circle(c, tuple(min(255, v + 70) for v in col), (m - r * 0.35, m - r * 0.35), r * 0.3)
            rng = random.Random(int(x) + int(y) * 7)
            for _ in range(9):
                draw.circle(c, (255, 255, 255), (m + rng.uniform(-0.6, 0.6) * r, m + rng.uniform(-0.6, 0.6) * r), 1.6)
        else:  # mushroom
            draw.circle(c, (232, 52, 62), (m, m), r)
            for dx, dy, sr in ((-0.35, -0.35, 0.26), (0.35, -0.2, 0.2), (0.05, 0.38, 0.24), (-0.5, 0.25, 0.15), (0.5, 0.35, 0.13)):
                draw.circle(c, (255, 250, 245), (m + dx * r, m + dy * r), sr * r)
        sprite = finish(c, (size, size), line=3)
        shadow = soft_shadow(int(r * 2.1), int(r * 1.7), 110)
        surf.blit(shadow, shadow.get_rect(center=(x + 7, y + 10)))
        surf.blit(sprite, sprite.get_rect(center=(x, y)))

    def _draw_start_line(self, layer, T, k):
        x, y = self.center[0]
        nx, ny = self.normal(0)
        a = self.tangents[0]
        tx, ty = math.cos(a), math.sin(a)
        cells, size = 12, TRACK_WIDTH / 12
        for row in range(2):
            for c in range(cells):
                off = -TRACK_WIDTH / 2 + (c + 0.5) * size
                cx, cy = x + nx * off + tx * (row - 0.5) * size, y + ny * off + ty * (row - 0.5) * size
                h = size / 2 + 0.5
                corners = [(cx + tx * dx * h + nx * dy * h, cy + ty * dx * h + ny * dy * h)
                           for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                color = (40, 30, 50) if (c + row) % 2 else (250, 250, 250)
                pygame.draw.polygon(layer, color, [T(*p) for p in corners])

    def _draw_boost_pad(self, layer, idx, T, k):
        x, y = self.center[idx]
        a = self.tangents[idx]
        tx, ty = math.cos(a), math.sin(a)
        nx, ny = self.normal(idx)
        for j in range(3):
            base = (x + tx * (j * 24 - 24), y + ty * (j * 24 - 24))
            tip = (base[0] + tx * 22, base[1] + ty * 22)
            wide = TRACK_WIDTH / 2 - 18
            left = (base[0] + nx * wide - tx * 10, base[1] + ny * wide - ty * 10)
            right = (base[0] - nx * wide - tx * 10, base[1] - ny * wide - ty * 10)
            notch = (base[0] + tx * 8, base[1] + ty * 8)
            poly = [T(*left), T(*tip), T(*right), T(*notch)]
            pygame.draw.polygon(layer, (255, 214, 40), poly)
            pygame.draw.polygon(layer, INK, poly, 3 * k)

    def _render_minimap(self, width):
        scale = width / WORLD_W
        mm = pygame.Surface((int(WORLD_W * scale), int(WORLD_H * scale)), pygame.SRCALPHA)
        pygame.draw.rect(mm, (30, 20, 50, 160), mm.get_rect(), border_radius=14)
        pygame.draw.rect(mm, INK, mm.get_rect(), 3, border_radius=14)
        pts = [(x * scale, y * scale) for x, y in self.center]
        lw = max(4, int(width / 45))
        for p in pts:
            pygame.draw.circle(mm, INK, p, lw / 2 + 2)
        for p in pts:
            pygame.draw.circle(mm, (250, 245, 255), p, lw / 2)
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
    shadow = None  # shared soft drop shadow, made on first draw

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
            font = load_font(26)
            text = font.render(player.label, True, (255, 255, 255))
            self.tag = pygame.Surface((text.get_width() + 14, text.get_height() + 6), pygame.SRCALPHA)
            pygame.draw.rect(self.tag, player.color, self.tag.get_rect(), border_radius=9)
            pygame.draw.rect(self.tag, INK, self.tag.get_rect(), 3, border_radius=9)
            self.tag.blit(text, (7, 3))

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
        self.steer_input = steer  # the 3D view leans the kart into turns
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

        if fwd > top:  # over the limit (a boost just ended): ease off; grass still bites quickly
            fwd = max(top, fwd - (900 if self.on_grass else 240) * dt)
        elif throttle > 0:  # the engine only pushes up to top speed
            fwd = min(top, fwd + ACCEL * throttle * (1.6 if self.boost_timer > 0 else 1.0) * dt)
        if brake > 0:
            fwd -= (BRAKE if fwd > 0 else ACCEL * 0.6) * brake * dt
        if throttle == 0 and brake == 0:
            fwd *= math.exp(-0.9 * dt)
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
        if walls:
            bounced = self.keep_on_track(track, dist)
        self.on_grass = (not walls) and dist > TRACK_WIDTH / 2 + CURB_WIDTH

        # Boost pads
        pad_hit = None
        for p in track.boost_pads:  # the arrows cover most of the road's width
            px, py = track.point(p)
            ta = track.tangents[p]
            along = (self.x - px) * math.cos(ta) + (self.y - py) * math.sin(ta)
            across = -(self.x - px) * math.sin(ta) + (self.y - py) * math.cos(ta)
            if -45 < along < 45 and abs(across) < TRACK_WIDTH / 2 - 10:
                pad_hit = p
        if pad_hit is not None and pad_hit != self.last_pad:
            self.boost_timer = max(self.boost_timer, 1.1)
        self.last_pad = pad_hit
        self.message_timer -= dt
        return bounced

    def keep_on_track(self, track, dist=None):
        """Little Racer's invisible walls: the whole kart stays on the road."""
        if dist is None:
            dist, self.idx = track.distance_to_center(self.x, self.y, self.idx)
        if dist > TRACK_WIDTH:  # lost track of where we are (e.g. pushed hard): search everywhere
            dist, self.idx = track.distance_to_center(self.x, self.y)
        limit = TRACK_WIDTH / 2 + CURB_WIDTH - KART_RADIUS * 0.9
        if dist <= limit or dist == 0:
            return False
        cx, cy = track.point(self.idx)
        nx, ny = (self.x - cx) / dist, (self.y - cy) / dist
        self.x, self.y = cx + nx * limit, cy + ny * limit
        vn = self.vx * nx + self.vy * ny
        if vn > 0:  # remove the push into the wall, keep the speed along it
            self.vx -= (1 + WALL_BOUNCE) * vn * nx
            self.vy -= (1 + WALL_BOUNCE) * vn * ny
        # Steer the nose back along the road so she glides on instead of sticking.
        self.heading += angle_diff(track.tangents[self.idx], self.heading) * 0.35
        return vn > 60

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
        if Kart.shadow is None:
            Kart.shadow = soft_shadow(58, 44, 120)
        surf.blit(Kart.shadow, Kart.shadow.get_rect(center=(cx + 5, cy + 8)))
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
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "size", "star", "puff")

    def __init__(self, x, y, vx, vy, life, color, size, star=False, puff=False):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.puff = puff
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
    def __init__(self, headless=False, fullscreen=False, mode3d=False, title="Kart Rush"):
        """`mode3d=True` is Kart Rush 3D (chase cameras); otherwise the classic top-down Kart Rush."""
        pygame.init()
        self.title = title
        # Each game keeps its own best lap (".kart_rush_best.json", ".kart_rush_3d_best.json").
        self.save_file = os.path.join(SAVE_DIR, "." + title.lower().replace(" ", "_") + "_best.json")
        self.r3d = None
        if mode3d:
            self.r3d = self._start_3d(headless, fullscreen)
        if self.r3d is None:  # classic top-down view
            flags = 0 if headless else pygame.SCALED | (pygame.FULLSCREEN if fullscreen else pygame.RESIZABLE)
            self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), flags)
        else:  # 2D HUD and menus are drawn on this see-through layer over the 3D scene
            self.screen = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        pygame.mouse.set_visible(headless or not fullscreen)
        pygame.display.set_caption(title)
        self.clock = pygame.time.Clock()
        self.font_huge = load_font(130)
        self.font_big = load_font(100)
        self.font_med = load_font(48)
        self.font = load_font(32)
        self.font_small = load_font(25)
        self.text_cache = TextCache()
        self.screen.fill((40, 20, 60))  # building the cartoon sprites takes a moment
        self.text(self.screen, self.font_big, "Loading...", (SCREEN_W / 2, SCREEN_H / 2), (255, 210, 60), anchor="center")
        if self.r3d:
            self.r3d.show_overlay(self.screen)
        pygame.display.flip()
        self.input = InputManager()
        music_on, sfx_on = self._load_audio_settings()
        self.audio = Audio(music_on, sfx_on)
        self.track = Track()
        self.roster = load_roster()
        if self.r3d:
            self.r3d.load_world(self.track, self.roster)
        self.best_lap = self._load_best()
        self.players = []
        self.ai_count = 3
        self.ai_difficulty = 0
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

    @staticmethod
    def _start_3d(headless, fullscreen):
        """Open an OpenGL window (or offscreen buffer) for the 3D view; None if this PC can't."""
        try:
            import render3d
            if headless:
                pygame.display.set_mode((1, 1))
                return render3d.Renderer3D(headless_size=(SCREEN_W, SCREEN_H))
            pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
            pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
            pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
            pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
            pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
            flags = pygame.OPENGL | pygame.DOUBLEBUF | (pygame.FULLSCREEN if fullscreen else pygame.RESIZABLE)
            try:
                pygame.display.set_mode((0, 0) if fullscreen else (SCREEN_W, SCREEN_H), flags)
            except pygame.error:  # no multisampling available
                pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 0)
                pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 0)
                pygame.display.set_mode((0, 0) if fullscreen else (SCREEN_W, SCREEN_H), flags)
            return render3d.Renderer3D()
        except Exception as e:  # noqa: BLE001 - any GL/driver problem: fall back to 2D
            print(f"3D view unavailable ({e}); using the top-down view.")
            pygame.display.quit()
            pygame.display.init()
            return None

    def present(self):
        """Show the frame: 3D views + HUD layer, or the 2D screen."""
        if self.r3d:
            racing = self.state not in ("lobby", "settings", "quit_confirm")
            views = list(zip(view_rects(len(self.humans)), self.humans)) if racing else []
            self.r3d.render(self, self.screen, views)
        pygame.display.flip()

    @staticmethod
    def _load_audio_settings():
        try:
            with open(AUDIO_SETTINGS) as f:
                data = json.load(f)
            return bool(data.get("music", True)), bool(data.get("sfx", True))
        except (OSError, ValueError, AttributeError):
            return True, True

    def _save_audio_settings(self):
        try:
            os.makedirs(os.path.dirname(AUDIO_SETTINGS), exist_ok=True)
            with open(AUDIO_SETTINGS, "w") as f:
                json.dump({"music": self.audio.music_on, "sfx": self.audio.sfx_on}, f)
        except OSError:
            pass

    def sfx(self, name, kart=None):
        """Play an effect (for karts, only the human players' ones, so 8 karts aren't a din)."""
        if kart is None or kart.is_human:
            self.audio.play(name)

    def _load_best(self):
        try:
            with open(self.save_file) as f:
                return json.load(f).get("best_lap")
        except (OSError, ValueError):
            return None

    def _save_best(self):
        try:
            with open(self.save_file, "w") as f:
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
        d = self.ai_difficulty
        kart.skill = clamp(base + 0.0004 * clamp(gap, -400, 300), base - AI_EASE_OFF[d], base + AI_CATCH_UP[d])

    # --- Little Racer helpers ---------------------------------------------------------
    def little_controls(self, kart, inp, dt):
        """Toddler mode: auto-go, steering help, turn-around and sparkle boost."""
        tangent = self.track.tangents[kart.idx]
        off = angle_diff(tangent, kart.heading)
        along = kart.vx * math.cos(tangent) + kart.vy * math.sin(tangent)  # speed down the track
        slow = abs(kart.forward_speed) < 60
        if along < -40 or abs(off) > 1.8 or (slow and abs(off) > 0.9):
            kart.wrong_way_timer += dt
        else:
            kart.wrong_way_timer = max(0.0, kart.wrong_way_timer - dt)
        if kart.wrong_way_timer > WRONG_WAY_SECONDS:
            self.magic_turn_around(kart)
        assist, _, _ = self.ai_drive(kart, lane=0.0)
        steer = clamp(assist * LITTLE_ASSIST + inp.steer * LITTLE_INPUT)

        kart.sparkle_cooldown -= dt
        if "boost" in inp.pressed and kart.sparkle_cooldown <= 0:
            kart.sparkle_cooldown = SPARKLE_COOLDOWN
            kart.boost_timer = max(kart.boost_timer, 0.9)
            self.burst(kart.x, kart.y, kart.character.trail, 26, star=True)
            self.rumble(kart, 0.4, 0.8, 180)
            self.sfx("sparkle", kart)
        # The kart always keeps moving; the gas just makes it a bit faster. No brakes.
        throttle = max(0.75, inp.throttle)
        return steer, throttle, 0.0, False

    def magic_turn_around(self, kart):
        """Poof! A puff of cartoon smoke and the kart is facing the right way again."""
        t = self.track
        self.puff(kart.x, kart.y)
        # Pop back to the middle of the road, pointing forwards, still moving.
        nx, ny = t.normal(kart.idx)
        cx, cy = t.point(kart.idx)
        side = (kart.x - cx) * nx + (kart.y - cy) * ny
        kart.x, kart.y = cx + nx * clamp(side, -30, 30), cy + ny * clamp(side, -30, 30)
        kart.heading = t.tangents[kart.idx]
        speed = max(220.0, abs(kart.forward_speed))
        kart.vx, kart.vy = math.cos(kart.heading) * speed, math.sin(kart.heading) * speed
        kart.wrong_way_timer = 0.0
        kart.say("Poof! This way!", 1.6)
        self.sfx("poof", kart)
        self.puff(kart.x, kart.y)
        self.burst(kart.x, kart.y, kart.character.trail + [(255, 255, 255)], 18, star=True, speed=260)
        self.rumble(kart, 0.4, 0.6, 250)

    def puff(self, x, y):
        for _ in range(14):
            a = random.uniform(0, 2 * math.pi)
            v = random.uniform(40, 160)
            self.particles.append(Particle(x + math.cos(a) * 12, y + math.sin(a) * 12, math.cos(a) * v, math.sin(a) * v,
                                           random.uniform(0.5, 0.9), random.choice([(245, 242, 255), (225, 215, 245), (255, 235, 250)]),
                                           random.uniform(9, 16), puff=True))

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
            if p.puff:  # cartoon smoke: grows as it fades
                size = p.size * (1.0 + 1.4 * (1 - p.life / p.max_life))
                pygame.draw.circle(surf, INK, (x, y), size + 3)
                pygame.draw.circle(surf, p.color, (x, y), size)
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
                        if (a.is_human or b.is_human) and rel < -60:
                            self.sfx("bump")

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
                    self.sfx("bonk", kart)

    def update_race(self, dt, frames):
        self.emit_trails(dt)
        self.banner_timer -= dt
        if self.countdown > 0:
            prev = self.countdown
            self.countdown -= dt
            tick = math.ceil(prev) != math.ceil(self.countdown) and 0 < self.countdown <= 3
            for h in self.humans:
                if tick:
                    self.rumble(h, 0.2, 0.2, 80)
                if self.countdown <= 0:
                    self.rumble(h, 0.5, 0.5, 200)
            if tick:
                self.sfx("beep")
            if self.countdown <= 0:
                self.banner, self.banner_timer = "GO!", 1.0
                self.sfx("go")
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
            charge_before = kart.drift_charge
            bounced = kart.update(dt, steer, throttle, brake, drift, self.track)
            if kart.is_human:
                if kart.boost_timer > boost_before + 0.2:
                    self.rumble(kart, 0.3, 0.9, 200)
                    self.sfx("boost")
                if charge_before < 0.7 <= kart.drift_charge:
                    self.sfx("ready")  # drift boost is charged: let go!
                if bounced:
                    self.sfx("boing")
                    self.rumble(kart, 0.5, 0.2, 120)
                    self.burst(kart.x, kart.y, [(255, 255, 255), (255, 230, 120)], 8, star=True, speed=120)
            self.collide_obstacles(kart)
            if kart.update_lap(prev_idx, self.track.n, self.race_time) and kart.finished_time is None:
                self.on_lap(kart)
        self.collide_karts()
        for kart in self.karts:  # bumps from other karts can't push a Little Racer off the road
            if kart.little:
                kart.keep_on_track(self.track)
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
                self.sfx("best")
            elif kart.laps < self.laps:
                kart.say("Yay! Keep going!" if kart.little else f"Lap {kart.laps}  {fmt_time(lap)}", 1.8)
                self.sfx("lap")
            if kart.laps == self.laps - 1 and kart.laps > 0:
                if not kart.little:
                    kart.say("FINAL LAP!", 1.8)
                self.sfx("final_lap")
        if kart.laps >= self.laps:
            kart.finished_time = self.race_time
            self.finish_order.append(kart)
            if kart.is_human:
                self.rumble(kart, 0.7, 0.7, 500)
                self.sfx("finish")
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
    def text(self, surf, font, s, pos, color=(255, 255, 255), anchor="topleft", shadow=True):
        """Chunky outlined cartoon text (cached)."""
        img = self.text_cache.render(font, s, color) if shadow else font.render(s, True, color)
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
        if self.r3d:
            return 0, 0  # the 3D renderer draws the world
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
        stats = f"Time {fmt_time(self.race_time)}   Best {fmt_time(self.best_lap)}"
        show_stats = not kart.little and not compact
        pw = avatar + (150 if compact else 210)
        if show_stats:
            pw = max(pw, avatar + 40 + small.size(stats)[0])
        ph = avatar + 16
        px = w - pw - 8 if right_side else 8
        rounded_panel(surf, (px, 8, pw, ph), (30, 20, 50, 170), kart.player.color if multi else INK, 4, 16)
        if kart.little:  # make the mode obvious at a glance
            badge = self.text_cache.render(small, "LITTLE RACER", (255, 255, 255))
            bw = badge.get_width() + 14
            rounded_panel(surf, (px + 8, 8 + ph + 4, bw, badge.get_height() + 2), (255, 110, 180), INK, 3, 10)
            surf.blit(badge, (px + 15, 8 + ph + 4))
        surf.blit(pygame.transform.smoothscale(kart.character.avatar_full, (avatar, avatar)), (px + 8, 16))
        tx = px + 16 + avatar
        label = f"{kart.player.label}  {ordinal(place)}" if multi else ordinal(place)
        self.text(surf, med, label, (tx, 14), (255, 220, 60))
        self.text(surf, norm, f"Lap {lap}/{self.laps}", (tx, 14 + med.get_height()))
        if show_stats:
            self.text(surf, small, stats, (tx, 14 + med.get_height() + 28))

        speed = abs(kart.forward_speed)
        if not kart.little:
            bw = 160 if compact else 240
            bar_x = w - bw - 20 if (right_side or not multi) else 20
            bar = pygame.Rect(bar_x, h - 34, bw, 16 if compact else 20)
            pygame.draw.rect(surf, INK, bar.inflate(8, 8), border_radius=10)
            pygame.draw.rect(surf, (70, 60, 95), bar, border_radius=6)
            fill = bar.copy()
            fill.width = int(bar.width * min(1.0, speed / (MAX_SPEED * BOOST_SPEED_FACTOR)))
            if fill.width > 0:
                pygame.draw.rect(surf, (255, 170, 40) if kart.boost_timer > 0 else (80, 200, 255), fill, border_radius=6)
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
        self.screen.fill((0, 0, 0, 0) if self.r3d else (10, 10, 20))
        if not self.r3d:
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
        if self.r3d:
            self.screen.fill((0, 0, 0, 0))  # a 3D flyover of the track shows through
            return
        k = self.karts[0]
        self.screen.blit(self.track.surface, (0, 0), pygame.Rect(*self.camera(k, SCREEN_W, SCREEN_H), SCREEN_W, SCREEN_H))

    def draw_lobby(self):
        self.draw_menu_background()
        self.overlay(self.screen, 170)
        S = self.screen
        cx = SCREEN_W / 2
        self.text(S, self.font_big, self.title.upper(), (cx, 52), (255, 210, 60), anchor="center")
        self.text(S, self.font, "Up to 4 players: press A on your controller (or Enter / Space on the keyboard) to join!",
                  (cx, 110), anchor="center")
        pw, ph, gap = 290, 500, 20
        left = cx - (4 * pw + 3 * gap) / 2
        for slot in range(MAX_HUMANS):
            rect = pygame.Rect(left + slot * (pw + gap), 145, pw, ph)
            player = next((p for p in self.players if p.slot == slot), None)
            if player is None:
                rounded_panel(S, rect, (255, 255, 255, 40), (220, 220, 230), 3, 22)
                self.text(S, self.font_med, f"P{slot + 1}", (rect.centerx, rect.top + 50), PLAYER_COLORS[slot], anchor="center")
                if (pygame.time.get_ticks() // 600) % 2 == 0 or slot != len(self.players):
                    self.text(S, self.font, "Press A to join", (rect.centerx, rect.centery), anchor="center")
                continue
            ch = self.roster[player.char_index]
            rounded_panel(S, rect.inflate(8, 8), (0, 0, 0, 0), INK, 4, 26)
            rounded_panel(S, rect, (*ch.body, 215), player.color, 7, 22)
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
            rounded_panel(S, mode_rect, (255, 120, 190) if player.little else (80, 140, 240), INK, 4, 16)
            self.text(S, self.font, "Little Racer" if player.little else "Big Racer", (mode_rect.centerx, mode_rect.top + 20), anchor="center")
            self.text(S, self.font_small, "easy - kart helps steer" if player.little else "full control + drifting",
                      (mode_rect.centerx, mode_rect.top + 46), (240, 240, 240), anchor="center")
            if player.ready:
                self.text(S, self.font_med, "READY!", (rect.centerx, rect.bottom - 70), (120, 255, 120), anchor="center")
                self.text(S, self.font_small, "B to change", (rect.centerx, rect.bottom - 32), anchor="center")
            else:
                self.text(S, self.font_small, "Left/Right: racer   Y or D-pad: mode", (rect.centerx, rect.bottom - 82), anchor="center")
                self.text(S, self.font_small, "A: ready   B: leave", (rect.centerx, rect.bottom - 56), anchor="center")
        if self.players and all(p.ready for p in self.players):
            self.text(S, self.font_med, "Everyone ready! Press A for race settings", (cx, SCREEN_H - 40), (120, 255, 120), anchor="center")
        else:
            self.text(S, self.font_small, "Keyboard players: Arrows + Enter (Backspace = back) or WASD + Space (Q = back)  ·  F11 fullscreen",
                      (cx, SCREEN_H - 46), (210, 210, 210), anchor="center")
            self.text(S, self.font_small, "Quit game: Select / View button  or  Esc", (cx, SCREEN_H - 20), (255, 190, 190), anchor="center")

    def settings_rows(self):
        max_ai = MAX_RACERS - len(self.players)
        return [
            ("Computer racers", f"{self.ai_count}", f"0 - {max_ai}"),
            ("Computer difficulty", DIFFICULTIES[self.ai_difficulty], "Easy / Medium / Hard"),
            ("Laps", f"{self.laps}", "1 - 5"),
            ("Music", "On" if self.audio.music_on else "Off", "On / Off"),
            ("Sound effects", "On" if self.audio.sfx_on else "Off", "On / Off"),
        ]

    def draw_settings(self):
        self.draw_menu_background()
        self.overlay(self.screen, 180)
        S = self.screen
        cx = SCREEN_W / 2
        self.text(S, self.font_big, "Race settings", (cx, 80), (255, 210, 60), anchor="center")
        for i, (label, value, hint) in enumerate(self.settings_rows()):
            rect = pygame.Rect(0, 0, 760, 74)
            rect.center = (cx, 180 + i * 84)
            selected = i == self.settings_row
            rounded_panel(S, rect, (110, 180, 255, 225) if selected else (255, 255, 255, 45),
                          (255, 255, 255) if selected else INK, 5 if selected else 3, 20)
            self.text(S, self.font_med, label, (rect.left + 30, rect.centery), anchor="midleft")
            self.text(S, self.font_med, f"<  {value}  >" if selected else value, (rect.right - 130, rect.centery), (255, 255, 120), anchor="center")
            if selected:
                self.text(S, self.font_small, hint, (rect.right - 130, rect.bottom - 12), (230, 230, 230), anchor="center")
        total = len(self.players) + self.ai_count
        y = 595
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

    def draw_quit_confirm(self):
        self.overlay(self.screen, 200)
        cx, cy = SCREEN_W / 2, SCREEN_H / 2
        rounded_panel(self.screen, (cx - 330, cy - 150, 660, 300), (60, 30, 90, 240), INK, 5, 26)
        self.text(self.screen, self.font_big, f"Quit {self.title}?", (cx, cy - 70), (255, 210, 60), anchor="center")
        self.text(self.screen, self.font_med, "A / Enter  -  yes, quit", (cx, cy + 20), (255, 180, 180), anchor="center")
        self.text(self.screen, self.font_med, "B / Esc  -  keep playing", (cx, cy + 80), (180, 255, 180), anchor="center")

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
        self.overlay(self.screen, 228)
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
                if "join" in f.pressed and len(self.players) < MAX_HUMANS:
                    slot = min(set(range(MAX_HUMANS)) - {p.slot for p in self.players})
                    taken = {p.char_index for p in self.players}
                    default = next(i for i in [0, 1, 2, 7, 3, 9, 4, 10, 5, 11, 6, 8] if i not in taken)
                    new_player = Player(slot, device, default)
                    new_player.little = default == LITTLE_DEFAULT_CHARACTER
                    self.players.append(new_player)
                    self.players.sort(key=lambda p: p.slot)
                    self.input.rumble(device, 0.4, 0.4, 150)
                    self.sfx("join")
                continue
            if player.ready:
                if "back" in f.pressed:
                    player.ready = False
                    self.sfx("back")
                elif "confirm" in f.pressed and all(p.ready for p in self.players):
                    self.sfx("select")
                    self.enter_settings()
                    return
                continue
            n = len(self.roster)
            if "left" in f.pressed or "right" in f.pressed:
                player.char_index = (player.char_index + (1 if "right" in f.pressed else -1)) % n
                self.sfx("move")
                if player.char_index == LITTLE_DEFAULT_CHARACTER:
                    player.little = True  # the little sister's racer starts in Little Racer
            elif "mode" in f.pressed:
                player.little = not player.little
                self.input.rumble(device, 0.2, 0.2, 80)
                self.sfx("tick")
            elif "confirm" in f.pressed:
                player.ready = True
                self.input.rumble(device, 0.3, 0.6, 120)
                self.sfx("select")
            elif "back" in f.pressed:
                self.players.remove(player)
                self.sfx("back")

    def enter_settings(self):
        self.state = "settings"
        self.settings_row = 0
        max_ai = MAX_RACERS - len(self.players)
        if not self.settings_touched:
            self.ai_count = max(0, 4 - len(self.players))
            self.ai_difficulty = 0
            self.laps = 2 if all(p.little for p in self.players) else 3
        self.ai_count = min(self.ai_count, max_ai)

    def update_settings(self, pressed):
        rows = len(self.settings_rows())
        if "up" in pressed:
            self.settings_row = (self.settings_row - 1) % rows
            self.sfx("move")
        elif "down" in pressed:
            self.settings_row = (self.settings_row + 1) % rows
            self.sfx("move")
        elif "left" in pressed or "right" in pressed:
            d = 1 if "right" in pressed else -1
            if self.settings_row == 0:
                self.settings_touched = True
                self.ai_count = max(0, min(MAX_RACERS - len(self.players), self.ai_count + d))
            elif self.settings_row == 1:
                self.settings_touched = True
                self.ai_difficulty = max(0, min(2, self.ai_difficulty + d))
            elif self.settings_row == 2:
                self.settings_touched = True
                self.laps = max(1, min(5, self.laps + d))
            elif self.settings_row == 3:
                self.audio.set_music(not self.audio.music_on)
                self._save_audio_settings()
            else:
                self.audio.set_sfx(not self.audio.sfx_on)
                self._save_audio_settings()
            self.sfx("tick")
        elif "confirm" in pressed:
            self.sfx("go")
            self.new_race()
            self.state = "race"
        elif "back" in pressed:
            self.sfx("back")
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
                try:
                    pygame.display.toggle_fullscreen()
                except pygame.error:
                    pass
                if self.r3d:
                    self.r3d.resize(pygame.display.get_window_size())
            elif event.type in (pygame.VIDEORESIZE, getattr(pygame, "WINDOWSIZECHANGED", -1)) and self.r3d:
                self.r3d.resize(pygame.display.get_window_size())
            self.input.handle_event(event)
        self.rebind_unplugged()
        frames = self.input.poll()
        # Menus outside the lobby can be driven by any joined player (or the keyboard).
        menu_devices = {p.device for p in self.players} | {"kb_arrows", "kb_wasd"}
        pressed = set().union(*(f.pressed for d, f in frames.items() if d in menu_devices))

        if self.state == "lobby":
            anyone = set().union(*(f.pressed for f in frames.values()))  # any controller, joined or not
            keyboard_esc = "pause" in frames["kb_arrows"].pressed
            if "quit" in anyone or keyboard_esc:
                self.state = "quit_confirm"  # Select / View button, or Esc / X on the keyboard
                self.sfx("pause")
            else:
                self.update_lobby(frames)
        elif self.state == "quit_confirm":
            anyone = set().union(*(f.pressed for f in frames.values()))
            if "confirm" in anyone:
                self.running = False
            elif anyone & {"back", "pause", "quit"}:
                self.state = "lobby"
                self.sfx("back")
        elif self.state == "settings":
            self.update_settings(pressed)
        elif self.state == "race":
            if "pause" in pressed:
                self.state = "paused"
                self.sfx("pause")
            else:
                self.update_race(dt, frames)
        elif self.state == "paused":
            if "confirm" in pressed or "pause" in pressed:
                self.state = "race"
                self.sfx("select")
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

        menu = self.state in ("lobby", "settings", "quit_confirm")
        self.audio.music("menu" if menu else "race",
                         0.15 if self.state == "paused" else (0.3 if self.state == "results" else 0.45))
        if self.state in ("lobby", "quit_confirm"):
            self.draw_lobby()
            if self.state == "quit_confirm":
                self.draw_quit_confirm()
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
            self.present()
        pygame.quit()


def main(three_d=False):
    """Kart Rush (top-down) by default; kart_rush_3d.py starts Kart Rush 3D."""
    title = "Kart Rush 3D" if three_d else "Kart Rush"
    parser = argparse.ArgumentParser(description=title)
    parser.add_argument("--fullscreen", action="store_true", help="start in fullscreen (used by the Steam launcher)")
    if three_d:
        parser.add_argument("--2d", dest="flat", action="store_true", help="use the top-down view (if 3D misbehaves)")
    args = parser.parse_args()
    Game(fullscreen=args.fullscreen, mode3d=three_d and not args.flat, title=title).run()


if __name__ == "__main__":
    main(three_d=False)
