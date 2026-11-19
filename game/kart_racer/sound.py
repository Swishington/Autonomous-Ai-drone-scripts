"""Music and sound effects for Kart Rush, all synthesised in code (no audio files).

The two music loops take a few seconds to compose, so they're rendered once
into ~/.cache/kart-rush/ and reused (the Bazzite installer pre-builds them).
Everything is optional: if the PC has no audio device the game stays silent.

    python sound.py            build the music cache (used by the installer)
    python sound.py --wav DIR  also write every sound effect to DIR as .wav
"""

import math
import os
import random
import struct
import sys
import wave
from array import array

import pygame

RATE = 22050
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "kart-rush")
MUSIC_VERSION = "1"
MASTER = 0.9

# ----------------------------------------------------------------------------
# Tiny synthesiser


def midi_hz(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def buffer(seconds):
    return array("f", bytes(4 * int(seconds * RATE)))


def env(i, n, attack=0.005, decay=0.08, sustain=0.6, release=0.05):
    """ADSR envelope value for sample i of an n-sample note."""
    t, length = i / RATE, n / RATE
    if t < attack:
        return t / attack
    if t > length - release:
        return max(0.0, sustain * (length - t) / release)
    if t < attack + decay:
        return 1.0 - (1.0 - sustain) * (t - attack) / decay
    return sustain


def add_tone(buf, start, dur, freq, amp, wave_kind="square", duty=0.25, vibrato=0.0, slide=0.0,
             adsr=(0.005, 0.08, 0.6, 0.05)):
    """Mix one note into buf. `slide` bends the pitch by that many octaves over the note."""
    s0, n = int(start * RATE), int(dur * RATE)
    end = min(len(buf), s0 + n)
    phase = 0.0
    a, d, s, r = adsr
    for k, idx in enumerate(range(s0, end)):
        t = k / RATE
        f = freq * (2 ** (slide * k / max(1, n)))
        if vibrato and t > 0.12:
            f *= 1 + vibrato * math.sin(2 * math.pi * 5.5 * t)
        phase = (phase + f / RATE) % 1.0
        if wave_kind == "square":
            v = 1.0 if phase < duty else -1.0
        elif wave_kind == "triangle":
            v = 4 * phase - 1 if phase < 0.5 else 3 - 4 * phase
        elif wave_kind == "saw":
            v = 2 * phase - 1
        else:  # sine
            v = math.sin(2 * math.pi * phase)
        buf[idx] += v * amp * env(k, n, a, d, s, r)


def add_noise(buf, start, dur, amp, decay=0.05, highpass=True, seed=1):
    rng = random.Random(seed)
    s0, n = int(start * RATE), int(dur * RATE)
    prev = 0.0
    for k, idx in enumerate(range(s0, min(len(buf), s0 + n))):
        x = rng.uniform(-1, 1)
        v = x - prev if highpass else x
        prev = x
        buf[idx] += v * amp * math.exp(-(k / RATE) / decay)


def add_kick(buf, start, amp=0.5):
    s0, n = int(start * RATE), int(0.16 * RATE)
    phase = 0.0
    for k, idx in enumerate(range(s0, min(len(buf), s0 + n))):
        t = k / RATE
        phase += (50 + 110 * math.exp(-t * 30)) / RATE
        buf[idx] += math.sin(2 * math.pi * phase) * amp * math.exp(-t * 18)


def to_bytes(buf, channels=2, gain=1.0):
    """Float samples -> 16-bit PCM with a soft limiter (never clips harshly)."""
    out = array("h")
    for v in buf:
        v = math.tanh(v * gain * MASTER * 1.2)
        s = int(v * 32000)
        out.append(s)
        if channels == 2:
            out.append(s)
    return out.tobytes()


def write_wav(path, buf, gain=1.0):
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(to_bytes(buf, 2, gain))

# ----------------------------------------------------------------------------
# Music: two original chiptune loops


C_MAJOR_CHORDS = {"C": (48, 52, 55), "G": (43, 47, 50), "Am": (45, 48, 52), "F": (41, 45, 48), "Dm": (50, 53, 57)}

# Melodies as (start in 16ths, length in 16ths, MIDI note), one list per bar.
RACE_A = [
    [(0, 2, 76), (2, 2, 79), (4, 4, 84), (8, 2, 83), (10, 2, 79), (12, 4, 76)],
    [(0, 2, 74), (2, 2, 79), (4, 4, 83), (8, 2, 81), (10, 2, 79), (12, 4, 74)],
    [(0, 2, 72), (2, 2, 76), (4, 4, 81), (8, 2, 79), (10, 2, 76), (12, 2, 72), (14, 2, 74)],
    [(0, 4, 77), (4, 4, 81), (8, 2, 84), (10, 2, 81), (12, 4, 79)],
]
RACE_B = [
    [(0, 3, 84), (3, 1, 83), (4, 2, 84), (6, 2, 88), (8, 4, 86), (12, 4, 84)],
    [(0, 3, 83), (3, 1, 81), (4, 2, 83), (6, 2, 86), (8, 4, 79), (12, 4, 83)],
    [(0, 3, 81), (3, 1, 79), (4, 2, 81), (6, 2, 84), (8, 4, 88), (12, 2, 84), (14, 2, 81)],
    [(0, 2, 77), (2, 2, 81), (4, 2, 84), (6, 2, 89), (8, 2, 88), (10, 2, 86), (12, 2, 84), (14, 2, 79)],
]
MENU_A = [
    [(0, 4, 76), (4, 4, 79), (8, 6, 84), (14, 2, 83)],
    [(0, 4, 81), (4, 4, 76), (8, 8, 72)],
    [(0, 4, 77), (4, 4, 81), (8, 4, 84), (12, 4, 81)],
    [(0, 6, 79), (6, 2, 77), (8, 4, 76), (12, 4, 74)],
]
MENU_B = MENU_A[:3] + [[(0, 4, 71), (4, 4, 74), (8, 8, 79)]]


def compose(bpm, chords, sections, lead="square", drums=True, pad=False):
    step = 60 / bpm / 4  # one 16th note
    bars = [(chords[i % len(chords)], bar) for sec in sections for i, bar in enumerate(sec)]
    buf = buffer(len(bars) * 16 * step + 0.05)
    for b, (chord, melody) in enumerate(bars):
        t0 = b * 16 * step
        root = C_MAJOR_CHORDS[chord]
        for s, length, note in melody:
            if lead == "square":
                add_tone(buf, t0 + s * step, length * step * 0.95, midi_hz(note), 0.13, "square", 0.25, vibrato=0.006)
            else:
                add_tone(buf, t0 + s * step, length * step, midi_hz(note), 0.16, "triangle", vibrato=0.005,
                         adsr=(0.01, 0.2, 0.5, 0.12))
                add_tone(buf, t0 + s * step, length * step, midi_hz(note + 12), 0.04, "sine", adsr=(0.01, 0.2, 0.4, 0.12))
        if drums:  # bouncy bass on the beat, octave jump on the off-beat
            for beat in range(4):
                add_tone(buf, t0 + beat * 4 * step, 2 * step, midi_hz(root[0] - 12), 0.2, "triangle",
                         adsr=(0.003, 0.05, 0.8, 0.03))
                add_tone(buf, t0 + (beat * 4 + 2) * step, 2 * step, midi_hz(root[0]), 0.14, "triangle",
                         adsr=(0.003, 0.05, 0.7, 0.03))
            for beat in range(4):
                if beat % 2 == 0:
                    add_kick(buf, t0 + beat * 4 * step, 0.38)
                else:
                    add_noise(buf, t0 + beat * 4 * step, 0.14, 0.16, decay=0.05, highpass=False, seed=b * 4 + beat)
                    add_tone(buf, t0 + beat * 4 * step, 0.08, 190, 0.08, "sine")
            for h in range(8):
                add_noise(buf, t0 + h * 2 * step, 0.04, 0.05, decay=0.012, seed=b * 8 + h + 99)
            for s in (3, 7, 11, 15):  # little chord stabs
                for note in root:
                    add_tone(buf, t0 + s * step, step * 0.8, midi_hz(note + 12), 0.025, "square", 0.5)
        else:  # gentle menu: slow bass + soft chord pad + shaker
            add_tone(buf, t0, 8 * step, midi_hz(root[0] - 12), 0.18, "triangle", adsr=(0.02, 0.3, 0.6, 0.1))
            add_tone(buf, t0 + 8 * step, 8 * step, midi_hz(root[0] - 12 + 7), 0.14, "triangle", adsr=(0.02, 0.3, 0.6, 0.1))
            if pad:
                for note in root:
                    add_tone(buf, t0, 16 * step, midi_hz(note + 12), 0.035, "sine", adsr=(0.2, 0.4, 0.8, 0.3))
            for h in range(8):
                add_noise(buf, t0 + h * 2 * step, 0.05, 0.03 if h % 2 else 0.045, decay=0.02, seed=b * 8 + h + 7)
    return buf


def build_music(force=False):
    """Render the music loops into the cache (once). Returns {name: path}."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    paths = {}
    for name in ("menu", "race"):
        path = os.path.join(CACHE_DIR, f"music_{name}_v{MUSIC_VERSION}.wav")
        if force or not os.path.exists(path):
            if name == "race":
                buf = compose(148, ["C", "G", "Am", "F"], [RACE_A, RACE_A, RACE_B, RACE_B])
            else:
                buf = compose(100, ["C", "Am", "F", "G"], [MENU_A, MENU_B], lead="soft", drums=False, pad=True)
            tmp = path + ".tmp"
            write_wav(tmp, buf)
            os.replace(tmp, path)
        paths[name] = path
    return paths

# ----------------------------------------------------------------------------
# Sound effects


def make_effects():
    fx = {}

    def new(seconds):
        return buffer(seconds)

    b = new(0.14)                                                       # menu blip
    add_tone(b, 0, 0.09, 880, 0.3, "square", 0.5, adsr=(0.002, 0.03, 0.5, 0.03))
    fx["move"] = b
    b = new(0.2)                                                        # select / ready pop
    add_tone(b, 0, 0.07, 660, 0.3, "square", 0.5)
    add_tone(b, 0.06, 0.12, 990, 0.3, "square", 0.5)
    fx["select"] = b
    b = new(0.22)                                                       # back
    add_tone(b, 0, 0.08, 660, 0.25, "square", 0.5)
    add_tone(b, 0.07, 0.12, 440, 0.25, "square", 0.5)
    fx["back"] = b
    b = new(0.34)                                                       # join: happy chirp
    for k, n in enumerate((72, 76, 79, 84)):
        add_tone(b, k * 0.06, 0.12, midi_hz(n), 0.22, "square", 0.25)
    fx["join"] = b
    b = new(0.12)                                                       # settings tick
    add_tone(b, 0, 0.05, 1320, 0.22, "triangle")
    fx["tick"] = b
    b = new(0.3)                                                        # countdown beep
    add_tone(b, 0, 0.22, midi_hz(72), 0.35, "square", 0.5, adsr=(0.002, 0.05, 0.7, 0.05))
    fx["beep"] = b
    b = new(0.6)                                                        # GO!
    add_tone(b, 0, 0.5, midi_hz(84), 0.35, "square", 0.5, adsr=(0.002, 0.05, 0.8, 0.15))
    add_tone(b, 0, 0.5, midi_hz(91), 0.15, "square", 0.25, adsr=(0.002, 0.05, 0.8, 0.15))
    fx["go"] = b
    b = new(0.6)                                                        # boost whoosh
    add_noise(b, 0, 0.55, 0.35, decay=0.25, highpass=True, seed=3)
    add_tone(b, 0, 0.5, 220, 0.18, "saw", slide=1.6, adsr=(0.01, 0.1, 0.7, 0.15))
    fx["boost"] = b
    b = new(0.7)                                                        # sparkle chime
    for k, n in enumerate((84, 88, 91, 96, 100)):
        add_tone(b, k * 0.05, 0.4, midi_hz(n), 0.13, "sine", adsr=(0.002, 0.1, 0.4, 0.25))
        add_tone(b, k * 0.05, 0.3, midi_hz(n + 12), 0.05, "triangle", adsr=(0.002, 0.1, 0.3, 0.2))
    fx["sparkle"] = b
    b = new(0.25)                                                       # drift boost ready
    add_tone(b, 0, 0.2, midi_hz(93), 0.2, "triangle", adsr=(0.002, 0.05, 0.5, 0.1))
    fx["ready"] = b
    b = new(0.45)                                                       # wall boing
    add_tone(b, 0, 0.4, 180, 0.4, "sine", vibrato=0.0, slide=1.3, adsr=(0.002, 0.1, 0.6, 0.15))
    for k in range(len(b)):
        b[k] *= 0.6 + 0.4 * math.sin(2 * math.pi * 14 * k / RATE)       # springy wobble
    fx["boing"] = b
    b = new(0.25)                                                       # tree bonk
    add_tone(b, 0, 0.18, 300, 0.45, "sine", slide=-0.8, adsr=(0.001, 0.05, 0.4, 0.08))
    add_noise(b, 0, 0.06, 0.2, decay=0.02, seed=5)
    fx["bonk"] = b
    b = new(0.2)                                                        # kart bump
    add_kick(b, 0, 0.45)
    add_noise(b, 0, 0.08, 0.15, decay=0.03, highpass=False, seed=6)
    fx["bump"] = b
    b = new(0.8)                                                        # magic poof
    add_noise(b, 0, 0.45, 0.4, decay=0.15, highpass=False, seed=8)
    for k, n in enumerate((79, 84, 88, 91)):
        add_tone(b, 0.2 + k * 0.06, 0.35, midi_hz(n), 0.12, "sine", adsr=(0.002, 0.1, 0.4, 0.2))
    fx["poof"] = b
    b = new(0.5)                                                        # lap ding-ding
    add_tone(b, 0, 0.2, midi_hz(88), 0.25, "triangle", adsr=(0.002, 0.05, 0.5, 0.1))
    add_tone(b, 0.18, 0.3, midi_hz(93), 0.25, "triangle", adsr=(0.002, 0.05, 0.5, 0.15))
    fx["lap"] = b
    b = new(0.9)                                                        # final lap jingle
    for k, n in enumerate((79, 79, 79, 84)):
        add_tone(b, k * 0.12, 0.11 if k < 3 else 0.4, midi_hz(n), 0.25, "square", 0.25)
    fx["final_lap"] = b
    b = new(2.2)                                                        # finish fanfare
    for s, d, n in ((0, 0.14, 72), (0.15, 0.14, 76), (0.3, 0.14, 79), (0.45, 0.5, 84), (1.0, 0.14, 81),
                    (1.15, 0.9, 84)):
        add_tone(b, s, d, midi_hz(n), 0.22, "square", 0.25, vibrato=0.006)
        add_tone(b, s, d, midi_hz(n - 12), 0.1, "triangle")
    for s in (0.45, 1.15):
        add_kick(b, s, 0.3)
    fx["finish"] = b
    b = new(1.0)                                                        # new best lap
    for k, n in enumerate((84, 88, 91, 96)):
        add_tone(b, k * 0.08, 0.5, midi_hz(n), 0.16, "square", 0.25, adsr=(0.002, 0.1, 0.5, 0.2))
    fx["best"] = b
    b = new(0.3)                                                        # pause
    add_tone(b, 0, 0.1, 523, 0.25, "square", 0.5)
    add_tone(b, 0.1, 0.12, 392, 0.25, "square", 0.5)
    fx["pause"] = b
    return fx

# ----------------------------------------------------------------------------
# Runtime


class Audio:
    """Plays music and effects. Every call is safe even when there's no sound device."""

    MIN_GAP = {"bump": 0.12, "boing": 0.15, "bonk": 0.15, "move": 0.04, "tick": 0.04}

    def __init__(self, music_on=True, sfx_on=True):
        self.ok = False
        self.music_on, self.sfx_on = music_on, sfx_on
        self.sounds = {}
        self.current = None
        self.last = {}
        try:
            init = pygame.mixer.get_init()
            if init and (init[0] != RATE or init[1] != -16):
                pygame.mixer.quit()  # pygame.init() picked another format: restart at ours
                init = None
            if not init:
                pygame.mixer.init(frequency=RATE, size=-16, channels=2, buffer=512)
            pygame.mixer.set_num_channels(24)
            freq, size, channels = pygame.mixer.get_init()
            if freq != RATE or size != -16:
                raise pygame.error(f"mixer runs at {freq} Hz / {size} bit")
            for name, buf in make_effects().items():
                self.sounds[name] = pygame.mixer.Sound(buffer=to_bytes(buf, channels))
                self.sounds[name].set_volume(0.55)
            self.music_paths = build_music()
            self.ok = True
        except Exception as e:  # noqa: BLE001 - no audio device, odd driver... just stay quiet
            print(f"Sound unavailable ({e}); playing silently.")

    def play(self, name, volume=1.0, now=None):
        if not (self.ok and self.sfx_on) or name not in self.sounds:
            return
        t = pygame.time.get_ticks() / 1000 if now is None else now
        if t - self.last.get(name, -9) < self.MIN_GAP.get(name, 0.03):
            return
        self.last[name] = t
        ch = self.sounds[name].play()
        if ch is not None:
            ch.set_volume(volume)

    def music(self, track, volume=0.5):
        """Switch to 'menu', 'race' or None (silence)."""
        if not self.ok:
            return
        want = track if self.music_on else None
        if want == self.current:
            pygame.mixer.music.set_volume(volume)
            return
        self.current = want
        try:
            if want is None:
                pygame.mixer.music.fadeout(400)
            else:
                pygame.mixer.music.load(self.music_paths[want])
                pygame.mixer.music.set_volume(volume)
                pygame.mixer.music.play(-1, fade_ms=600)
        except pygame.error as e:
            print(f"Music problem: {e}")

    def set_music(self, on):
        self.music_on = on
        if not on:
            self.music(None)

    def set_sfx(self, on):
        self.sfx_on = on


if __name__ == "__main__":
    import time
    t = time.time()
    paths = build_music(force="--force" in sys.argv)
    print(f"Music ready in {time.time() - t:.1f}s: {', '.join(paths.values())}")
    if "--wav" in sys.argv:
        out = sys.argv[sys.argv.index("--wav") + 1]
        os.makedirs(out, exist_ok=True)
        for name, buf in make_effects().items():
            write_wav(os.path.join(out, f"{name}.wav"), buf)
        print(f"Effects written to {out}")
