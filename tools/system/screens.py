"""Interactive diagnostics built on shared display/input/sound services."""
import gc
from core.screen_manager import Screen
from core.system_info import device_lines, memory_lines, storage_lines
try:
    from time import ticks_ms, ticks_diff
except ImportError:
    import time
    ticks_ms = lambda: int(time.time() * 1000)
    ticks_diff = lambda a, b: a - b


class SystemMonitorScreen(Screen):
    def __init__(self):
        self.last_draw = 0

    def update(self, app):
        now = ticks_ms()
        if ticks_diff(now, self.last_draw) >= 1000:
            self.last_draw = now
            return True
        return False

    def render(self, app):
        elapsed = ticks_diff(ticks_ms(), app.started_at) // 1000
        try:
            free = gc.mem_free()
            memory = "%d B free" % free
        except Exception:
            memory = "Memory unavailable"
        try:
            import machine
            frequency = "%d MHz" % (machine.freq() // 1000000)
        except Exception:
            frequency = "CPU unavailable"
        app.display.render_lines("Monitor", ["Uptime: %ds" % elapsed, "CPU: " + frequency,
                                  memory, "Screen: " + app.navigation.current.__class__.__name__],
                                 footer="LEFT: Back")


class DisplayDiagnosticScreen(Screen):
    MODES = ("PIXEL", "BORDER", "TEXT", "INVERT", "REFRESH")

    def __init__(self):
        self.mode = 0
        self.contrast = None
        self.original_invert = None

    def render(self, app):
        d = app.display.display
        d.fill(0)
        mode = self.MODES[self.mode]
        if mode == "PIXEL":
            for x in range(0, 128, 8):
                for y in range(0, 128, 8):
                    d.pixel(x, y, 1)
            app.display.text("Pixel grid", 24, 56)
        elif mode == "BORDER":
            d.rect(0, 0, 128, 128, 1)
            d.rect(4, 4, 120, 120, 1)
            app.display.text("Border test", 32, 58)
        elif mode == "TEXT":
            app.display.text("SH1107 TEXT", 12, 32)
            app.display.text("0123456789", 16, 56)
            app.display.text("Refresh OK", 20, 80)
        elif mode == "INVERT":
            d.fill(0)
            app.display.text("Inverted output", 8, 56, 1)
            app.display.text("SELECT: Next", 8, 72, 1)
        else:
            app.display.text("Refresh test", 16, 40)
            app.display.text("Frame sent", 24, 64)
        app.display.text("UP/DN: Contrast", 0, 104)
        app.display.text("LEFT: Exit", 0, 112)
        d.show()

    def handle(self, app, button):
        d = app.display.display
        if button == "up":
            if self.contrast is None:
                self.contrast = app.settings.get("brightness")
            self.contrast = min(255, self.contrast + 32)
            d.contrast(self.contrast)
        elif button == "down":
            if self.contrast is None:
                self.contrast = app.settings.get("brightness")
            self.contrast = max(0, self.contrast - 32)
            d.contrast(self.contrast)
        elif button in ("select", "right"):
            self.mode = (self.mode + 1) % len(self.MODES)
            self._apply_inversion(app)
        elif button == "left":
            app.navigation.back()
            return True
        else:
            return False
        return True

    def _apply_inversion(self, app):
        display = app.display.display
        if self.MODES[self.mode] == "INVERT":
            if self.original_invert is None:
                self.original_invert = display.inverse
            display.invert(not self.original_invert)
        elif self.original_invert is not None:
            display.invert(self.original_invert)

    def on_exit(self, app):
        if self.original_invert is not None:
            app.display.display.invert(self.original_invert)
        app.display.display.contrast(app.settings.get("brightness"))


class BuzzerDiagnosticScreen(Screen):
    def __init__(self):
        self.frequency = 2200
        self.duration = 80
        self.message = "SELECT: Play tone"

    def render(self, app):
        app.display.render_lines("Buzzer Test", ["Freq: %d Hz" % self.frequency,
                                  "Length: %d ms" % self.duration,
                                  "UP/DN: Frequency", "RIGHT: Length", self.message],
                                 footer="L:Back SEL:Play")

    def handle(self, app, button):
        if button == "left":
            app.navigation.back()
        elif button == "up":
            self.frequency = min(5000, self.frequency + 100)
        elif button == "down":
            self.frequency = max(200, self.frequency - 100)
        elif button == "right":
            self.duration = 200 if self.duration == 80 else 80
        elif button == "select":
            if app.sound.enabled and app.sound.buzzer is not None:
                app.sound.play(self.frequency, self.duration, "test")
                self.message = "Tone requested"
            else:
                self.message = "Buzzer unavailable"
        else:
            return False
        return True

    def on_exit(self, app):
        app.sound.stop_tone()


class I2CScanScreen(Screen):
    def __init__(self):
        self.addresses = None
        self.error = ""
        self.offset = 0
        self.lines = []

    def render(self, app):
        if self.addresses is None and not self.error:
            self.addresses = app.display.i2c_addresses
        if self.error:
            lines = ["Scan error", self.error]
        elif self.addresses:
            lines = ["Found %d device(s)" % len(self.addresses)] + ["0x%02X" % a for a in self.addresses]
        else:
            lines = ["No responding", "I2C devices"]
        self.lines = app.display.wrap_lines(lines)
        app.display.render_document("I2C Scan", self.lines, self.offset,
                                    "UP/DN Scroll SEL" if len(self.lines) > 12 else "L:Back SEL:Scan")

    def handle(self, app, button):
        if button in ("up", "down") and len(self.lines) > 12:
            self.offset = max(0, min(len(self.lines) - 12,
                                     self.offset + (1 if button == "down" else -1)))
            return True
        if button == "select":
            try:
                bus = app.display.i2c
                if bus is None:
                    raise RuntimeError("I2C bus unavailable")
                self.addresses = bus.scan()
                app.display.i2c_addresses = list(self.addresses)
                self.error = ""
            except Exception as exc:
                self.error = str(exc)
            return True
        if button == "left":
            app.navigation.back()
            return True
        return False
