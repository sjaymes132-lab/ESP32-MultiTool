"""Temporary BLE observation screens; IRQ work stays in a fixed-size queue."""
from core.screen_manager import Screen, InformationScreen
from hardware.bluetooth.advertising import AdvertisementQueue, parse_advertisement
try:
    from time import ticks_ms, ticks_diff, ticks_add
except ImportError:
    import time
    ticks_ms = lambda: int(time.time() * 1000)
    ticks_diff = lambda newer, older: newer - older
    ticks_add = lambda value, delta: value + delta

MAX_OBSERVATIONS = 24
EVENT_SCAN_RESULT = 5
EVENT_SCAN_DONE = 6


def _lease(app, owner):
    radio = getattr(app, "radio", None)
    return True if radio is None else radio.acquire(owner)


def _release(app, owner):
    radio = getattr(app, "radio", None)
    if radio is not None:
        radio.release(owner)


def _block_if_uncertain(app, adapter):
    if adapter is not None and getattr(adapter, "scan_failed", False):
        radio = getattr(app, "radio", None)
        if radio is not None:
            radio.block("BLE state uncertain after native error; restart required")


def _failure_text(stage, exc):
    name = type(exc).__name__
    args = getattr(exc, "args", ())
    if name == "OSError" and args and isinstance(args[0], int):
        detail = "OSError errno %d: %s" % (args[0], str(exc))
    else:
        detail = name + ": " + str(exc)
    return "%s failed: %s" % (stage, detail)


def _radio_busy_text(app, default):
    radio = getattr(app, "radio", None)
    reason = getattr(radio, "failure_reason", None) if radio is not None else None
    return "Radio unavailable: " + reason if reason else default


def _address_text(address):
    return ":".join("%02X" % byte for byte in address)


def observation_text(row):
    info = row["advertisement"]
    lines = ["Name: " + (row["name"] or "(not advertised)"),
             "Address: " + row["address"], "RSSI: %d dBm" % row["rssi"],
             "Adv type: %d" % row["adv_type"], "Seen: %d ms ago" %
             max(0, ticks_diff(ticks_ms(), row["last_seen"]))]
    if info["manufacturer"]:
        lines.append("Maker: " + info["manufacturer"])
    if info["service_uuids"]:
        lines.append("Services: " + ", ".join(info["service_uuids"]))
    if info["ibeacon"]:
        beacon = info["ibeacon"]
        lines.extend(["iBeacon UUID:", beacon["uuid"], "Major/minor: %d/%d" %
                      (beacon["major"], beacon["minor"]), "TX power: %d dBm" % beacon["tx_power"]])
    if info["malformed"]:
        lines.append("Malformed advertisement data")
    return "\n".join(lines)


class BLEScanScreen(Screen):
    def __init__(self, app=None, live=False, ibeacon_only=False):
        self.app = app
        self.live = live
        self.ibeacon_only = ibeacon_only
        self.ble = None
        self.queue = AdvertisementQueue(16, 62)
        self.devices = []
        self.selected = 0
        self.status = "SELECT to scan"
        self.scanning = False
        self.scan_done = False
        self.cancel_requested = False
        self.deadline = 0
        self.last_refresh = ticks_ms()
        self.irq_errors = 0
        self.seen_events = 0
        self.dropped = 0
        self.scan_count = 0
        self.pending_redraw = False
        self.display_labels = []
        self.redraw_interval_ms = 150
        self.duration_ms = 8000
        self.interval_us = None
        self.window_us = None
        if app is not None and getattr(app, "settings", None) is not None:
            self.duration_ms = app.settings.get("ble_scan_duration_ms") or 8000
            self.interval_us = app.settings.get("ble_scan_interval_us")
            self.window_us = app.settings.get("ble_scan_window_us")

    def _irq(self, event, data):
        # Only copy bounded bytes and set flags here. Parsing, formatting, list
        # updates, UI calls and file operations all run in Screen.update().
        if event == EVENT_SCAN_RESULT:
            try:
                addr_type, address, adv_type, rssi, adv_data = data
                if self.queue.push(addr_type, address, adv_type, rssi, adv_data):
                    if self.seen_events < 0x7FFFFFFF:
                        self.seen_events += 1
            except Exception:
                if self.irq_errors < 0x7FFFFFFF:
                    self.irq_errors += 1
        elif event == EVENT_SCAN_DONE:
            self.scan_done = True

    def _start(self):
        if self.scanning:
            self.status = "Scan already active"
            return
        if not _lease(self.app, "ble_scan"):
            self.status = _radio_busy_text(self.app, "Radio busy: Wi-Fi scan/monitor active")
            return
        self.scan_done = False
        self.cancel_requested = False
        self.queue.clear()
        self.devices = []
        self.display_labels = []
        if self.app is not None:
            self.app.ble_devices = self.devices
        self.selected = 0
        stage = "BLE adapter initialization"
        try:
            self.ble = self.app.hardware.initialise("bluetooth")
            if self.ble is None:
                raise RuntimeError(self.app.hardware.error("bluetooth") or "BLE unavailable")
            # Required MicroPython order: activate/verify before other BLE APIs.
            stage = "BLE activation"
            self.ble.activate()
            stage = "BLE IRQ registration"
            self.ble.irq(self._irq)
            stage = "BLE scan startup (gap_scan)"
            self.ble.scan(self.duration_ms, self.interval_us, self.window_us)
            self.scanning = True
            self.status = "Scanning... SELECT stops"
            self.deadline = ticks_add(ticks_ms(), self.duration_ms + 1000)
            self.last_refresh = ticks_ms()
        except Exception as exc:
            stage = getattr(self.ble, "last_stage", stage) if self.ble is not None else stage
            self.status = _failure_text(stage, exc)
            _block_if_uncertain(self.app, self.ble)
            if self.ble is not None:
                # A gap_scan native error leaves controller state uncertain;
                # do not issue speculative stop/deactivate calls in that case.
                if not getattr(self.ble, "scan_failed", False):
                    try:
                        self.ble.deactivate()
                    except Exception as cleanup_error:
                        self.status += " / cleanup: " + str(cleanup_error)
                self.app.hardware.fail("bluetooth", exc)
            self.ble = None
            _release(self.app, "ble_scan")

    def _process_queue(self, limit=8):
        changed = False
        for _ in range(limit):
            item = self.queue.pop()
            if item is None:
                break
            address_type, address, adv_type, rssi, payload = item
            parsed = parse_advertisement(payload)
            if self.ibeacon_only and parsed["ibeacon"] is None:
                continue
            address_string = _address_text(address)
            key = (address_type, address_string)
            found = None
            for row in self.devices:
                if row["key"] == key:
                    found = row
                    break
            if found is None:
                if len(self.devices) >= MAX_OBSERVATIONS:
                    # Replace the least recently observed item; never grow RAM.
                    oldest = 0
                    for index in range(1, len(self.devices)):
                        if ticks_diff(self.devices[index]["last_seen"],
                                      self.devices[oldest]["last_seen"]) < 0:
                            oldest = index
                    found = self.devices[oldest]
                    found.clear()
                    found["key"] = key
                    found["sightings"] = 0
                else:
                    found = {"key": key, "sightings": 0}
                    self.devices.append(found)
            found.update({"address_type": address_type, "address": address_string,
                          "adv_type": adv_type, "rssi": rssi,
                          "name": parsed["name"], "advertisement": parsed,
                          "last_seen": ticks_ms(), "sightings": min(0x7FFFFFFF,
                              found["sightings"] + 1)})
            changed = True
        if self.app is not None:
            self.app.ble_devices = self.devices
        self.dropped = self.queue.dropped
        return changed

    def update(self, app):
        changed = self._process_queue()
        if changed:
            self.pending_redraw = True
        now = ticks_ms()
        if self.scanning and (self.scan_done or ticks_diff(now, self.deadline) >= 0):
            if self.live and not self.cancel_requested and self.scan_done:
                # A bounded repeated scan for live discovery; no recursive loop.
                self.scan_done = False
                self.ble.scan_done()
                try:
                    self.ble.scan(self.duration_ms, self.interval_us, self.window_us)
                    self.deadline = ticks_add(now, self.duration_ms + 1000)
                    if self.scan_count < 0x7FFFFFFF:
                        self.scan_count += 1
                    self.status = "Live scan %d; SEL stops" % self.scan_count
                except Exception as exc:
                    self._fail(app, exc)
                return True
            self.scanning = False
            adapter = self.ble
            try:
                if self.scan_done:
                    adapter.scan_done()
                adapter.deactivate()
                self.status = "Scan complete" if self.scan_done else "Scan timed out"
            except Exception as exc:
                stage = getattr(adapter, "last_stage", "BLE stop")
                self.status = _failure_text(stage, exc)
                _block_if_uncertain(app, adapter)
                app.hardware.fail("bluetooth", exc)
            self.ble = None
            _release(app, "ble_scan")
            self.pending_redraw = False
            return True
        if self.pending_redraw and ticks_diff(now, self.last_refresh) >= self.redraw_interval_ms:
            self.last_refresh = now
            self.pending_redraw = False
            return True
        if self.display_labels:
            self.selected = max(0, min(self.selected, len(self.display_labels) - 1))
            scroll = max(0, min(self.selected - 5, len(self.display_labels) - 6))
            app.display.update_marquee(self, self.display_labels[self.selected], self.selected, scroll)
        return False

    def _fail(self, app, exc):
        stage = getattr(self.ble, "last_stage", "BLE scan") if self.ble is not None else "BLE scan"
        self.status = _failure_text(stage, exc)
        if self.ble is not None:
            _block_if_uncertain(app, self.ble)
            if not getattr(self.ble, "scan_failed", False):
                try:
                    self.ble.deactivate()
                except Exception as cleanup_error:
                    self.status += " / cleanup: " + str(cleanup_error)
            app.hardware.fail("bluetooth", exc)
        self.ble = None
        self.scanning = False
        _release(app, "ble_scan")

    def render(self, app):
        self.dropped = self.queue.dropped
        if not self.devices:
            footer = "SEL Stop" if self.scanning else "SEL Scan R Scan"
            app.display.render_document("BLE Scanner", [self.status,
                "Events: %d" % self.seen_events, "Queue drops: %d" % self.dropped,
                "IRQ errors: %d" % self.irq_errors], 0, footer)
            return
        rows = sorted(self.devices, key=lambda row: row["rssi"], reverse=True)
        self.selected = max(0, min(self.selected, len(rows) - 1))
        self.display_rows = rows
        labels = ["%s %ddBm" % (row["name"] or row["address"][-8:], row["rssi"])
                  for row in rows]
        self.display_labels = labels
        scroll = max(0, min(self.selected - 5, len(labels) - 6))
        footer = "SEL Stop" if self.scanning else "SEL Details R Scan"
        app.display.render_lines("BLE " + str(len(rows)), labels, self.selected, scroll,
                                 footer, marquee_key=self)

    def handle(self, app, button):
        if button == "left":
            app.navigation.back()
            return True
        if button in ("up", "down") and self.devices:
            self.selected = max(0, min(len(self.devices) - 1,
                                       self.selected + (-1 if button == "up" else 1)))
            return True
        if button == "select":
            if self.scanning:
                self.cancel_requested = True
                self.live = False
                try:
                    self.ble.deactivate()
                    self.status = "Scan stopped"
                except Exception as exc:
                    stage = getattr(self.ble, "last_stage", "BLE stop")
                    self.status = _failure_text(stage, exc)
                    _block_if_uncertain(app, self.ble)
                    app.hardware.fail("bluetooth", exc)
                self.scanning = False
                self.ble = None
                _release(app, "ble_scan")
                return True
            if self.devices:
                rows = getattr(self, "display_rows", self.devices)
                app.navigation.open(InformationScreen("BLE Device", observation_text(rows[self.selected])))
                return True
            self._start()
            return True
        if button == "right":
            if self.scanning:
                self.status = "Scan already active"
            else:
                self._start()
            return True
        return False

    def on_exit(self, app):
        if self.scanning and self.ble is not None:
            try:
                self.ble.deactivate()
            except Exception as exc:
                _block_if_uncertain(app, self.ble)
                app.hardware.fail("bluetooth", exc)
            self.scanning = False
            self.ble = None
        _release(app, "ble_scan")


def status_lines(app):
    ble = None
    try:
        ble = app.hardware.initialise("bluetooth")
        if ble is None:
            return ["BLE unavailable", app.hardware.error("bluetooth")]
        return ["BLE API: available", "Active: " + str(ble.active())]
    except Exception as exc:
        radio = getattr(app, "radio", None)
        if radio is not None and getattr(ble, "scan_failed", False):
            radio.block("BLE state uncertain after native status error; restart required")
        app.hardware.fail("bluetooth", exc)
        return ["BLE unavailable", str(exc)]


class BLEInitTestScreen(Screen):
    """Explicit user-triggered activation/deactivation diagnostic."""
    def __init__(self):
        self.status = "SELECT to test adapter"

    def render(self, app):
        app.display.render_document("BLE Init Test", [self.status,
            "Test runs only on selection."], 0, "SELECT: Test L Back")

    def handle(self, app, button):
        if button == "left":
            app.navigation.back()
            return True
        if button != "select":
            return False
        if not _lease(app, "ble_diagnostics"):
            self.status = _radio_busy_text(app, "Radio busy with another scan")
            return True
        ble = None
        stage = "BLE adapter initialization"
        try:
            ble = app.hardware.initialise("bluetooth")
            if ble is None:
                raise RuntimeError(app.hardware.error("bluetooth") or "BLE unavailable")
            stage = "BLE activation"
            ble.activate()
            self.status = "Activation succeeded"
            stage = "BLE deactivation"
            ble.deactivate()
            self.status = "Activation and cleanup succeeded"
        except Exception as exc:
            stage = getattr(ble, "last_stage", stage) if ble is not None else stage
            self.status = _failure_text(stage, exc)
            if ble is not None:
                _block_if_uncertain(app, ble)
                app.hardware.fail("bluetooth", exc)
        finally:
            _release(app, "ble_diagnostics")
        return True
