"""Live GPS diagnostics; no fix is shown until checksum-valid NMEA data arrives."""
from core.screen_manager import Screen
try:
    from time import ticks_ms, ticks_diff
except ImportError:
    import time
    ticks_ms = lambda: int(time.time() * 1000)
    ticks_diff = lambda newer, older: newer - older


class GPSDataScreen(Screen):
    def __init__(self, fields=None, raw=False):
        self.fields = fields
        self.raw = raw
        self.error = ""
        self.fix_was_fresh = None
        self.offset = 0

    def update(self, app):
        driver = app.hardware.get("gps")
        if driver is None:
            return False
        try:
            changed = driver.poll()
            fresh = self._fresh(driver)
            if fresh != self.fix_was_fresh:
                self.fix_was_fresh = fresh
                changed = True
            return changed
        except Exception as exc:
            self.error = str(exc)
            return True

    def render(self, app):
        driver = app.hardware.get("gps")
        if driver is None:
            lines = ["GPS: " + app.hardware.status("gps")]
            error = app.hardware.error("gps")
            lines.append(error if error else "Configure UART pins")
        elif self.error:
            lines = ["GPS read error", self.error]
        elif self.raw:
            lines = [driver.last_sentence or "Waiting for NMEA"]
        else:
            data = driver.parser.data
            fresh = self._fresh(driver)
            if not fresh:
                status = "STALE" if data["fix"] else "NO FIX"
                lines = ["Fix: " + status, "Waiting for valid NMEA"]
            else:
                values = {
                    "Latitude": _format(data["latitude"], " deg"),
                    "Longitude": _format(data["longitude"], " deg"),
                    "Altitude": _format(data["altitude_m"], " m"),
                    "Speed": _format(data["speed_kmh"], " km/h"),
                    "Satellites": _format(data["satellites"], ""),
                    "UTC": data["utc"] or "Unavailable",
                    "Date": data["date"] or "Unavailable",
                }
                lines = ["Fix: VALID"] + [key + ": " + values[key] for key in (self.fields or list(values.keys()))]
        self.lines = app.display.wrap_lines(lines)
        app.display.render_document("Raw NMEA" if self.raw else "GPS Data", lines,
                                    self.offset,
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

    def on_exit(self, app):
        app.hardware.deinitialise("gps")

    def _fresh(self, driver):
        last = driver.last_valid_fix_ms
        return (driver.parser.data["fix"] and last is not None and
                ticks_diff(ticks_ms(), last) <= 5000)


def _format(value, suffix):
    if value is None:
        return "Unavailable"
    return ("%.5f" % value if suffix == " deg" else str(value)) + suffix
