# Kart Rush

A top-down arcade kart racer for PC, made to be played with console-style
controllers. **Up to 4 people play split-screen**, and computer racers fill
the rest of the grid. Pick one of 10 racers and race through a candy
countryside with lollipops, gumdrops and mushrooms.

## Run it

Requires Python 3.8+.

```sh
cd game/kart_racer
pip install -r requirements.txt
python kart_racer.py            # add --fullscreen for fullscreen
```

Press **F11** for fullscreen.

## Install on Bazzite and add to Steam

You'll use this once, in **Desktop Mode**. Open **Konsole** and run:

```sh
git clone --depth 1 -b claude/pc-game-controller-support-qjf2bx \
    https://github.com/Swishington/Autonomous-Ai-drone-scripts.git ~/kart-rush-src
~/kart-rush-src/game/kart_racer/bazzite/install.sh --names "Sister" "Brother"
```

Put your kids' names in the `--names` part. They're saved only on that PC,
in `~/.config/kart-rush/family.json`.

The script installs everything into your home folder, which works fine on
Bazzite's read-only system. It doesn't need `sudo`. It:
- sets up its own Python environment with
  [pygame-ce](https://pyga.me), which works with Bazzite's Python;
- makes a fullscreen launcher and a "Kart Rush" app-menu entry;
- draws Steam artwork into `~/.local/share/kart-rush/steam-art`.

Then add it to Steam:
1. In Steam, go to **Games → Add a Non-Steam Game to My Library...**.
2. Tick **Kart Rush** and click **Add Selected Programs**.
3. Optional: right-click it, then **Manage → Set custom artwork**, and pick
   `capsule.png` (cover), `hero.png` (banner) and `logo.png` from the
   `steam-art` folder.

Kart Rush now appears in **Game Mode** alongside your other games. Every
controller that's connected can join. To quit, press the **Steam button →
Exit Game**, or pause the game and press **Select/View**.

You don't need a Steamworks developer account for this. A Non-Steam Game
shortcut gives the same library entry, controller support and artwork
privately, without the fee or Valve's review.

To update after a new version is pushed:
`cd ~/kart-rush-src && git pull && ./game/kart_racer/bazzite/install.sh`.
Your names are kept.

On Windows or another desktop, `pip install pygame-ce` (or `pygame`) and
`python kart_racer.py` also works.

## Getting a race going

1. **Join.** Each player presses **A** on their own controller. Two people
   can also share the keyboard: one presses **Enter** to play with the arrow
   keys, and the other presses **Space** to play with WASD.
2. **Pick.** Use **Left/Right** to choose a racer and **Up/Down** to choose
   that player's mode (Little Racer or Big Racer), then press **A** when ready.
   Players in the same race can use different modes, so a toddler and an older
   kid can race together.
3. **Race settings.** When everyone is ready, press A again and choose:
   - **Computer racers:** 0 up to 8 racers in total.
   - **Computer difficulty:** Easy, Medium or Hard.
   - **Laps:** 1–5. This starts at 2 if every player is a Little Racer,
     otherwise 3.

   Computer racers always get characters that nobody has picked.

Split-screen: 1 player gets the full screen, 2 players get side-by-side
halves, and 3–4 players get quarters. With 3 players, the spare quarter shows
a big map and the live standings. The race ends once every player has
finished, or 45 seconds after the first player finishes, with a "Hurry!"
countdown, so one controller left on the sofa doesn't hold everyone up.

If a controller gets unplugged mid-race, that player's kart keeps going (in
Little Racer mode) or coasts. They're moved onto the next controller that's
plugged in.

## Modes (chosen per player)

### Little Racer (for about ages 3–5)
- **The kart drives itself.** It never stops, and there's no brake to get
  stuck on.
- **Their steering counts.** The game gently steers too, but pushing the
  stick clearly moves the kart.
- **Bouncy walls.** The kart bounces off the edge of the road with a sparkle
  and keeps going. It can't leave the track or hit trees.
- **Turns itself around.** If the kart is going the wrong way for about 2
  seconds, it turns back to face the right way.
- **Any button gives a sparkle boost:** a burst of stars, a speed-up and a
  little rumble.
- Every race ends with "Hooray! Everyone did great!" and confetti.

### Big Racer (for about ages 6+)
Full control: gas, brake, reverse and drift boosts. Driving on the grass
slows you down and trees are solid. The best lap is saved.

## Racers

| Magical & sweet       | Action                       |
|-----------------------|------------------------------|
| Little Sis (family racer) | Big Bro (family racer)   |
| Sparkle the unicorn   | Blaze, the fire creature     |
| Coral the mermaid     | Droplet, the water creature  |
| Sprinkles the donut   | Ember Ninja (brick-built)    |
| Swirly the lollipop   | Jade Ninja (brick-built)     |
| Cupcake               | Flame Rod, a die-cast hot rod |

Little Sis and Big Bro are cartoon versions of the family's own kids. They
are drawn in code, and no photos are stored. Their real names come from
`~/.config/kart-rush/family.json` on the PC the game is installed on (the
Bazzite installer's `--names` option writes it). That keeps the names out of
this repository.

Every racer has a matching kart and boost trail. Sparkle's trail is a
rainbow.

## Controls

| Action                 | Controller (Xbox / PlayStation)  | Keyboard (arrows) | Keyboard (WASD) |
|------------------------|----------------------------------|-------------------|-----------------|
| Join / ready / pick    | A / Cross                        | Enter             | Space           |
| Back / leave           | B / Circle                       | Backspace         | Q               |
| Steer                  | Left stick or D-pad              | Left / Right      | A / D           |
| Accelerate             | RT / R2 (or A / Cross)           | Up                | W               |
| Brake / reverse        | LT / L2 (or B / Circle)          | Down              | S               |
| Drift (hold in a turn) | RB / LB / X (R1 / L1 / Square)   | Right Shift       | Left Shift      |
| Sparkle boost (Little) | Any of A B X Y LB RB             | Enter / R-Shift   | Space / L-Shift |
| Pause                  | Start / Options                  | Esc               | Esc             |
| Quit (when paused)     | Select / View / Share            | X                 | X               |
| Restart (when paused)  | Y / Triangle                     | R                 | R               |

**Drift boost (Big Racer):** hold drift through a corner at speed. When the
sparks change from blue to orange, release for a burst of speed.

## Supported controllers

The game uses SDL's GameController database (built into pygame), so Xbox
360/One/Series, PlayStation 4/5, Switch Pro, 8BitDo and most other wired or
Bluetooth pads work with the right button layout and no setup. Pads rumble
on bumps, boosts and the countdown. If SDL doesn't recognise a pad, it falls
back to a generic layout, which you can adjust in `RAW_BUTTONS` / `RAW_AXES`
in `input_manager.py`.

## Tuning

The constants at the top of `kart_racer.py` control the computer racers'
speed (`AI_SKILL`) and how much they catch up (`AI_CATCH_UP`) for each
difficulty, plus `FINISH_GRACE_SECONDS`. These control Little Racer:
`LITTLE_ASSIST` (how much the game steers), `LITTLE_INPUT` (how much her
stick counts), `WRONG_WAY_SECONDS`, `WALL_BOUNCE` and `LITTLE_PLAYER_SKILL`
(her top speed).

## Files

- `kart_racer.py`: the game (track, physics, AI, lobby, settings, split-screen, HUD).
- `characters.py`: the 10 racers, all drawn in code.
- `cartoon.py`: the cartoon look: supersampled shapes, sticker outlines, shading, soft shadows and outlined text.
- `assets/fonts/`: the Lilita One font (SIL Open Font License, see `OFL-LilitaOne.txt`).
- `make_art.py`: draws the Steam library artwork and icon.
- `bazzite/install.sh`: the Bazzite / Linux installer.
- `input_manager.py`: input from multiple controllers and a split keyboard, with hot-plug and rumble.
