"""Unified gamepad + keyboard input for Kart Rush.

Console-style controllers (Xbox, PlayStation, Switch Pro, 8BitDo, most
generic USB/Bluetooth pads) are read through SDL's GameController API, which
gives every supported pad the same Xbox-style layout. A pad SDL doesn't
recognise falls back to the raw joystick API with an XInput-style mapping.
The keyboard always works too, and both can be used at once.

Controllers can be plugged in or removed while the game is running.
"""

import pygame

try:
    from pygame._sdl2 import controller as sdl_controller
except ImportError:  # very old pygame builds
    sdl_controller = None

STICK_DEADZONE = 0.15
TRIGGER_DEADZONE = 0.05

# Raw-joystick fallback layout (XInput order as reported by SDL on Windows).
# Edit these if you use an unusual pad that SDL has no mapping for.
RAW_BUTTONS = {"a": 0, "b": 1, "x": 2, "y": 3, "lb": 4, "rb": 5, "back": 6, "start": 7}
RAW_AXES = {"lx": 0, "ly": 1, "lt": 4, "rt": 5}


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
    """Everything the game needs to know about input for one frame."""

    def __init__(self, steer=0.0, throttle=0.0, brake=0.0, drift=False, pressed=()):
        self.steer = steer
        self.throttle = throttle
        self.brake = brake
        self.drift = drift
        # Actions that went down this frame:
        # confirm, back, pause, restart, up, down, left, right, boost
        self.pressed = set(pressed)


class InputManager:
    def __init__(self):
        pygame.joystick.init()
        if sdl_controller is not None:
            sdl_controller.init()
        self.pad = None
        self._prev_actions = set()
        self.rescan()

    @property
    def device_name(self):
        return self.pad.name if self.pad else "Keyboard (plug in a controller any time)"

    def rescan(self):
        """Grab the first connected pad, if we don't already have one."""
        if self.pad is not None:
            return
        for i in range(pygame.joystick.get_count()):
            try:
                self.pad = Gamepad(i)
                return
            except pygame.error:
                continue

    def handle_event(self, event):
        """Call for every pygame event so hot-plugging works."""
        if event.type in (pygame.JOYDEVICEADDED, getattr(pygame, "CONTROLLERDEVICEADDED", -1)):
            self.rescan()
        elif event.type in (pygame.JOYDEVICEREMOVED, getattr(pygame, "CONTROLLERDEVICEREMOVED", -1)):
            if self.pad is not None and getattr(event, "instance_id", None) == self.pad.instance_id:
                self.pad.close()
                self.pad = None
                self.rescan()

    def rumble(self, low, high, duration_ms):
        if self.pad is not None:
            self.pad.rumble(low, high, duration_ms)

    def poll(self):
        keys = pygame.key.get_pressed()
        steer = float(keys[pygame.K_RIGHT] or keys[pygame.K_d]) - float(keys[pygame.K_LEFT] or keys[pygame.K_a])
        throttle = 1.0 if (keys[pygame.K_UP] or keys[pygame.K_w]) else 0.0
        brake = 1.0 if (keys[pygame.K_DOWN] or keys[pygame.K_s]) else 0.0
        drift = bool(keys[pygame.K_SPACE] or keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])

        actions = set()
        if keys[pygame.K_RETURN] or keys[pygame.K_KP_ENTER]:
            actions.add("confirm")
        if keys[pygame.K_ESCAPE]:
            actions.add("pause")
        if keys[pygame.K_BACKSPACE]:
            actions.add("back")
        if keys[pygame.K_r]:
            actions.add("restart")
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            actions.add("up")
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            actions.add("down")
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            actions.add("left")
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            actions.add("right")
        if drift or keys[pygame.K_RETURN]:
            actions.add("boost")

        if self.pad is not None:
            try:
                p_steer, p_throttle, p_brake, held = self.pad.read()
            except pygame.error:
                p_steer, p_throttle, p_brake, held = 0.0, 0.0, 0.0, set()
            if abs(p_steer) > abs(steer):
                steer = p_steer
            # A / B work as gas / brake for pads with digital (or no) triggers.
            throttle = max(throttle, p_throttle, 1.0 if "a" in held else 0.0)
            brake = max(brake, p_brake, 1.0 if "b" in held else 0.0)
            drift = drift or bool(held & {"rb", "lb", "x"})
            if "a" in held:
                actions.add("confirm")
            if "b" in held or "back" in held:
                actions.add("back")
            if "start" in held:
                actions.add("pause")
            if "y" in held:
                actions.add("restart")
            for direction in ("up", "down", "left", "right"):
                if direction in held:
                    actions.add(direction)
            if held & {"a", "b", "x", "y", "lb", "rb"}:
                actions.add("boost")  # any face/shoulder button: used for Little Racer's sparkle boost

        pressed = actions - self._prev_actions
        self._prev_actions = actions
        return InputFrame(max(-1.0, min(1.0, steer)), throttle, brake, drift, pressed)
