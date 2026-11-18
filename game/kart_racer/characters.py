"""Racer roster for Kart Rush.

Every character is drawn in code (no image files), so they stay crisp at any
size. Each one has an `avatar` (a big friendly face drawn above the kart and
shown on the select screen) and kart colours.
"""

import math
import random

import pygame

# Names for the two family racers. Change these to your kids' names
# (only on your own computer if this repository is public).
SISTER_NAME = "Little Sis"
BROTHER_NAME = "Big Bro"

CANVAS = 120


def _canvas():
    return pygame.Surface((CANVAS, CANVAS), pygame.SRCALPHA)


def _eyes(s, cx, cy, gap, r=8, lashes=False, look=(1, 1), iris=None):
    for ex in (cx - gap, cx + gap):
        pygame.draw.ellipse(s, (255, 255, 255), (ex - r, cy - r * 1.2, r * 2, r * 2.4))
        if iris is not None:
            pygame.draw.ellipse(s, iris, (ex - r * 0.8 + look[0], cy - r * 0.95 + look[1], r * 1.6, r * 2.0))
        pygame.draw.ellipse(s, (30, 25, 45), (ex - r * 0.65 + look[0], cy - r * 0.8 + look[1], r * 1.3, r * 1.7)
                            if iris is None else (ex - r * 0.4 + look[0], cy - r * 0.5 + look[1], r * 0.8, r * 1.0))
        pygame.draw.circle(s, (255, 255, 255), (ex - r * 0.2 + look[0], cy - r * 0.4 + look[1]), max(2, r // 3))
        if lashes:
            side = -1 if ex < cx else 1
            for k in range(3):
                x0 = ex + side * r * (0.55 + 0.2 * k)
                y0 = cy - r * 1.0 + k * 4
                pygame.draw.line(s, (30, 25, 45), (x0, y0), (x0 + side * 5, y0 - 3), 2)


def _smile(s, cx, cy, w=16, color=(120, 30, 50), width=3):
    pygame.draw.arc(s, color, (cx - w / 2, cy - w / 3, w, w * 0.7), math.pi * 1.1, math.pi * 1.9, width)


def _cheeks(s, cx, cy, gap, color=(255, 140, 170, 140)):
    blush = pygame.Surface((CANVAS, CANVAS), pygame.SRCALPHA)
    for x in (cx - gap, cx + gap):
        pygame.draw.ellipse(blush, color, (x - 7, cy - 4, 14, 8))
    s.blit(blush, (0, 0))


def _star(s, cx, cy, r, color):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    pygame.draw.polygon(s, color, pts)


# --- Magical & sweet -----------------------------------------------------------
def draw_unicorn():
    s = _canvas()
    for i, c in enumerate([(255, 110, 170), (255, 190, 80), (120, 210, 255), (180, 130, 255)]):
        pygame.draw.circle(s, c, (30 - i * 2, 40 + i * 16), 17)
        pygame.draw.circle(s, c, (90 + i * 2, 40 + i * 16), 13)
    for ex in (38, 82):
        pygame.draw.polygon(s, (255, 255, 255), [(ex - 10, 40), (ex + 10, 40), (ex, 18)])
        pygame.draw.polygon(s, (255, 170, 200), [(ex - 5, 38), (ex + 5, 38), (ex, 26)])
    pygame.draw.circle(s, (255, 255, 255), (60, 64), 34)
    pygame.draw.ellipse(s, (255, 215, 230), (36, 76, 48, 28))
    pygame.draw.polygon(s, (255, 205, 60), [(52, 34), (68, 34), (60, 2)])
    for k in range(3):
        pygame.draw.line(s, (230, 150, 30), (54 + k, 28 - k * 8), (66 - k, 24 - k * 8), 2)
    _eyes(s, 60, 60, 14, 8, lashes=True)
    _cheeks(s, 60, 74, 22)
    pygame.draw.circle(s, (220, 120, 150), (52, 90), 2)
    pygame.draw.circle(s, (220, 120, 150), (68, 90), 2)
    _smile(s, 60, 96, 14)
    _star(s, 96, 22, 9, (255, 230, 90))
    return s


def draw_mermaid():
    s = _canvas()
    pygame.draw.polygon(s, (40, 200, 190), [(60, 100), (34, 118), (58, 110)])
    pygame.draw.polygon(s, (40, 200, 190), [(60, 100), (86, 118), (62, 110)])
    for x, y, r in [(60, 56, 44), (24, 84, 18), (96, 84, 18), (30, 100, 13), (90, 100, 13)]:
        pygame.draw.circle(s, (190, 60, 140), (x, y), r)
    pygame.draw.circle(s, (255, 214, 180), (60, 64), 30)
    for x in (40, 52, 64, 78):
        pygame.draw.circle(s, (190, 60, 140), (x, 38), 13)
    # Seashell hair clip
    pygame.draw.polygon(s, (255, 170, 200), [(82, 30), (100, 18), (104, 40)])
    for k in range(3):
        pygame.draw.line(s, (220, 110, 160), (84, 31), (100 + k * 2, 22 + k * 8), 2)
    _eyes(s, 60, 64, 12, 8, lashes=True)
    _cheeks(s, 60, 78, 19)
    _smile(s, 60, 86, 14)
    for bx, by, br in [(16, 22, 5), (24, 10, 3), (104, 62, 4)]:
        pygame.draw.circle(s, (170, 230, 255), (bx, by), br, 2)
    return s


def draw_donut():
    s = _canvas()
    pygame.draw.circle(s, (220, 160, 90), (60, 62), 50)
    for i in range(12):
        a = i * math.pi / 6
        pygame.draw.circle(s, (255, 130, 190), (60 + math.cos(a) * 34, 62 + math.sin(a) * 34), 14)
    pygame.draw.circle(s, (255, 130, 190), (60, 62), 38)
    pygame.draw.circle(s, (220, 160, 90), (60, 44), 13)
    pygame.draw.circle(s, (0, 0, 0, 0), (60, 44), 9)
    rng = random.Random(3)
    for _ in range(22):
        a, d = rng.uniform(0, 2 * math.pi), rng.uniform(22, 40)
        x, y = 60 + math.cos(a) * d, 62 + math.sin(a) * d
        if 50 < y < 100 and 36 < x < 84:
            continue
        b = rng.uniform(0, math.pi)
        c = rng.choice([(255, 255, 255), (90, 200, 255), (255, 230, 60), (140, 230, 120)])
        pygame.draw.line(s, c, (x, y), (x + math.cos(b) * 6, y + math.sin(b) * 6), 3)
    _eyes(s, 60, 70, 13, 7)
    _cheeks(s, 60, 82, 20)
    _smile(s, 60, 88, 14)
    return s


def draw_lollipop():
    s = _canvas()
    pygame.draw.rect(s, (245, 245, 245), (56, 80, 8, 40), border_radius=3)
    colors = [(255, 90, 140), (255, 255, 255), (120, 200, 255), (255, 255, 255), (255, 210, 70), (255, 255, 255)]
    for i in range(12):
        a0, a1 = i * math.pi / 6, (i + 1) * math.pi / 6
        pts = [(60, 52)] + [(60 + math.cos(a0 + (a1 - a0) * t / 4 + 0.6) * 44,
                             52 + math.sin(a0 + (a1 - a0) * t / 4 + 0.6) * 44) for t in range(5)]
        pygame.draw.polygon(s, colors[i % len(colors)], pts)
    pygame.draw.circle(s, (230, 70, 120), (60, 52), 44, 3)
    pygame.draw.circle(s, (255, 240, 245), (60, 58), 22)
    _eyes(s, 60, 54, 9, 6, lashes=True)
    _smile(s, 60, 68, 11)
    pygame.draw.rect(s, (255, 90, 140), (40, 84, 40, 10), border_radius=4)  # ribbon
    pygame.draw.polygon(s, (255, 90, 140), [(40, 89), (26, 80), (26, 98)])
    pygame.draw.polygon(s, (255, 90, 140), [(80, 89), (94, 80), (94, 98)])
    return s


def draw_cupcake():
    s = _canvas()
    pygame.draw.polygon(s, (120, 200, 255), [(26, 64), (94, 64), (84, 114), (36, 114)])
    for k in range(6):
        x = 32 + k * 11
        pygame.draw.line(s, (80, 160, 230), (x, 66), (x + 3 - k, 112), 3)
    for x, y, r in [(30, 60, 16), (50, 52, 20), (72, 52, 20), (90, 60, 16), (60, 36, 20), (60, 64, 26)]:
        pygame.draw.circle(s, (255, 200, 225), (x, y), r)
    pygame.draw.circle(s, (230, 30, 60), (60, 14), 10)
    pygame.draw.line(s, (90, 160, 60), (60, 6), (68, -2), 3)
    pygame.draw.circle(s, (255, 255, 255), (57, 11), 3)
    rng = random.Random(5)
    for _ in range(14):
        x, y = rng.uniform(32, 88), rng.uniform(32, 60)
        pygame.draw.circle(s, rng.choice([(255, 90, 140), (255, 230, 60), (140, 230, 120), (150, 120, 255)]), (x, y), 2)
    _eyes(s, 60, 82, 13, 7)
    _cheeks(s, 60, 94, 21)
    _smile(s, 60, 100, 14)
    return s


# --- Action ----------------------------------------------------------------------
def draw_fire_creature():
    s = _canvas()
    for c, w, h in [((230, 50, 30), 34, 50), ((255, 140, 30), 24, 38), ((255, 220, 70), 12, 24)]:
        pygame.draw.polygon(s, c, [(60 - w / 2, 40), (60, 40 - h), (60 + w / 2, 40), (60, 50)])
    pygame.draw.polygon(s, (240, 110, 40), [(30, 50), (24, 24), (44, 40)])
    pygame.draw.polygon(s, (240, 110, 40), [(90, 50), (96, 24), (76, 40)])
    pygame.draw.circle(s, (255, 130, 40), (60, 70), 38)
    pygame.draw.ellipse(s, (255, 225, 160), (38, 74, 44, 36))
    _eyes(s, 60, 62, 14, 9, look=(2, 1))
    pygame.draw.line(s, (120, 40, 20), (37, 46), (55, 51), 4)  # determined brows
    pygame.draw.line(s, (120, 40, 20), (83, 46), (65, 51), 4)
    pygame.draw.arc(s, (120, 30, 20), (46, 78, 28, 18), math.pi * 1.05, math.pi * 1.95, 4)
    pygame.draw.polygon(s, (255, 255, 255), [(52, 88), (56, 88), (54, 94)])
    pygame.draw.polygon(s, (255, 255, 255), [(64, 88), (68, 88), (66, 94)])
    return s


def draw_water_creature():
    s = _canvas()
    pygame.draw.polygon(s, (60, 150, 255), [(60, 4), (26, 62), (94, 62)])
    pygame.draw.circle(s, (60, 150, 255), (60, 74), 38)
    pygame.draw.polygon(s, (30, 100, 220), [(60, 10), (76, 30), (62, 34)])
    pygame.draw.ellipse(s, (190, 230, 255), (40, 76, 40, 32))
    pygame.draw.ellipse(s, (210, 240, 255), (36, 46, 12, 20))
    _eyes(s, 60, 68, 14, 9, look=(1, 1))
    pygame.draw.ellipse(s, (20, 50, 120), (51, 86, 18, 12))
    pygame.draw.rect(s, (60, 150, 255), (51, 84, 18, 6))
    pygame.draw.ellipse(s, (255, 130, 150), (55, 91, 10, 6))
    for bx, by, br in [(14, 40, 6), (104, 30, 5), (100, 96, 7), (20, 96, 4)]:
        pygame.draw.circle(s, (150, 210, 255), (bx, by), br, 2)
    return s


def _ninja(main, dark, emblem):
    s = _canvas()
    pygame.draw.rect(s, (170, 170, 175), (50, 8, 20, 12), border_radius=3)  # stud on top of the block head
    pygame.draw.rect(s, (200, 200, 205), (52, 8, 16, 4), border_radius=2)
    pygame.draw.rect(s, main, (22, 18, 76, 82), border_radius=14)
    pygame.draw.rect(s, dark, (22, 18, 76, 82), 4, border_radius=14)
    pygame.draw.rect(s, (40, 35, 40), (28, 46, 64, 24), border_radius=8)
    for ex in (46, 74):
        pygame.draw.ellipse(s, (255, 255, 255), (ex - 9, 50, 18, 16))
        pygame.draw.ellipse(s, (20, 20, 20), (ex - 4, 53, 9, 11))
        pygame.draw.circle(s, (255, 255, 255), (ex - 1, 56), 2)
    pygame.draw.line(s, (40, 35, 40), (36, 48), (54, 52), 4)  # brave brows
    pygame.draw.line(s, (40, 35, 40), (84, 48), (66, 52), 4)
    _star(s, 60, 32, 9, emblem)
    pygame.draw.polygon(s, main, [(96, 70), (116, 60), (112, 84)])  # mask knot tails
    pygame.draw.polygon(s, dark, [(96, 78), (118, 88), (106, 98)])
    return s


def draw_ember_ninja():
    return _ninja((220, 40, 40), (150, 20, 20), (255, 200, 40))


def draw_jade_ninja():
    return _ninja((40, 180, 80), (20, 110, 50), (220, 240, 120))


def draw_hot_rod():
    s = _canvas()
    pygame.draw.rect(s, (200, 200, 210), (4, 60, 22, 6), border_radius=3)  # exhaust
    pygame.draw.polygon(s, (220, 30, 40), [(10, 76), (20, 50), (54, 46), (70, 30), (92, 32), (100, 54), (116, 62), (116, 82), (10, 86)])
    pygame.draw.polygon(s, (170, 230, 255), [(60, 48), (72, 34), (88, 36), (92, 50)])
    for c, off in [((255, 220, 40), 0), ((255, 140, 30), 4)]:
        pygame.draw.polygon(s, c, [(74 - off, 62), (60, 56 + off), (54, 64), (42, 58 + off), (36, 68), (24, 64), (30, 76), (74 - off, 78)])
    for wx, r in ((32, 18), (96, 14)):
        pygame.draw.circle(s, (30, 30, 30), (wx, 88), r)
        pygame.draw.circle(s, (210, 210, 220), (wx, 88), r // 2)
    pygame.draw.circle(s, (255, 250, 200), (113, 68), 4)
    _eyes(s, 80, 50, 6, 5, look=(2, 0))  # cartoon eyes in the windscreen
    return s


# --- Family racers (drawn from a photo: no image is stored) -------------------------
HAIR = (55, 35, 25)
HAIR_LIGHT = (90, 60, 40)
SKIN = (232, 190, 155)
SKIN_SHADE = (215, 165, 130)
BROWN_EYES = (110, 70, 40)


def draw_sister():
    """Dark curly pigtail buns, a fringe and a pink dress."""
    s = _canvas()
    # Curly ringlets hanging from the pigtails
    for side in (-1, 1):
        bx = 60 + side * 34
        for k in range(4):
            pygame.draw.circle(s, HAIR, (bx + side * (k % 2) * 4, 34 + k * 11), 7)
            pygame.draw.circle(s, HAIR_LIGHT, (bx + side * (k % 2) * 4 - 2, 32 + k * 11), 2)
    pygame.draw.circle(s, HAIR, (60, 58), 38)                   # hair behind the head
    for side in (-1, 1):                                       # the two buns
        pygame.draw.circle(s, HAIR, (60 + side * 32, 22), 15)
        pygame.draw.circle(s, HAIR_LIGHT, (60 + side * 32 - 4, 17), 5)
        pygame.draw.circle(s, (255, 150, 190), (60 + side * 22, 30), 5)   # pink hair ties
    # Pink dress at the bottom
    pygame.draw.ellipse(s, (255, 190, 210), (24, 94, 72, 40))
    pygame.draw.rect(s, SKIN, (52, 88, 16, 10))                 # neck
    pygame.draw.circle(s, SKIN, (60, 64), 29)                   # face
    pygame.draw.circle(s, SKIN, (31, 66), 6)                    # ears
    pygame.draw.circle(s, SKIN, (89, 66), 6)
    # Fringe
    pygame.draw.ellipse(s, HAIR, (30, 32, 60, 26))
    for x in (38, 48, 58, 68, 78):
        pygame.draw.polygon(s, HAIR, [(x - 7, 48), (x + 7, 48), (x + 1, 58)])
    _eyes(s, 60, 66, 12, 7, lashes=True, iris=BROWN_EYES)
    _cheeks(s, 60, 78, 18)
    pygame.draw.arc(s, (170, 70, 80), (51, 76, 18, 12), math.pi * 1.1, math.pi * 1.9, 3)
    _star(s, 100, 100, 8, (255, 160, 200))
    return s


def draw_brother():
    """Short dark hair, a few freckles and a navy button-up shirt."""
    s = _canvas()
    # Navy shirt with a collar and buttons
    pygame.draw.ellipse(s, (40, 50, 80), (18, 92, 84, 50))
    pygame.draw.rect(s, SKIN_SHADE, (52, 86, 16, 12))           # neck
    pygame.draw.polygon(s, (55, 68, 105), [(46, 92), (60, 104), (52, 110), (38, 98)])   # collar
    pygame.draw.polygon(s, (55, 68, 105), [(74, 92), (60, 104), (68, 110), (82, 98)])
    for y in (108, 118):
        pygame.draw.circle(s, (150, 130, 100), (60, y), 2)
    pygame.draw.circle(s, SKIN, (29, 60), 7)                    # ears
    pygame.draw.circle(s, SKIN, (91, 60), 7)
    pygame.draw.ellipse(s, SKIN, (30, 26, 60, 66))              # face
    # Short hair
    pygame.draw.ellipse(s, HAIR, (30, 16, 60, 30))
    pygame.draw.rect(s, HAIR, (30, 30, 6, 10), border_radius=3)
    pygame.draw.rect(s, HAIR, (84, 30, 6, 10), border_radius=3)
    for x in (40, 50, 60, 70, 80):                              # short soft fringe
        pygame.draw.polygon(s, HAIR, [(x - 7, 34), (x + 6, 34), (x - 2, 41)])
    for x, y in ((42, 22), (56, 19), (70, 21), (50, 27), (64, 26)):
        pygame.draw.circle(s, HAIR_LIGHT, (x, y), 2)
    pygame.draw.line(s, HAIR, (40, 49), (52, 48), 3)            # eyebrows
    pygame.draw.line(s, HAIR, (68, 48), (80, 49), 3)
    _eyes(s, 60, 58, 12, 7, iris=BROWN_EYES)
    for x, y in ((44, 70), (48, 73), (41, 74), (76, 70), (72, 73), (79, 74)):   # freckles
        pygame.draw.circle(s, (190, 135, 100), (x, y), 1)
    pygame.draw.arc(s, (150, 70, 60), (48, 72, 24, 14), math.pi * 1.1, math.pi * 1.9, 3)
    return s


ROSTER = [
    (SISTER_NAME, draw_sister,         (255, 170, 205), (255, 255, 255), [(255, 160, 200), (200, 150, 255), (255, 255, 255)], "rider"),
    (BROTHER_NAME, draw_brother,       (40, 55, 95),    (235, 220, 190), [(120, 160, 255), (255, 255, 255)],             "rider"),
    # name,      avatar fn,           kart body,        accent,           trail colours,                               style
    ("Sparkle",  draw_unicorn,        (255, 150, 200), (255, 255, 255), [(255, 110, 170), (255, 200, 80), (120, 210, 255), (180, 130, 255)], "rider"),
    ("Coral",    draw_mermaid,        (40, 200, 190),  (190, 60, 140),  [(120, 230, 255), (255, 255, 255)],             "rider"),
    ("Sprinkles", draw_donut,         (255, 130, 190), (220, 160, 90),  [(255, 255, 255), (90, 200, 255), (255, 230, 60)], "rider"),
    ("Swirly",   draw_lollipop,       (255, 90, 140),  (120, 200, 255), [(255, 90, 140), (255, 210, 70), (120, 200, 255)], "rider"),
    ("Cupcake",  draw_cupcake,        (120, 200, 255), (255, 200, 225), [(255, 200, 225), (255, 255, 255)],             "rider"),
    ("Blaze",    draw_fire_creature,  (255, 120, 30),  (230, 50, 30),   [(255, 80, 30), (255, 200, 50)],                "rider"),
    ("Droplet",  draw_water_creature, (60, 150, 255),  (190, 230, 255), [(150, 210, 255), (255, 255, 255)],             "rider"),
    ("Ember Ninja", draw_ember_ninja, (60, 60, 70),    (220, 40, 40),   [(255, 80, 60), (255, 200, 40)],                "rider"),
    ("Jade Ninja", draw_jade_ninja,  (60, 60, 70),    (40, 180, 80),   [(120, 255, 140), (220, 240, 120)],             "rider"),
    ("Flame Rod", draw_hot_rod,      (220, 30, 40),   (255, 200, 40),  [(255, 220, 40), (255, 120, 30)],               "hotrod"),
]


class Character:
    def __init__(self, name, avatar_fn, body, accent, trail, style):
        self.name = name
        self.body = body
        self.accent = accent
        self.trail = trail
        self.style = style
        self.avatar_full = avatar_fn()
        self.avatar_race = pygame.transform.smoothscale(self.avatar_full, (50, 50))
        self.kart = self._kart_sprite()

    def _kart_sprite(self):
        """Top-down kart pointing right (rotated in game)."""
        if self.style == "hotrod":
            s = pygame.Surface((64, 34), pygame.SRCALPHA)
            for wx, wy, w in ((6, 0, 14), (6, 26, 14), (44, 2, 10), (44, 26, 10)):
                pygame.draw.rect(s, (25, 25, 25), (wx, wy, w, 8), border_radius=2)
            pygame.draw.polygon(s, self.body, [(2, 8), (40, 6), (62, 11), (62, 23), (40, 28), (2, 26)])
            for c, off in ((self.accent, 0), ((255, 130, 30), 5)):
                pygame.draw.polygon(s, c, [(58 - off, 17), (46, 9 + off / 2), (42, 13), (32, 8 + off / 2), (28, 14), (18, 12),
                                           (24, 17), (18, 22), (28, 20), (32, 26 - off / 2), (42, 21), (46, 25 - off / 2)])
            pygame.draw.rect(s, (170, 230, 255), (14, 10, 12, 14), border_radius=3)
            pygame.draw.rect(s, (200, 200, 210), (0, 12, 6, 3))
            pygame.draw.rect(s, (200, 200, 210), (0, 19, 6, 3))
            return s
        s = pygame.Surface((56, 38), pygame.SRCALPHA)
        for wx, wy in ((6, 1), (38, 1), (6, 29), (38, 29)):
            pygame.draw.rect(s, (25, 25, 25), (wx, wy, 13, 8), border_radius=3)
        pygame.draw.rect(s, self.body, (3, 7, 50, 24), border_radius=9)
        pygame.draw.rect(s, self.accent, (3, 16, 50, 6))
        pygame.draw.polygon(s, self.accent, [(42, 9), (55, 19), (42, 29)])
        pygame.draw.rect(s, tuple(max(0, c - 50) for c in self.body), (3, 7, 50, 24), 2, border_radius=9)
        return s


def load_roster():
    return [Character(*row) for row in ROSTER]
