"""Generate Steam library artwork and an icon for Kart Rush.

    python make_art.py OUTPUT_DIR

Writes, in Steam's custom-artwork sizes:
    capsule.png  600x900    (library grid cover)
    wide.png     920x430    (wide capsule / "recent games")
    hero.png     1920x620   (banner at the top of the game's page)
    logo.png     1280x400   (transparent logo drawn over the hero)
    icon.png     256x256    (desktop / Steam icon)
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cartoon import load_font  # noqa: E402
from characters import load_roster  # noqa: E402
from kart_racer import Track  # noqa: E402

TITLE = "KART RUSH"
GOLD = (255, 210, 60)


def outlined_text(surf, text, size, center, color=GOLD, outline=(60, 20, 70)):
    font = load_font(size)
    w = max(3, size // 22)
    base = font.render(text, True, outline)
    for dx in range(-w, w + 1, max(1, w // 2)):
        for dy in range(-w, w + 1, max(1, w // 2)):
            surf.blit(base, base.get_rect(center=(center[0] + dx, center[1] + dy)))
    img = font.render(text, True, color)
    surf.blit(img, img.get_rect(center=center))


def background(track, size, focus=(420, 1250)):
    """A crop of the real track, scaled to fill `size`."""
    w, h = size
    src_w = min(track.surface.get_width(), max(w, int(h * 1.6)))
    src_h = int(src_w * h / w)
    x = max(0, min(track.surface.get_width() - src_w, focus[0] - src_w // 2))
    y = max(0, min(track.surface.get_height() - src_h, focus[1] - src_h // 2))
    crop = track.surface.subsurface(pygame.Rect(x, y, src_w, min(src_h, track.surface.get_height() - y))).copy()
    return pygame.transform.smoothscale(crop, (w, h))


def tint(surf, alpha):
    shade = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    shade.fill((40, 10, 60, alpha))
    surf.blit(shade, (0, 0))


def avatars(surf, roster, picks, row_center, size):
    gap = size * 0.95
    left = row_center[0] - gap * (len(picks) - 1) / 2
    for i, idx in enumerate(picks):
        img = pygame.transform.smoothscale(roster[idx].avatar_full, (size, size))
        bob = (i % 2) * size * 0.12
        surf.blit(img, img.get_rect(center=(left + i * gap, row_center[1] + bob)))


def main(out_dir):
    pygame.init()
    pygame.display.set_mode((1, 1))
    os.makedirs(out_dir, exist_ok=True)
    track = Track()
    roster = load_roster()

    cap = background(track, (600, 900))
    tint(cap, 90)
    outlined_text(cap, "KART", 200, (300, 150))
    outlined_text(cap, "RUSH", 200, (300, 300))
    avatars(cap, roster, [0, 1], (300, 520), 230)
    avatars(cap, roster, [2, 9, 11], (300, 760), 150)
    pygame.image.save(cap, os.path.join(out_dir, "capsule.png"))

    wide = background(track, (920, 430))
    tint(wide, 80)
    outlined_text(wide, TITLE, 150, (460, 100))
    avatars(wide, roster, [2, 0, 1, 9, 11], (460, 290), 170)
    pygame.image.save(wide, os.path.join(out_dir, "wide.png"))

    hero = background(track, (1920, 620), focus=(1600, 1200))
    tint(hero, 40)
    avatars(hero, roster, [3, 4, 7, 10], (1450, 330), 220)
    pygame.image.save(hero, os.path.join(out_dir, "hero.png"))

    logo = pygame.Surface((1280, 400), pygame.SRCALPHA)
    outlined_text(logo, TITLE, 260, (640, 200))
    pygame.image.save(logo, os.path.join(out_dir, "logo.png"))

    icon = pygame.Surface((256, 256), pygame.SRCALPHA)
    pygame.draw.rect(icon, (255, 150, 200), icon.get_rect(), border_radius=48)
    pygame.draw.rect(icon, (120, 40, 110), icon.get_rect(), 8, border_radius=48)
    icon.blit(pygame.transform.smoothscale(roster[0].kart, (190, 129)), (33, 110))
    icon.blit(pygame.transform.smoothscale(roster[0].avatar_full, (150, 150)), (53, 6))
    pygame.image.save(icon, os.path.join(out_dir, "icon.png"))
    print(f"Artwork written to {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "steam_art")
