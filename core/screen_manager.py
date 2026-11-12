"""Reusable screen types and the render/event contract."""
class Screen:
    def update(self, app):
        return False

    def render(self, app):
        pass

    def handle(self, app, button):
        return False

    def on_exit(self, app):
        pass


class MessageScreen(Screen):
    def __init__(self, title, message):
        self.title, self.message = title, message
        self.offset = 0
        self.total_lines = 0

    def render(self, app):
        self.total_lines = app.display.show_message(self.title, self.message, self.offset)

    def handle(self, app, button):
        if button in ("up", "down") and self.total_lines > 12:
            maximum = self.total_lines - 12
            self.offset = max(0, min(maximum, self.offset + (1 if button == "down" else -1)))
            return True
        if button in ("select", "right", "left"):
            app.navigation.back()
            return True
        return False


class InformationScreen(Screen):
    def __init__(self, title, text):
        self.title = title
        self.text = str(text)
        self.lines = []
        self.offset = 0

    def render(self, app):
        self.lines = app.display.wrap(self.text, max(1, (app.display.width - 8) // 8))
        app.display.render_document(self.title, self.lines, self.offset,
                                    "UP/DN Scroll L" if len(self.lines) > 12 else "LEFT: Back")

    def handle(self, app, button):
        page = 12
        if button == "down":
            self.offset = min(max(0, len(self.lines) - page), self.offset + 1)
        elif button == "up":
            self.offset = max(0, self.offset - 1)
        elif button in ("left", "select", "right"):
            app.navigation.back()
        else:
            return False
        return True


class SelectableListScreen(Screen):
    def __init__(self, title, items, on_select=None):
        self.title, self.items, self.on_select, self.selected = title, list(items), on_select, 0

    def render(self, app):
        first = max(0, min(self.selected - 5, max(0, len(self.items) - 6)))
        app.display.render_lines(self.title, self.items, self.selected, first,
                                 marquee_key=self)

    def update(self, app):
        if not self.items:
            return False
        first = max(0, min(self.selected - 5, max(0, len(self.items) - 6)))
        app.display.update_marquee(self, self.items[self.selected], self.selected, first)
        # The shared renderer has already flushed only the affected SH1107 pages.
        return False

    def handle(self, app, button):
        if button == "up":
            self.selected = max(0, self.selected - 1)
        elif button == "down":
            self.selected = min(max(0, len(self.items) - 1), self.selected + 1)
        elif button in ("select", "right"):
            if self.items and self.on_select:
                self.on_select(self.items[self.selected])
            else:
                app.navigation.back()
        elif button == "left":
            app.navigation.back()
        else:
            return False
        return True


class ConfirmationScreen(SelectableListScreen):
    def __init__(self, title, message, on_yes):
        self.message, self.on_yes = message, on_yes
        self.message_lines = []
        self.message_offset = 0
        self.long_message = False
        SelectableListScreen.__init__(self, title, ["No", "Yes"])

    def render(self, app):
        message_lines = app.display.wrap(self.message, 15)
        self.message_lines = message_lines
        self.long_message = len(message_lines) > 4
        if self.long_message:
            app.display.render_confirmation(self.title, message_lines,
                                            self.message_offset, self.selected)
            return
        message_lines = message_lines[:4]
        lines = message_lines + self.items
        app.display.render_lines(self.title, lines,
                                 self.selected + len(message_lines),
                                 marquee_key=self)

    def handle(self, app, button):
        if self.long_message:
            if button in ("up", "down"):
                maximum = max(0, len(self.message_lines) - 7)
                self.message_offset = max(0, min(maximum, self.message_offset +
                                                 (1 if button == "down" else -1)))
                return True
            if button == "right":
                self.selected = 1 - self.selected
                return True
            if button == "left":
                app.navigation.back()
                return True
            if button != "select":
                return False
            result = None
            if self.selected == 1:
                try:
                    result = self.on_yes()
                except Exception as exc:
                    result = "Action failed: " + str(exc)
            app.navigation.back()
            if result:
                app.show_message(self.title, result)
            return True
        if button in ("up", "down"):
            self.selected = 0 if button == "up" else 1
            return True
        if button in ("left", "select", "right"):
            result = None
            if button in ("right", "select") and self.selected == 1:
                try:
                    result = self.on_yes()
                except Exception as exc:
                    result = "Action failed: " + str(exc)
            app.navigation.back()
            if result:
                app.show_message(self.title, result)
            return True
        return False


class PlaceholderScreen(MessageScreen):
    def __init__(self, title):
        MessageScreen.__init__(self, title, "Not implemented yet. This entry is ready for future tool integration.")


class InputMonitorScreen(Screen):
    """Live read-only view of the shared, debounced joystick state."""
    def render(self, app):
        state = app.input.current_state()
        lines = ["%s: %s" % (button.upper(), "DOWN" if state[button] else "UP")
                 for button in app.input.BUTTONS]
        app.display.render_lines("Input Test", lines, footer="LEFT: Back")

    def handle(self, app, button):
        if button == "left":
            app.navigation.back()
        else:
            app.invalidate()
        return True


def DisplayWrap(text, width):
    # Backwards-compatible helper for integrations using the old function.
    from ui.text_renderer import TextRenderer
    return TextRenderer().wrap(text, width)
