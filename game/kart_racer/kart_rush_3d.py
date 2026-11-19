"""Kart Rush 3D - the chase-camera 3D version of Kart Rush.

Run:  python kart_rush_3d.py            (add --fullscreen for fullscreen)

It shares its racers, controls, Little Racer mode and race rules with the
top-down Kart Rush (kart_racer.py); only the view and the title differ.
If this PC can't run OpenGL 3.3, it falls back to the top-down view.
"""

from kart_racer import main

if __name__ == "__main__":
    main(three_d=True)
