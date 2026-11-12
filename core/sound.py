"""Optional non-blocking passive buzzer service."""
import config
try:
    from time import ticks_ms, ticks_add, ticks_diff
except ImportError:
    import time
    ticks_ms = lambda: int(time.time() * 1000)
    ticks_add = lambda value, delta: value + delta
    ticks_diff = lambda newer, older: newer - older


class SoundManager:
    def __init__(self):
        self.enabled = config.SOUND_ENABLED
        self.ui_enabled = config.UI_SOUNDS_ENABLED
        self.volume = 256
        self.music_active = False
        self.error = ""
        self.buzzer = None
        self.stop_at = None
        try:
            from machine import Pin, PWM
            self.buzzer = PWM(Pin(config.BUZZER_PIN), freq=2200, duty=0)
        except Exception as exc:
            self.enabled = False
            self.error = str(exc)

    def play(self, frequency=2200, duration_ms=25, kind="ui"):
        if (not self.enabled or self.music_active or
                (kind == "ui" and not self.ui_enabled) or self.buzzer is None):
            return
        try:
            self.buzzer.freq(frequency)
            self.buzzer.duty(self.volume)
            self.stop_at = ticks_add(ticks_ms(), duration_ms)
        except Exception as exc:
            self.error = str(exc)
            self.enabled = False

    def music_tone(self, frequency, duty):
        if self.buzzer is None or not self.enabled:
            return False
        try:
            self.stop_at = None
            self.music_active = True
            if frequency > 0 and duty > 0:
                self.buzzer.freq(frequency)
                self.buzzer.duty(duty)
            else:
                self.buzzer.duty(0)
            return True
        except Exception as exc:
            self.error = str(exc)
            self.enabled = False
            self.music_end()
            return False

    def music_end(self):
        self.music_active = False
        self.stop_at = None
        if self.buzzer is not None:
            try:
                self.buzzer.duty(0)
            except Exception as exc:
                self.error = str(exc)
                self.enabled = False

    def stop_tone(self):
        self.stop_at = None
        if self.buzzer is not None and not self.music_active:
            try:
                self.buzzer.duty(0)
            except Exception as exc:
                self.error = str(exc)
                self.enabled = False

    def update(self):
        if self.stop_at is not None and ticks_diff(ticks_ms(), self.stop_at) >= 0:
            self.stop_at = None
            try:
                self.buzzer.duty(0)
            except Exception as exc:
                self.error = str(exc)
                self.enabled = False

    def close(self):
        if self.buzzer is not None:
            try:
                self.buzzer.duty(0)
                self.buzzer.deinit()
            except Exception as exc:
                self.error = str(exc)

