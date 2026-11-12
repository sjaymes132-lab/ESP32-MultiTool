"""Independent CC1101 module status/configuration views."""
from core.screen_manager import Screen, MessageScreen


class ModuleStatusScreen(Screen):
    def __init__(self, name, record, values):
        self.name, self.record, self.values = name, record, values
        self.offset = 0

    def render(self, app):
        lines = ["Status: " + app.hardware.status(self.record)]
        error = app.hardware.error(self.record)
        if error:
            lines.append(error)
        for field in ("spi_id", "sck", "mosi", "miso", "csn", "gdo0", "gdo2"):
            lines.append("%s: %s" % (field.upper(), self.values.get(field)))
        self.lines = app.display.wrap_lines(lines)
        app.display.render_document(self.name, lines, self.offset,
                                    "UP/DN Scroll L" if len(self.lines) > 12 else "LEFT: Back")

    def handle(self, app, button):
        if button in ("up", "down"):
            self.offset = max(0, min(max(0, len(getattr(self, "lines", [])) - 12),
                                     self.offset + (1 if button == "down" else -1)))
            return True
        if button == "left":
            app.navigation.back()
            return True
        return False


class InitialiseScreen(MessageScreen):
    def __init__(self, name, record):
        MessageScreen.__init__(self, "CC1101 Init", "Waiting for configuration")
        self.record = record

    def render(self, app):
        app.hardware.initialise(self.record)
        record = app.hardware.records[self.record]
        if record.status == "NOT_CONFIGURED":
            self.message = "Configure pins in config.py"
        else:
            self.message = record.error if record.error else record.status
        self.total_lines = app.display.show_message(self.title, self.message, self.offset)

