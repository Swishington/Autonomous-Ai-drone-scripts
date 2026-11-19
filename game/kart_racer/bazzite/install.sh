#!/usr/bin/env bash
# Install Kart Rush on Bazzite (or SteamOS / any Linux with Steam) and add it to Steam.
#
#   ./install.sh                         install (or update) the game
#   ./install.sh --names Sister Brother ...and set the names of the two family racers
#
# Everything goes into your home folder, so it works on Bazzite's read-only system:
#   ~/.local/share/kart-rush/            game files, Python environment, Steam artwork
#   ~/.local/share/applications/         a "Kart Rush" app entry (so Steam can find it)
#   ~/.config/kart-rush/family.json      the family racers' names (only if --names given)
# Run it again any time to update after downloading a newer version.
set -euo pipefail

SISTER=""
BROTHER=""
while [ $# -gt 0 ]; do
    case "$1" in
        --names)
            [ $# -ge 3 ] || { echo "Usage: $0 --names SISTER BROTHER" >&2; exit 1; }
            SISTER="$2"; BROTHER="$3"; shift 3 ;;
        -h|--help)
            sed -n '2,13p' "$0"; exit 0 ;;
        *)
            echo "Unknown option: $1 (try --help)" >&2; exit 1 ;;
    esac
done

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
DEST="$DATA/kart-rush"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/kart-rush"
PYTHON="${PYTHON:-python3}"

say() { printf '\n\033[1;35m==> %s\033[0m\n' "$*"; }

command -v "$PYTHON" >/dev/null || { echo "Python 3 was not found." >&2; exit 1; }
"$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 8))' || { echo "Python 3.8 or newer is needed." >&2; exit 1; }

say "Copying the game to $DEST"
mkdir -p "$DEST/game"
cp "$SRC"/*.py "$DEST/game/"
cp -r "$SRC/assets" "$DEST/game/"

say "Setting up Python, pygame-ce and ModernGL for 3D (first run downloads about 20 MB)"
if [ ! -x "$DEST/venv/bin/python" ]; then
    "$PYTHON" -m venv "$DEST/venv"
fi
"$DEST/venv/bin/python" -m pip install --quiet --upgrade pip
"$DEST/venv/bin/python" -m pip install --quiet --upgrade "pygame-ce>=2.5" "moderngl>=5.8"

if [ -n "$SISTER" ]; then
    say "Saving racer names: $SISTER and $BROTHER"
    mkdir -p "$CONFIG"
    SISTER="$SISTER" BROTHER="$BROTHER" "$DEST/venv/bin/python" - "$CONFIG/family.json" <<'PY'
import json, os, sys
with open(sys.argv[1], "w") as f:
    json.dump({"sister": os.environ["SISTER"], "brother": os.environ["BROTHER"]}, f)
PY
fi

say "Making the launcher"
cat > "$DEST/kart-rush.sh" <<EOF
#!/usr/bin/env bash
# Starts Kart Rush fullscreen. Add this file to Steam as a Non-Steam Game.
cd "$DEST/game"
exec "$DEST/venv/bin/python" kart_racer.py --fullscreen "\$@"
EOF
chmod +x "$DEST/kart-rush.sh"

say "Drawing Steam artwork"
"$DEST/venv/bin/python" "$DEST/game/make_art.py" "$DEST/steam-art" >/dev/null
mkdir -p "$DATA/icons/hicolor/256x256/apps"
cp "$DEST/steam-art/icon.png" "$DATA/icons/hicolor/256x256/apps/kart-rush.png"

say "Adding Kart Rush to the app menu"
mkdir -p "$DATA/applications"
DESKTOP="$DATA/applications/kart-rush.desktop"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Kart Rush
Comment=Kart racing for up to 4 players with controllers
Exec="$DEST/kart-rush.sh"
Icon=kart-rush
Terminal=false
Categories=Game;
EOF
command -v update-desktop-database >/dev/null && update-desktop-database "$DATA/applications" >/dev/null 2>&1 || true

say "Adding to Steam"
if command -v steamos-add-to-steam >/dev/null; then
    steamos-add-to-steam "$DESKTOP" && echo "Sent to Steam - look for Kart Rush in your library." \
        || echo "That didn't work - use the manual steps below."
else
    echo "Do this once in Desktop Mode:"
fi
cat <<EOF

  1. Open Steam, then Games > Add a Non-Steam Game to My Library...
  2. Tick "Kart Rush" in the list and click "Add Selected Programs".
     (Not listed? Click Browse... and pick $DEST/kart-rush.sh)
  3. Optional cover art: in your Library, right-click Kart Rush > Manage >
     Set custom artwork, and pick the pictures in:
        $DEST/steam-art
     (capsule.png = cover, hero.png = banner, logo.png = logo)

Kart Rush then shows up in Game Mode with your other games. Every controller
plugged in can join, and the Steam button > Exit Game quits it.
EOF
