"""Lightweight text layout and one-at-a-time menu marquee support.

The bundled SH1107 driver uses MicroPython's built-in 8x8 framebuffer font.
All measurements therefore use fixed-width 8-pixel character cells.
"""
import config

try:
    from time import ticks_ms, ticks_diff
except ImportError:
    import time
    ticks_ms = lambda: int(time.time() * 1000)
    ticks_diff = lambda newer, older: newer - older


class TextRenderer:
    def __init__(self, char_width=8):
        self.char_width = char_width
        self.state = None

    def measure(self, text):
        return len(str(text)) * self.char_width

    def fit(self, text, width_px, ellipsis=True):
        """Return a complete short label or an explicit ellipsis-truncated one."""
        text = str(text)
        limit = max(0, width_px // self.char_width)
        if len(text) <= limit:
            return text
        if not ellipsis or limit <= 0:
            return text[:limit]
        if limit <= 3:
            return "." * limit
        return text[:limit - 3] + "..."

    def wrap(self, text, width_chars):
        """Wrap paragraphs on words, splitting only unbroken overlong tokens."""
        width_chars = max(1, int(width_chars))
        lines = []
        for paragraph in str(text).split("\n"):
            words = paragraph.split()
            if not words:
                lines.append("")
                continue
            line = ""
            for word in words:
                while len(word) > width_chars:
                    if line:
                        lines.append(line)
                        line = ""
                    lines.append(word[:width_chars])
                    word = word[width_chars:]
                if not word:
                    continue
                candidate = word if not line else line + " " + word
                if len(candidate) > width_chars:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            if line:
                lines.append(line)
        return lines or [""]

    def _new_state(self, key, text, width_px, now):
        overflow = max(0, self.measure(text) - width_px)
        self.state = {
            "key": key, "text": text, "width": width_px,
            "overflow": overflow, "offset": 0, "phase": "delay",
            "last": now,
        }

    def offset_for(self, key, text, width_px, now=None):
        """Get the current marquee offset, resetting when the focused label changes."""
        text = str(text)
        if now is None:
            now = ticks_ms()
        if not getattr(config, "TEXT_MARQUEE_ENABLED", True):
            self.cancel()
            return 0
        if self.measure(text) <= width_px:
            self.cancel()
            return 0
        if (self.state is None or self.state["key"] != key or
                self.state["text"] != text or self.state["width"] != width_px):
            self._new_state(key, text, width_px, now)
        return self.state["offset"]

    def advance(self, key, now=None):
        """Advance animation state without sleeping; return True when pixels moved."""
        state = self.state
        if state is None or state["key"] != key:
            return False
        if now is None:
            now = ticks_ms()
        elapsed = ticks_diff(now, state["last"])
        phase = state["phase"]
        moved = False
        if phase == "delay":
            if elapsed >= config.TEXT_MARQUEE_START_DELAY_MS:
                state["phase"] = "forward"
                state["last"] = now
        elif phase == "end_pause":
            if elapsed >= config.TEXT_MARQUEE_END_PAUSE_MS:
                state["phase"] = "return"
                state["last"] = now
        elif phase == "start_pause":
            if elapsed >= config.TEXT_MARQUEE_START_DELAY_MS:
                state["phase"] = "forward"
                state["last"] = now
        elif elapsed >= config.TEXT_MARQUEE_STEP_MS:
            steps = elapsed // config.TEXT_MARQUEE_STEP_MS
            state["last"] = now
            if phase == "forward":
                offset = min(state["overflow"], state["offset"] + steps)
                moved = offset != state["offset"]
                state["offset"] = offset
                if offset >= state["overflow"]:
                    state["phase"] = "end_pause"
            else:
                offset = max(0, state["offset"] - steps)
                moved = offset != state["offset"]
                state["offset"] = offset
                if offset <= 0:
                    state["phase"] = "start_pause"
        return moved

    def cancel(self):
        self.state = None
