"""Menu screen implementation using the shared SH1107 display manager."""
from core.screen_manager import Screen


class MenuEntry:
    def __init__(self, label, action):
        self.label = label
        self.action = action


class MenuScreen(Screen):
    def __init__(self, title, entries):
        self.title = title
        self.entries = list(entries)
        self.selected = 0

    def render(self, app):
        labels = [entry.label for entry in self.entries]
        first = self._scroll_top(len(labels))
        footer = "UP/DN Move SEL Go" if len(app.navigation.stack) == 1 else "L:Back SEL:Open"
        app.display.render_lines(self.title, labels, self.selected, first, footer,
                                 marquee_key=self)

    def _scroll_top(self, count):
        return max(0, min(self.selected - 5, max(0, count - 6)))

    def update(self, app):
        if not self.entries:
            return False
        labels = self.entries[self.selected].label
        app.display.update_marquee(self, labels, self.selected,
                                   self._scroll_top(len(self.entries)))
        # update_marquee draws and flushes only its dirty display pages itself.
        return False

    def on_exit(self, app):
        app.display.text_renderer.cancel()

    def handle(self, app, button):
        if button == "left":
            app.navigation.back()
            return True
        if button == "up":
            self.selected = max(0, self.selected - 1)
        elif button == "down":
            self.selected = min(len(self.entries) - 1, self.selected + 1)
        elif button in ("select", "right"):
            if self.entries:
                action = self.entries[self.selected].action
                try:
                    action(app)
                except Exception as exc:
                    app.show_message("Action error", str(exc))
        else:
            return False
        return True
