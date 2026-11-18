# Kart Rush

A top-down arcade kart racer for PC, made to be played with a console-style
controller. Pick one of 10 racers, then race three rivals through a candy
countryside with lollipops, gumdrops and mushrooms. There are two modes: one
for little kids and one for big kids.

## Run it

Requires Python 3.8+.

```sh
cd game/kart_racer
pip install -r requirements.txt
python kart_racer.py
```

Plug in a controller before or while the game is running. Press **F11** for
fullscreen.

## Modes

### Little Racer (for about ages 3–5)
- **The kart drives itself.** It never stops, and there's no brake to get
  stuck on.
- **Her steering counts.** The game gently steers too, but pushing the stick
  clearly moves the kart, so she can weave and chase the other racers.
- **Bouncy walls.** The kart bounces off the edge of the road with a sparkle
  and keeps going. It can't leave the track or crash into trees.
- **Turns itself around.** If she ends up going the wrong way for about 2
  seconds, the kart turns back to face the right way.
- **Any button gives a sparkle boost:** a burst of stars, a speed-up and a
  little rumble.
- Races are 2 laps, the rivals are gentle, and every finish gets
  "Hooray! You did it!" with confetti.

### Big Racer (for about ages 6+)
Full control over 3 laps: gas, brake, reverse, and drift boosts. Driving on
the grass slows you down, trees are solid, and the rivals race properly. Your
best lap is saved.

## Racers

| Magical & sweet       | Action                       |
|-----------------------|------------------------------|
| Sparkle the unicorn   | Blaze, the fire creature     |
| Coral the mermaid     | Droplet, the water creature  |
| Sprinkles the donut   | Ember Ninja (brick-built)    |
| Swirly the lollipop   | Jade Ninja (brick-built)     |
| Cupcake               | Flame Rod, a die-cast hot rod |

Every racer has a matching kart and boost trail. Sparkle's trail is a
rainbow.

## Controls

| Action                 | Controller (Xbox / PlayStation)  | Keyboard        |
|------------------------|----------------------------------|-----------------|
| Menus                  | Left stick / D-pad, A to pick, B back | Arrows, Enter, Backspace |
| Steer                  | Left stick or D-pad              | Arrows / A D    |
| Accelerate             | RT / R2 (or A / Cross)           | Up / W          |
| Brake / reverse        | LT / L2 (or B / Circle)          | Down / S        |
| Drift (hold in a turn) | RB / LB / X  (R1 / L1 / Square)  | Space / Shift   |
| Sparkle boost (Little) | Any of A B X Y LB RB             | Space / Enter   |
| Pause                  | Start / Options                  | Esc             |
| Restart (when paused)  | Y / Triangle                     | R               |

**Drift boost (Big Racer):** hold drift through a corner at speed. When the
sparks change from blue to orange, release for a burst of speed.

## Supported controllers

The game uses SDL's GameController database (built into pygame), so Xbox
360/One/Series, PlayStation 4/5, Switch Pro, 8BitDo and most other wired or
Bluetooth pads work with the right button layout and no setup. Pads rumble
on bumps, boosts and the countdown. If SDL doesn't recognise a pad, it falls
back to a generic layout, which you can adjust in `RAW_BUTTONS` / `RAW_AXES`
in `input_manager.py`.

## Tuning Little Racer

The constants at the top of `kart_racer.py` control the toddler mode:
`LITTLE_ASSIST` (how much the game steers), `LITTLE_INPUT` (how much her
stick counts), `WRONG_WAY_SECONDS`, `WALL_BOUNCE` and `LITTLE_PLAYER_SKILL`
(her top speed).

## Files

- `kart_racer.py`: the game (track, physics, AI, both modes, menus, HUD).
- `characters.py`: the 10 racers, all drawn in code.
- `input_manager.py`: controller and keyboard input with hot-plug and rumble.
