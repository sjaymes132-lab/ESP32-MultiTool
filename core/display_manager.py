"""Owns the single SH1107 instance and bounded text rendering helpers."""
import config
from ui.text_renderer import TextRenderer


class DisplayManager:
    i2c_addresses = []

    def __init__(self, display, i2c=None):
        self.display = display
        self.i2c = i2c
        self.width = display.width
        self.height = display.height
        self.text_renderer = TextRenderer()

    @classmethod
    def from_hardware(cls):
        from machine import Pin, I2C
        import sh1107
        bus = I2C(0, scl=Pin(config.OLED_SCL), sda=Pin(config.OLED_SDA), freq=100000)
        devices = bus.scan()
        if config.OLED_ADDRESS not in devices:
            raise OSError("SH1107 not found at I2C 0x3C")
        display = sh1107.SH1107_I2C(config.OLED_WIDTH, config.OLED_HEIGHT, bus,
                                    address=config.OLED_ADDRESS, rotate=config.OLED_ROTATION)
        display.sleep(False)
        display.contrast(config.DISPLAY_BRIGHTNESS)
        manager = cls(display, bus)
        manager.i2c_addresses = list(devices)
        return manager

    def clear(self):
        self.display.fill(0)

    def text(self, value, x, y, color=1):
        """Draw one clipped 8x8-font line, marking truncation with an ellipsis."""
        value = self.text_renderer.fit(value, self.width - max(0, x))
        if 0 <= y < self.height and value:
            self.display.text(value, max(0, x), y, color)

    def wrap(self, value, max_chars):
        return self.text_renderer.wrap(value, max_chars)

    def wrap_lines(self, lines, max_chars=None):
        """Wrap a sequence of display lines while preserving paragraph order."""
        if max_chars is None:
            max_chars = max(1, (self.width - 8) // self.text_renderer.char_width)
        result = []
        for line in lines:
            result.extend(self.wrap(line, max_chars))
        return result

    def render_lines(self, title, lines, selected=None, scroll=0, footer="LEFT: Back",
                     marquee_key=None):
        d = self.display
        expected_key = (marquee_key, selected) if marquee_key is not None and selected is not None else None
        if expected_key is None or (self.text_renderer.state is not None and
                                    self.text_renderer.state["key"] != expected_key):
            self.text_renderer.cancel()
        d.fill(0)
        self.text(title, 0, 0)
        d.hline(0, 10, self.width, 1)
        visible = min(config.MENU_ROWS, (self.height - config.HEADER_HEIGHT - 8) // config.MENU_ROW_HEIGHT)
        for row in range(visible):
            index = scroll + row
            if index >= len(lines):
                break
            y = config.HEADER_HEIGHT + row * config.MENU_ROW_HEIGHT
            label = str(lines[index])
            if selected == index:
                d.fill_rect(0, y, self.width, config.MENU_ROW_HEIGHT, 1)
            if selected == index:
                self._draw_selected_label(label, y, marquee_key, selected)
            else:
                # Unselected rows stay static and end with an explicit ellipsis.
                self.text(" " + label, 0, y + 4, 1)
        if scroll:
            self.text("^", self.width - 8, 12)
        if scroll + visible < len(lines):
            self.text("v", self.width - 8, self.height - 16)
        if footer:
            footer = self.text_renderer.fit(footer, self.width)
            self.text(footer, 0, self.height - 8)
        d.show()

    def _draw_selected_label(self, label, y, marquee_key, index, state_key=None):
        d = self.display
        marker_width = 16
        area_width = max(0, self.width - marker_width)
        key = state_key if state_key is not None else (
            (marquee_key, index) if marquee_key is not None else None)
        long_label = self.text_renderer.measure(label) > area_width
        if long_label and key is not None and config.TEXT_MARQUEE_ENABLED:
            offset = self.text_renderer.offset_for(key, label, area_width)
            d.text(label, marker_width - offset, y + 4, 0)
            # Mask text that scrolled under the selection marker, then redraw it.
            if offset:
                d.fill_rect(0, y, marker_width, config.MENU_ROW_HEIGHT, 1)
            d.text(">", 0, y + 4, 0)
        elif long_label:
            self.text(self.text_renderer.fit(label, area_width), marker_width, y + 4, 0)
            d.text(">", 0, y + 4, 0)
        else:
            d.text(label, marker_width, y + 4, 0)
            d.text(">", 0, y + 4, 0)

    def update_marquee(self, key, label, selected, scroll):
        """Redraw just the focused menu row when its marquee moves."""
        if not config.TEXT_MARQUEE_ENABLED:
            self.text_renderer.cancel()
            return False
        state = self.text_renderer.state
        if (state is None or not isinstance(state["key"], tuple) or
                state["key"][0] is not key or state["key"][1] != selected):
            return False
        state_key = state["key"]
        if not self.text_renderer.advance(state_key):
            return False
        row = selected - scroll
        y = config.HEADER_HEIGHT + row * config.MENU_ROW_HEIGHT
        if row < 0 or y + config.MENU_ROW_HEIGHT > self.height - 8:
            return False
        d = self.display
        d.fill_rect(0, y, self.width, config.MENU_ROW_HEIGHT, 1)
        self._draw_selected_label(label, y, key, selected, state_key)
        d.show()
        return True

    def render_document(self, title, lines, offset=0, footer="LEFT: Back"):
        """Render wrapped information with a fixed title and vertically scrollable body."""
        self.text_renderer.cancel()
        lines = self.wrap_lines(lines)
        d = self.display
        d.fill(0)
        self.text(title, 0, 0)
        d.hline(0, 10, self.width, 1)
        body_y = 20
        footer_y = self.height - 8
        rows = max(1, (footer_y - body_y) // 8)
        start = max(0, min(offset, max(0, len(lines) - rows)))
        for row in range(rows):
            index = start + row
            if index >= len(lines):
                break
            self.text(lines[index], 0, body_y + row * 8)
        if start:
            self.text("^", self.width - 8, body_y)
        if start + rows < len(lines):
            self.text("v", self.width - 8, body_y + (rows - 1) * 8)
        if footer:
            self.text(footer, 0, footer_y)
        d.show()
        return len(lines)

    def render_confirmation(self, title, lines, offset=0, selected=0):
        """Show a long confirmation prompt with wrapped, scrollable text and fixed choices."""
        self.text_renderer.cancel()
        lines = self.wrap_lines(lines)
        d = self.display
        d.fill(0)
        self.text(title, 0, 0)
        d.hline(0, 10, self.width, 1)
        body_y = 20
        body_rows = 7
        start = max(0, min(offset, max(0, len(lines) - body_rows)))
        for row in range(body_rows):
            index = start + row
            if index >= len(lines):
                break
            self.text(lines[index], 0, body_y + row * 8)
        if start:
            self.text("^", self.width - 8, body_y)
        if start + body_rows < len(lines):
            self.text("v", self.width - 8, body_y + (body_rows - 1) * 8)
        options = ("No", "Yes")
        for index in range(2):
            y = 84 + index * 16
            if selected == index:
                d.fill_rect(0, y, self.width, 16, 1)
            d.text(">" if selected == index else " ", 0, y + 4,
                   0 if selected == index else 1)
            d.text(options[index], 16, y + 4, 0 if selected == index else 1)
        self.text("UP/DN Text R Tog", 0, self.height - 8)
        d.show()
        return len(lines)

    def show_message(self, title, message, offset=0):
        lines = self.wrap(message, max(1, (self.width - 8) // 8))
        self.render_document(title, lines, offset,
                             "UP/DN Scroll L" if len(lines) > 12 else "SELECT: Back")
        return len(lines)

