"""Small validated JSON preferences store; hardware pin configuration is separate."""
import config
try:
    import ujson as json
except ImportError:
    import json


DEFAULTS = {
    "brightness": 128,
    "debounce_ms": 35,
    "repeat_delay_ms": 450,
    "repeat_interval_ms": 140,
    "sound_enabled": True,
    "ui_sounds_enabled": True,
    "music_tempo": 100,
    "music_volume": 256,
    "ble_scan_duration_ms": 8000,
    "ble_scan_interval_us": 1280000,
    "ble_scan_window_us": 11250,
    "wifi_live_interval_ms": 2000,
    "wifi_result_limit": 24,
    "wifi_csi_buffer": 8,
}
MAX_SETTINGS_BYTES = 4096


class SettingsManager:
    def __init__(self, path="settings.json"):
        self.path = path
        self.values = dict(DEFAULTS)
        self.load()

    def _valid(self, key, value):
        if key in ("sound_enabled", "ui_sounds_enabled"):
            return isinstance(value, bool)
        bounds = {"brightness": (0, 255), "debounce_ms": (5, 250),
                  "repeat_delay_ms": (100, 2000), "repeat_interval_ms": (40, 1000),
                  "music_tempo": (50, 200), "music_volume": (0, 1023),
                  "ble_scan_duration_ms": (1000, 30000),
                  "ble_scan_interval_us": (100000, 2000000),
                  "ble_scan_window_us": (10000, 100000),
                  "wifi_live_interval_ms": (2000, 10000),
                  "wifi_result_limit": (1, 24), "wifi_csi_buffer": (4, 16)}
        if key in bounds and type(value) is int:
            return bounds[key][0] <= value <= bounds[key][1]
        return False

    def load(self):
        try:
            with open(self.path, "r") as stream:
                raw = stream.read(MAX_SETTINGS_BYTES + 1)
            if len(raw) > MAX_SETTINGS_BYTES:
                raise ValueError("settings file exceeds size limit")
            saved = json.loads(raw)
            if not isinstance(saved, dict):
                return self.values
            if isinstance(saved, dict):
                for key in DEFAULTS:
                    value = saved.get(key)
                    if self._valid(key, value):
                        self.values[key] = value
        except OSError:
            pass
        except Exception as exc:
            print("Settings file ignored:", exc)
        return self.values

    def get(self, key):
        return self.values.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        if key not in DEFAULTS or not self._valid(key, value):
            return False
        if key == "ble_scan_interval_us" and self.values.get("ble_scan_window_us", 11250) > value:
            return False
        if key == "ble_scan_window_us" and value > self.values.get("ble_scan_interval_us", 1280000):
            return False
        if self.values.get(key) == value:
            return True
        self.values[key] = value
        return self.save()

    def save(self):
        try:
            with open(self.path, "w") as stream:
                stream.write(json.dumps(self.values))
            return True
        except Exception as exc:
            print("Could not save settings:", exc)
            return False

    def reset(self):
        self.values = dict(DEFAULTS)
        return self.save()

    def apply(self, app):
        app.input.debounce_ms = self.get("debounce_ms")
        app.input.repeat_delay_ms = self.get("repeat_delay_ms")
        app.input.repeat_interval_ms = self.get("repeat_interval_ms")
        app.sound.enabled = self.get("sound_enabled")
        app.sound.ui_enabled = self.get("ui_sounds_enabled")
        app.sound.volume = self.get("music_volume")
        app.music.tempo = self.get("music_tempo")
        app.display.display.contrast(self.get("brightness"))
        config.DISPLAY_BRIGHTNESS = self.get("brightness")
