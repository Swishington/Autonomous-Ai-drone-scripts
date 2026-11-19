"""Cartoon rendering helpers: smooth supersampled shapes, sticker outlines,
soft shading, blurred drop shadows and outlined text.

Characters and props are drawn with `draw.*` (same arguments as pygame.draw)
onto a `Canvas`, which secretly works at several times the size. `finish()`
then shades it, wraps it in a thick outline and scales it down, which gives
smooth, bold, modern-cartoon sprites without any image files.
"""

import math
import os

import pygame

INK = (38, 24, 48)  # outline colour: a warm near-black
FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts", "LilitaOne-Regular.ttf")


class Canvas:
    """A drawing surface in logical units that is really `k` times bigger."""

    def __init__(self, w, h, k=4):
        self.w, self.h, self.k = w, h, k
        self.surface = pygame.Surface((w * k, h * k), pygame.SRCALPHA)

    def get_size(self):
        return self.w, self.h

    def blit(self, src, pos):
        k = self.k
        self.surface.blit(src.surface if isinstance(src, Canvas) else src, (pos[0] * k, pos[1] * k))


def _scale_rect(r, k):
    r = pygame.Rect(r) if not isinstance(r, (tuple, list)) else r
    x, y, w, h = r
    return pygame.Rect(round(x * k), round(y * k), max(1, round(w * k)), max(1, round(h * k)))


class _Draw:
    """Drop-in for pygame.draw that understands Canvas."""

    @staticmethod
    def _target(surf):
        return (surf.surface, surf.k) if isinstance(surf, Canvas) else (surf, 1)

    def circle(self, surf, color, center, radius, width=0):
        s, k = self._target(surf)
        return pygame.draw.circle(s, color, (center[0] * k, center[1] * k), max(1, radius * k), round(width * k))

    def ellipse(self, surf, color, rect, width=0):
        s, k = self._target(surf)
        return pygame.draw.ellipse(s, color, _scale_rect(rect, k), round(width * k))

    def polygon(self, surf, color, points, width=0):
        s, k = self._target(surf)
        return pygame.draw.polygon(s, color, [(x * k, y * k) for x, y in points], round(width * k))

    def rect(self, surf, color, rect, width=0, border_radius=0):
        s, k = self._target(surf)
        return pygame.draw.rect(s, color, _scale_rect(rect, k), round(width * k), border_radius=round(border_radius * k))

    def line(self, surf, color, start, end, width=1):
        s, k = self._target(surf)
        w = max(1, round(width * k))
        a, b = (start[0] * k, start[1] * k), (end[0] * k, end[1] * k)
        pygame.draw.line(s, color, a, b, w)
        if w > 2:  # round caps
            pygame.draw.circle(s, color, a, w / 2)
            pygame.draw.circle(s, color, b, w / 2)

    def arc(self, surf, color, rect, start, stop, width=1):
        """Thick arcs drawn as a chain of round-capped segments (pygame's thick arcs have holes)."""
        r = pygame.Rect(rect) if not isinstance(rect, (tuple, list)) else pygame.Rect(*rect)
        cx, cy, rx, ry = r.centerx, r.centery, r.width / 2, r.height / 2
        steps = 14
        pts = [(cx + math.cos(start + (stop - start) * i / steps) * rx,
                cy - math.sin(start + (stop - start) * i / steps) * ry) for i in range(steps + 1)]
        for a, b in zip(pts, pts[1:]):
            self.line(surf, color, a, b, width)


draw = _Draw()


def shade(surface, top=(255, 255, 255), bottom=(196, 188, 214), highlight=36):
    """Soft top-lit volume: darken towards the bottom, add a little light at the top."""
    w, h = surface.get_size()
    col = pygame.Surface((1, 64))
    for y in range(64):
        t = y / 63
        col.set_at((0, y), [round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)])
    grad = pygame.transform.smoothscale(col, (w, h))
    surface.blit(grad, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    if highlight:
        glow = pygame.Surface((1, 64))
        for y in range(64):
            v = max(0, round(highlight * (1 - y / 22)))
            glow.set_at((0, y), (v, v, v))
        surface.blit(pygame.transform.smoothscale(glow, (w, h)), (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def outline(surface, thickness, color=INK):
    """Wrap a sprite in a solid outline (sticker style). Returns a bigger surface."""
    t = max(1, round(thickness))
    mask = pygame.mask.from_surface(surface, 100)
    sil = mask.to_surface(setcolor=(*color, 255), unsetcolor=(0, 0, 0, 0))
    w, h = surface.get_size()
    out = pygame.Surface((w + 2 * t, h + 2 * t), pygame.SRCALPHA)
    steps = max(12, t * 3)
    for i in range(steps):
        a = 2 * math.pi * i / steps
        out.blit(sil, (t + round(math.cos(a) * t), t + round(math.sin(a) * t)))
    for r in range(1, t):  # fill the inside of the ring so there are no gaps
        out.blit(sil, (t + r, t))
        out.blit(sil, (t - r, t))
        out.blit(sil, (t, t + r))
        out.blit(sil, (t, t - r))
    out.blit(surface, (t, t))
    return out


def finish(canvas, size, line=3.0, shaded=True):
    """Shade + outline a Canvas, then scale to `size` (w, h) in final pixels.

    `line` is the outline thickness in final pixels."""
    surf = canvas.surface.copy() if isinstance(canvas, Canvas) else canvas.copy()
    if shaded:
        shade(surf)
    w, h = size
    k = surf.get_width() / w
    surf = outline(surf, line * k)
    return pygame.transform.smoothscale(surf, (round(w + 2 * line), round(h + 2 * line)))


def blur(surface, amount=4):
    """Cheap blur: shrink and grow again (works on pygame and pygame-ce)."""
    w, h = surface.get_size()
    small = pygame.transform.smoothscale(surface, (max(1, w // amount), max(1, h // amount)))
    return pygame.transform.smoothscale(small, (w, h))


def soft_shadow(w, h, alpha=90):
    """A blurred ellipse for drop shadows."""
    pad = max(6, w // 4)
    s = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (20, 10, 40, alpha), (pad, pad, w, h))
    return blur(blur(s, 3), 2)


def load_font(size):
    """The chunky cartoon font, falling back to pygame's default if it's missing."""
    try:
        return pygame.font.Font(FONT_PATH, round(size * 0.78))
    except (OSError, FileNotFoundError, pygame.error):
        return pygame.font.Font(None, size)


class TextCache:
    """Outlined cartoon text, cached because rendering an outline costs several renders."""

    def __init__(self, limit=600):
        self.cache = {}
        self.limit = limit

    def render(self, font, text, color, outline_color=INK, thickness=None):
        key = (id(font), text, tuple(color), tuple(outline_color), thickness)
        img = self.cache.get(key)
        if img is None:
            t = thickness if thickness is not None else max(2, font.get_height() // 14)
            base = font.render(text, True, color)
            ink = font.render(text, True, outline_color)
            w, h = base.get_size()
            img = pygame.Surface((w + 2 * t, h + 2 * t + t), pygame.SRCALPHA)
            for dx, dy in ((0, t + t), (t, t + t), (-t, t + t)):  # chunky drop under the outline
                img.blit(ink, (t + dx, t + dy - t // 2))
            for i in range(12):
                a = 2 * math.pi * i / 12
                img.blit(ink, (t + round(math.cos(a) * t), t + round(math.sin(a) * t)))
            img.blit(base, (t, t))
            if len(self.cache) > self.limit:
                self.cache.clear()
            self.cache[key] = img
        return img


def rounded_panel(surf, rect, fill, border=INK, width=3, radius=14):
    """A rounded, outlined HUD/menu panel. `fill` may include alpha."""
    rect = pygame.Rect(rect)
    box = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(box, fill, box.get_rect(), border_radius=radius)
    if width:
        pygame.draw.rect(box, border, box.get_rect(), width, border_radius=radius)
    surf.blit(box, rect)
