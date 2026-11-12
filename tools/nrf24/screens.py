"""Independent NRF24 module status/configuration views."""
from core.screen_manager import Screen, InformationScreen, MessageScreen


class ModuleStatusScreen(Screen):
    def __init__(self, module_name, record_name, values):
        self.module_name, self.record_name, self.values = module_name, record_name, values
        self.offset = 0

    def render(self, app):
        status = app.hardware.status(self.record_name)
        error = app.hardware.error(self.record_name)
        lines = ["Status: " + status]
        if error:
            lines.append(error)
        lines.extend(["SPI ID: " + str(self.values.get("spi_id")),
                      "SCK: " + str(self.values.get("sck")),
                      "MOSI: " + str(self.values.get("mosi")),
                      "MISO: " + str(self.values.get("miso")),
                      "CSN: " + str(self.values.get("csn")),
                      "CE: " + str(self.values.get("ce"))])
        self.lines = app.display.wrap_lines(lines)
        app.display.render_document(self.module_name, lines, self.offset,
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
    def __init__(self, module_name, record_name):
        MessageScreen.__init__(self, "NRF24 Init", "Waiting for configuration")
        self.record_name = record_name

    def render(self, app):
        app.hardware.initialise(self.record_name)
        record = app.hardware.records[self.record_name]
        if record.status == "NOT_CONFIGURED":
            self.message = "Configure pins in config.py"
        else:
            self.message = record.error if record.error else record.status
        self.total_lines = app.display.show_message(self.title, self.message, self.offset)

