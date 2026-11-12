"""Settings controls and non-blocking music-player screen."""
from core.screen_manager import Screen, MessageScreen


class NumericSettingScreen(Screen):
    def __init__(self, title, key, minimum, maximum, step, suffix, app):
        self.title, self.key = title, key
        self.minimum, self.maximum, self.step, self.suffix = minimum, maximum, step, suffix
        self.value = app.settings.get(key)
        self.persisted = self.value
        self.status = "UP/DN adjust SEL save"

    def render(self, app):
        app.display.render_lines(self.title,
            ["Value: %s%s" % (self.value, self.suffix), self.status],
            footer="L Cancel R Save")

    def _save(self, app):
        if not app.settings.set(self.key, self.value):
            self.status = "Save failed"
            return False
        app.settings.apply(app)
        self.persisted = self.value
        self.status = "Saved"
        return True

    def handle(self, app, button):
        if button == "left":
            if self.key == "brightness":
                app.display.display.contrast(self.persisted)
            app.navigation.back()
            return True
        if button in ("up", "down"):
            delta = self.step if button == "up" else -self.step
            self.value = max(self.minimum, min(self.maximum, self.value + delta))
            self.status = "Pending; SELECT saves"
            if self.key == "brightness":
                app.display.display.contrast(self.value)
            return True
        if button == "select":
            self._save(app)
            return True
        if button == "right":
            if self._save(app):
                app.navigation.back()
            return True
        return False


class ToggleSettingScreen(Screen):
    def __init__(self, title, key, app):
        self.title, self.key = title, key
        self.message = "SELECT: Toggle"

    def render(self, app):
        value = app.settings.get(self.key)
        lines = ["State: " + ("ON" if value else "OFF")]
        if self.key in ("sound_enabled", "ui_sounds_enabled") and app.sound.buzzer is None:
            lines.append("Buzzer: unavailable")
        lines.append(self.message)
        app.display.render_lines(self.title, lines, footer="LEFT: Back")

    def handle(self, app, button):
        if button == "left":
            app.navigation.back()
            return True
        if button in ("select", "right"):
            result = app.settings.set(self.key, not app.settings.get(self.key))
            app.settings.apply(app)
            self.message = "Saved" if result else "Save failed"
            app.invalidate()
            return True
        return False


class MusicPlayerScreen(Screen):
    def render(self, app):
        player = app.music
        tune = player.current_tune()
        current, total = player.progress()
        if app.sound.buzzer is None:
            state = "NO BUZZER"
        elif not app.sound.enabled:
            state = "SOUND OFF"
        else:
            state = "PLAYING" if player.playing else ("PAUSED" if player.paused else "STOPPED")
        lines = [tune["name"], state, "Note: %d/%d" % (min(current + 1, total), total),
                 "Tempo: %d%%" % player.tempo, "UP/DN Tune/Tempo", "SEL Play R Next"]
        app.display.render_lines("Music Player", lines, footer="LEFT: Stop")
        d = app.display.display
        d.rect(2, 104, 124, 7, 1)
        if total:
            d.fill_rect(3, 105, max(1, (122 * current) // total), 5, 1)
        d.show()

    def handle(self, app, button):
        player = app.music
        if button == "left":
            player.stop()
            app.navigation.back()
        elif button == "up":
            if player.playing:
                player.adjust_tempo(5)
            else:
                player.select(player.index - 1)
        elif button == "down":
            if player.playing:
                player.adjust_tempo(-5)
            else:
                player.select(player.index + 1)
        elif button == "right":
            player.next(1)
        elif button == "select":
            player.toggle()
        else:
            return False
        return True

    def on_exit(self, app):
        app.music.stop()

