"""Multi-player gamepad + keyboard input for Kart Rush.

Every connected controller is its own input *device*, and so are two halves of
the keyboard (arrow keys and WASD), so up to 4 people can play at once.

Console-style controllers (Xbox, PlayStation, Switch Pro, 8BitDo, most
generic USB/Bluetooth pads) are read through SDL's GameController API, which
gives every supported pad the same Xbox-style layout. A pad SDL doesn't
recognise falls back to the raw joystick API with an XInput-style mapping.

Controllers can be plugged in or removed while the game is running.
"""

import os
import sys

# Map buttons by POSITION, not by the printed label. Nintendo-style pads (Switch Pro,
# 8BitDo in Switch mode) print "A" on the right, so label mapping puts the game's
# "A" (bottom button: join / gas) in the wrong place. Must be set before pygame starts.
os.environ.setdefault("SDL_GAMECONTROLLER_USE_BUTTON_LABELS", "0")

import pygame  # noqa: E402

try:
    from pygame._sdl2 import controller as sdl_controller
except ImportError:  # very old pygame builds
    sdl_controller = None

STICK_DEADZONE = 0.15
TRIGGER_DEADZONE = 0.05

# Raw-joystick fallback layout, only used for pads SDL has no mapping for.
# Xbox-style order: Windows (XInput) and Linux (xpad driver) report axes differently.
# Edit these if you use an unusual pad.
RAW_BUTTONS = {"a": 0, "b": 1, "x": 2, "y": 3, "lb": 4, "rb": 5, "back": 6, "start": 7}
if sys.platform.startswith("linux"):
    RAW_AXES = {"lx": 0, "ly": 1, "lt": 2, "rt": 5}
else:
    RAW_AXES = {"lx": 0, "ly": 1, "lt": 4, "rt": 5}

# Two players can share one keyboard.
KEYBOARD_LAYOUTS = {
    "kb_arrows": {
        "name": "Keyboard (arrows)",
        "left": [pygame.K_LEFT], "right": [pygame.K_RIGHT], "up": [pygame.K_UP], "down": [pygame.K_DOWN],
        "drift": [pygame.K_RSHIFT, pygame.K_RCTRL], "confirm": [pygame.K_RETURN, pygame.K_KP_ENTER],
        "back": [pygame.K_BACKSPACE], "boost": [pygame.K_RSHIFT, pygame.K_RCTRL, pygame.K_RETURN],
    },
    "kb_wasd": {
        "name": "Keyboard (WASD)",
        "left": [pygame.K_a], "right": [pygame.K_d], "up": [pygame.K_w], "down": [pygame.K_s],
        "drift": [pygame.K_LSHIFT], "confirm": [pygame.K_SPACE],
        "back": [pygame.K_q], "boost": [pygame.K_LSHIFT, pygame.K_SPACE],
    },
}


def apply_deadzone(value, deadzone=STICK_DEADZONE):
    """Zero out small stick noise and rescale the rest back to the full -1..1 range."""
    if abs(value) < deadzone:
        return 0.0
    sign = 1.0 if value > 0 else -1.0
    return sign * min(1.0, (abs(value) - deadzone) / (1.0 - deadzone))


class Gamepad:
    """One physical pad, read through either the GameController or raw joystick API."""

    def __init__(self, device_index):
        self.controller = None
        self.joystick = None
        if sdl_controller is not None and sdl_controller.is_controller(device_index):
            self.controller = sdl_controller.Controller(device_index)
            self.name = self.controller.name or "Game controller"
            self.instance_id = self.controller.as_joystick().get_instance_id()
        else:
            self.joystick = pygame.joystick.Joystick(device_index)
            self.joystick.init()
            self.name = self.joystick.get_name() + " (generic mapping)"
            self.instance_id = self.joystick.get_instance_id()

    # --- raw reads -------------------------------------------------------
    def _axis(self, name):
        if self.controller is not None:
            axis = {
                "lx": pygame.CONTROLLER_AXIS_LEFTX,
                "ly": pygame.CONTROLLER_AXIS_LEFTY,
                "lt": pygame.CONTROLLER_AXIS_TRIGGERLEFT,
                "rt": pygame.CONTROLLER_AXIS_TRIGGERRIGHT,
            }[name]
            return max(-1.0, min(1.0, self.controller.get_axis(axis) / 32767.0))
        index = RAW_AXES[name]
        if index >= self.joystick.get_numaxes():
            return 0.0
        value = self.joystick.get_axis(index)
        if name in ("lt", "rt"):
            # Raw triggers usually rest at -1 and go to +1 when fully pressed.
            value = (value + 1.0) / 2.0
        return value

    def _button(self, name):
        if self.controller is not None:
            button = {
                "a": pygame.CONTROLLER_BUTTON_A,
                "b": pygame.CONTROLLER_BUTTON_B,
                "x": pygame.CONTROLLER_BUTTON_X,
                "y": pygame.CONTROLLER_BUTTON_Y,
                "lb": pygame.CONTROLLER_BUTTON_LEFTSHOULDER,
                "rb": pygame.CONTROLLER_BUTTON_RIGHTSHOULDER,
                "back": pygame.CONTROLLER_BUTTON_BACK,
                "start": pygame.CONTROLLER_BUTTON_START,
                "left": pygame.CONTROLLER_BUTTON_DPAD_LEFT,
                "right": pygame.CONTROLLER_BUTTON_DPAD_RIGHT,
                "up": pygame.CONTROLLER_BUTTON_DPAD_UP,
                "down": pygame.CONTROLLER_BUTTON_DPAD_DOWN,
            }[name]
            return bool(self.controller.get_button(button))
        if name in ("left", "right", "up", "down"):
            if self.joystick.get_numhats() == 0:
                return False
            hx, hy = self.joystick.get_hat(0)
            return {"left": hx < 0, "right": hx > 0, "up": hy > 0, "down": hy < 0}[name]
        index = RAW_BUTTONS[name]
        return index < self.joystick.get_numbuttons() and bool(self.joystick.get_button(index))

    # --- public -------------------------------------------------------------
    def read(self):
        """Return (steer, throttle, brake, held_buttons) for this pad."""
        steer = apply_deadzone(self._axis("lx"))
        if self._button("left"):
            steer = -1.0
        elif self._button("right"):
            steer = 1.0
        rt = self._axis("rt")
        lt = self._axis("lt")
        throttle = rt if rt > TRIGGER_DEADZONE else 0.0
        brake = lt if lt > TRIGGER_DEADZONE else 0.0
        held = {n for n in ("a", "b", "x", "y", "lb", "rb", "back", "start", "up", "down", "left", "right")
                if self._button(n)}
        if "up" in held:
            held.add("dpad_up")      # D-pad only (the stick also adds "up"/"down" below)
        if "down" in held:
            held.add("dpad_down")
        # Let the stick drive menus too.
        lx, ly = self._axis("lx"), self._axis("ly")
        if lx < -0.6:
            held.add("left")
        elif lx > 0.6:
            held.add("right")
        if ly < -0.6:
            held.add("up")
        elif ly > 0.6:
            held.add("down")
        return steer, throttle, brake, held

    def rumble(self, low, high, duration_ms):
        try:
            if self.controller is not None:
                self.controller.rumble(low, high, duration_ms)
            else:
                self.joystick.rumble(low, high, duration_ms)
        except (pygame.error, AttributeError):
            pass  # rumble isn't supported on every pad / platform

    def close(self):
        try:
            if self.controller is not None:
                self.controller.quit()
            else:
                self.joystick.quit()
        except pygame.error:
            pass


class InputFrame:
    """Everything the game needs to know about one device for one frame."""

    def __init__(self, steer=0.0, throttle=0.0, brake=0.0, drift=False, pressed=()):
        self.steer = steer
        self.throttle = throttle
        self.brake = brake
        self.drift = drift
        # Actions that went down this frame:
        # confirm, back, pause, restart, quit, up, down, left, right, boost, join, mode
        self.pressed = set(pressed)


EMPTY_FRAME = InputFrame()


class InputManager:
    def __init__(self):
        pygame.joystick.init()
        if sdl_controller is not None:
            sdl_controller.init()
        self.pads = {}            # device id ("pad<instance id>") -> Gamepad
        self._prev_actions = {}   # device id -> set of held actions last frame
        self.rescan()

    # --- devices ------------------------------------------------------------
    @property
    def device_ids(self):
        return list(KEYBOARD_LAYOUTS) + list(self.pads)

    @property
    def pad_ids(self):
        return list(self.pads)

    def device_name(self, device):
        if device in KEYBOARD_LAYOUTS:
            return KEYBOARD_LAYOUTS[device]["name"]
        pad = self.pads.get(device)
        return pad.name if pad else "Disconnected"

    def is_connected(self, device):
        return device in KEYBOARD_LAYOUTS or device in self.pads

    def rescan(self):
        """Open every connected pad we don't already have."""
        open_ids = {p.instance_id for p in self.pads.values()}
        for i in range(pygame.joystick.get_count()):
            try:
                if pygame.joystick.Joystick(i).get_instance_id() in open_ids:
                    continue
                pad = Gamepad(i)
            except pygame.error:
                continue
            self.pads[f"pad{pad.instance_id}"] = pad
            open_ids.add(pad.instance_id)

    def handle_event(self, event):
        """Call for every pygame event so hot-plugging works."""
        if event.type in (pygame.JOYDEVICEADDED, getattr(pygame, "CONTROLLERDEVICEADDED", -1)):
            self.rescan()
        elif event.type in (pygame.JOYDEVICEREMOVED, getattr(pygame, "CONTROLLERDEVICEREMOVED", -1)):
            device = f"pad{getattr(event, 'instance_id', -1)}"
            pad = self.pads.pop(device, None)
            if pad is not None:
                pad.close()
                self._prev_actions.pop(device, None)

    def rumble(self, device, low, high, duration_ms):
        pad = self.pads.get(device)
        if pad is not None:
            pad.rumble(low, high, duration_ms)

    # --- polling ------------------------------------------------------------
    def _keyboard(self, device, keys):
        layout = KEYBOARD_LAYOUTS[device]
        down = lambda name: any(keys[k] for k in layout[name])
        steer = float(down("right")) - float(down("left"))
        throttle = 1.0 if down("up") else 0.0
        brake = 1.0 if down("down") else 0.0
        drift = down("drift")
        actions = {name for name in ("left", "right", "up", "down", "confirm", "back", "boost") if down(name)}
        if "confirm" in actions:
            actions.add("join")
        if down("up") or down("down"):
            actions.add("mode")
        if keys[pygame.K_ESCAPE]:
            actions.add("pause")
        if keys[pygame.K_r]:
            actions.add("restart")
        if keys[pygame.K_x]:
            actions.add("quit")
        return steer, throttle, brake, drift, actions

    @staticmethod
    def _pad(pad):
        try:
            steer, throttle, brake, held = pad.read()
        except pygame.error:
            return 0.0, 0.0, 0.0, False, set()
        # A / B work as gas / brake for pads with digital (or no) triggers.
        throttle = max(throttle, 1.0 if "a" in held else 0.0)
        brake = max(brake, 1.0 if "b" in held else 0.0)
        drift = bool(held & {"rb", "lb", "x"})
        actions = {d for d in ("up", "down", "left", "right") if d in held}
        if "a" in held:
            actions.add("confirm")
        if "b" in held:
            actions.add("back")
        if "back" in held:
            actions.add("quit")  # Select / View / Share button
        if "start" in held:
            actions.add("pause")
        if "y" in held:
            actions.add("restart")
        if held & {"a", "b", "x", "y", "lb", "rb"}:
            actions.add("boost")  # any face/shoulder button: Little Racer's sparkle boost
        if held & {"a", "b", "x", "y"}:
            actions.add("join")   # any face button joins, whatever the pad's layout
        if held & {"y", "dpad_up", "dpad_down"}:
            actions.add("mode")   # switch Little / Big Racer (not the stick: too easy to wiggle)
        return steer, throttle, brake, drift, actions

    def poll(self):
        """Return {device id: InputFrame} for every connected device."""
        keys = pygame.key.get_pressed()
        frames = {}
        for device in self.device_ids:
            if device in KEYBOARD_LAYOUTS:
                steer, throttle, brake, drift, actions = self._keyboard(device, keys)
            else:
                steer, throttle, brake, drift, actions = self._pad(self.pads[device])
            pressed = actions - self._prev_actions.get(device, set())
            self._prev_actions[device] = actions
            frames[device] = InputFrame(max(-1.0, min(1.0, steer)), throttle, brake, drift, pressed)
        return frames
