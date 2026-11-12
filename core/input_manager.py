"""Non-blocking debounced, active-low joystick event polling."""
import config
try:
    from time import ticks_ms, ticks_diff
except ImportError:
    import time
    ticks_ms = lambda: int(time.time() * 1000)
    ticks_diff = lambda newer, older: newer - older


class InputManager:
    BUTTONS = ("up", "down", "left", "right", "select")

    def __init__(self, pins=None, debounce_ms=None, repeat_delay_ms=None, repeat_interval_ms=None):
        from machine import Pin
        pin_map = config.JOYSTICK_PINS if pins is None else pins
        self.pins = dict((name, Pin(pin_map[name], Pin.IN, Pin.PULL_UP)) for name in self.BUTTONS)
        self.debounce_ms = config.INPUT_DEBOUNCE_MS if debounce_ms is None else debounce_ms
        self.repeat_delay_ms = config.INPUT_REPEAT_DELAY_MS if repeat_delay_ms is None else repeat_delay_ms
        self.repeat_interval_ms = config.INPUT_REPEAT_INTERVAL_MS if repeat_interval_ms is None else repeat_interval_ms
        now = ticks_ms()
        self.raw = dict((b, False) for b in self.BUTTONS)
        self.state = dict((b, False) for b in self.BUTTONS)
        self.changed = dict((b, now) for b in self.BUTTONS)
        self.pressed_at = dict((b, now) for b in self.BUTTONS)
        self.last_repeat = dict((b, now) for b in self.BUTTONS)
        self.events = []
        self.chord_latched = False

    def is_pressed(self, button):
        return self.state.get(button, False)

    def current_state(self):
        return dict(self.state)

    def poll(self):
        now = ticks_ms()
        self.events = []
        active = [b for b in self.BUTTONS if self.pins[b].value() == 0]
        # Ignore ambiguous chords until all keys are released.
        if len(active) > 1:
            self.chord_latched = True
        if self.chord_latched:
            if not active:
                self.chord_latched = False
            active = []
        for button in self.BUTTONS:
            raw = button in active
            if raw != self.raw[button]:
                self.raw[button] = raw
                self.changed[button] = now
            if raw != self.state[button] and ticks_diff(now, self.changed[button]) >= self.debounce_ms:
                self.state[button] = raw
                if raw:
                    self.pressed_at[button] = now
                    self.last_repeat[button] = now
                    self.events.append((button, "press"))
                else:
                    self.events.append((button, "release"))
            elif raw and self.state[button] and button in ("up", "down"):
                if (ticks_diff(now, self.pressed_at[button]) >= self.repeat_delay_ms and
                        ticks_diff(now, self.last_repeat[button]) >= self.repeat_interval_ms):
                    self.last_repeat[button] = now
                    self.events.append((button, "repeat"))
        return self.events
