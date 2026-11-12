"""Persistent settings menu and music player integration."""
from ui.screens import MenuEntry
from tools.common import submenu, show_message
from tools.settings.screens import NumericSettingScreen, ToggleSettingScreen, MusicPlayerScreen
from core.screen_manager import ConfirmationScreen


def build_menu(app):
    def numeric(title, key, low, high, step, suffix):
        return lambda a: a.navigation.open(NumericSettingScreen(title, key, low, high, step, suffix, a))

    def toggle(title, key):
        return lambda a: a.navigation.open(ToggleSettingScreen(title, key, a))

    def reset(_):
        def apply_defaults():
            saved = app.settings.reset()
            app.settings.apply(app)
            return "Defaults restored" if saved else "Defaults active; save failed"
        app.navigation.open(ConfirmationScreen("Reset Settings", "Restore default settings?", apply_defaults))

    entries = [
        MenuEntry("Brightness / Contrast", numeric("Brightness", "brightness", 0, 255, 16, " / 255")),
        MenuEntry("Buzzer Sounds", toggle("Buzzer Sounds", "sound_enabled")),
        MenuEntry("UI Sound Effects", toggle("UI Sound Effects", "ui_sounds_enabled")),
        MenuEntry("Debounce Timing", numeric("Debounce", "debounce_ms", 5, 250, 5, " ms")),
        MenuEntry("Repeat Delay", numeric("Repeat Delay", "repeat_delay_ms", 100, 2000, 50, " ms")),
        MenuEntry("Repeat Speed", numeric("Repeat Interval", "repeat_interval_ms", 40, 1000, 20, " ms")),
        MenuEntry("Music Tempo", numeric("Music Tempo", "music_tempo", 50, 200, 5, "%")),
        MenuEntry("Music Volume", numeric("Music Volume", "music_volume", 0, 1023, 64, " / 1023")),
        MenuEntry("UI Theme", show_message("UI Theme", "Monochrome theme is fixed for SH1107.")),
        MenuEntry("Music Player", lambda a: a.navigation.open(MusicPlayerScreen())),
        MenuEntry("Reset Settings", reset),
        MenuEntry("Back", lambda a: a.navigation.back()),
    ]
    return submenu("Settings", [entry.label for entry in entries[:-1]],
                   dict((entry.label, entry.action) for entry in entries[:-1]))
