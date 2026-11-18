# Kart Rush

A top-down arcade kart racer for PC, made to be played with a console-style
controller. Race three AI rivals over 3 laps, use boost pads, and chain
drifts for speed boosts. The keyboard works too.

## Run it

Requires Python 3.8+.

```sh
cd game/kart_racer
pip install -r requirements.txt
python kart_racer.py
```

Plug in a controller before or while the game is running. The bottom-left
corner shows which input device is active. Press **F11** for fullscreen.

## Controls

| Action                 | Controller (Xbox / PlayStation)  | Keyboard        |
|------------------------|----------------------------------|-----------------|
| Steer                  | Left stick or D-pad              | Arrows / A D    |
| Accelerate             | RT / R2 (or A / Cross)           | Up / W          |
| Brake / reverse        | LT / L2 (or B / Circle)          | Down / S        |
| Drift (hold in a turn) | RB / LB / X  (R1 / L1 / Square)  | Space / Shift   |
| Pause                  | Start / Options                  | Esc             |
| Restart (when paused)  | Y / Triangle                     | R               |
| Back to title          | B / Circle                       | Backspace       |

Triggers are analog, so you can feather the throttle. The controller rumbles
on bumps, crashes, boosts and the start countdown.

**Drift boost:** hold drift through a corner at speed. When the sparks change
from blue to orange, release to get a burst of speed. Longer drifts give
longer boosts.

## Supported controllers

The game uses SDL's GameController database (built into pygame), so Xbox
360/One/Series, PlayStation 4/5, Switch Pro, 8BitDo and most other wired or
Bluetooth pads work with the right button layout and no setup. If SDL doesn't
recognise a pad, it falls back to a generic XInput-style layout. You can
adjust that layout in `RAW_BUTTONS` / `RAW_AXES` at the top of
`input_manager.py`.

On Steam Deck or with Steam Input running, launch normally. Steam presents
the pad as an Xbox controller.

## Files

- `kart_racer.py`: the game (track, kart physics, AI, race logic, HUD).
- `input_manager.py`: controller and keyboard input with hot-plug and rumble.

Your best lap is saved to `~/.kart_rush_best.json`.
