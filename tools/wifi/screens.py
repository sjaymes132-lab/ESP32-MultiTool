"""Bounded Wi-Fi scan, AP analysis, monitor and feature-detected CSI screens."""
from core.screen_manager import Screen, InformationScreen
from tools.wifi.analysis import bounded_scan_results, sort_results, statistics, filter_results
from hardware.wifi.driver import heap_snapshot
from tools.wifi.storage import load_sessions, save_session, export_csv
try:
    from time import ticks_ms, ticks_diff
except ImportError:
    import time
    ticks_ms = lambda: int(time.time() * 1000)
    ticks_diff = lambda newer, older: newer - older

MAX_RESULTS = 24


def wifi_error_text(exc):
    """Keep Python heap failures distinct from native WLAN OSErrors."""
    if isinstance(exc, MemoryError):
        return "MemoryError: MicroPython heap allocation failed"
    if isinstance(exc, OSError):
        args = getattr(exc, "args", ())
        if args and isinstance(args[0], int):
            return "OSError errno %d: %s" % (args[0], str(exc))
        return "OSError: " + str(exc)
    return type(exc).__name__ + ": " + str(exc)


def _heap_kb(value):
    return "n/a" if value is None else "%dKB" % (value // 1024)


def _wlan(app):
    wlan = app.hardware.initialise("wifi")
    if wlan is None:
        detail = getattr(app.hardware, "error_detail", None)
        if detail is not None:
            reason = detail("wifi")
        else:
            reason = app.hardware.error("wifi")
        raise RuntimeError("Wi-Fi adapter initialization failed: " +
                           (reason or "Wi-Fi unavailable"))
    return wlan


def _lease(app, owner):
    radio = getattr(app, "radio", None)
    return True if radio is None else radio.acquire(owner)


def _release(app, owner):
    radio = getattr(app, "radio", None)
    if radio is not None:
        radio.release(owner)


def _block_radio_if_uncertain(app, reason):
    radio = getattr(app, "radio", None)
    if radio is not None:
        radio.block(reason)


def _radio_busy_text(app, fallback):
    radio = getattr(app, "radio", None)
    reason = getattr(radio, "failure_reason", None) if radio is not None else None
    return "Radio unavailable: " + reason if reason else fallback


class NetworkScanScreen(Screen):
    """Threaded user-requested AP scan with bounded results and cancellation."""
    def __init__(self, app, live=False, initial_results=None, query=""):
        self.app = app
        self.live = live
        self.results = [] if initial_results is None else list(initial_results)
        self.query = query
        self.started = initial_results is not None
        self.running = False
        self.cancel_requested = False
        self.error = ""
        self.status = "SELECT to scan"
        self.sort_mode = "rssi"
        self.selected = 0
        self.last_refresh = ticks_ms()
        self.last_update = 0
        self.scan_count = 0
        self.version = 0
        self.rendered_version = 0
        self.display_labels = []
        self.total_found = 0
        self.heap_free_before = None
        self.heap_free_native_after = None
        self.heap_free_processed_after = None
        self.heap_free_pre_thread = None
        self.heap_free_worker_start = None
        self.heap_alloc_pre_thread = None
        self.heap_alloc_worker_start = None
        self.heap_diagnostic_error = ""
        self.raw_result_count = 0
        self.failure_stage = ""
        self.live_interval_ms = 2000
        self.result_limit = 24
        if getattr(app, "settings", None) is not None:
            self.live_interval_ms = app.settings.get("wifi_live_interval_ms") or 2000
            self.result_limit = app.settings.get("wifi_result_limit") or 24

    def _start_worker(self):
        if self.running:
            self.cancel_requested = True
            self.live = False
            self.status = "Stopping after current scan"
            return
        if not _lease(self.app, "wifi_scan"):
            self.status = _radio_busy_text(self.app, "Radio busy: another scan is active")
            return
        self.results = []
        self.app.wifi_scan_results = self.results
        self.display_labels = []
        self.total_found = 0
        self.heap_free_before = None
        self.heap_free_native_after = None
        self.heap_free_processed_after = None
        self.heap_free_worker_start = None
        self.heap_free_pre_thread = None
        self.heap_alloc_pre_thread = None
        self.heap_alloc_worker_start = None
        self.heap_diagnostic_error = ""
        self.raw_result_count = 0
        self.failure_stage = ""
        try:
            (self.heap_free_pre_thread, self.heap_alloc_pre_thread,
             self.heap_diagnostic_error) = heap_snapshot(collect=True)
        except Exception:
            self.heap_diagnostic_error = "pre-thread heap snapshot failed"
        self.running = True
        self.started = True
        self.cancel_requested = False
        self.error = ""
        self.status = "Scanning nearby APs"
        self.last_refresh = ticks_ms()
        try:
            import _thread
            _thread.start_new_thread(self._worker, ())
        except Exception as exc:
            self.running = False
            _release(self.app, "wifi_scan")
            self.failure_stage = "Wi-Fi worker startup"
            try:
                (self.heap_free_worker_start, self.heap_alloc_worker_start,
                 self.heap_diagnostic_error) = heap_snapshot(collect=True)
            except Exception as diagnostic_exc:
                self.heap_diagnostic_error = "worker-start heap snapshot: " + str(diagnostic_exc)
            self.error = self.failure_stage + ": " + wifi_error_text(exc)
            self.status = "Scan failed"

    def _worker(self):
        try:
            try:
                (self.heap_free_worker_start, self.heap_alloc_worker_start,
                 diagnostic_error) = heap_snapshot(collect=True)
                if diagnostic_error:
                    self.heap_diagnostic_error = diagnostic_error
            except Exception as diagnostic_exc:
                self.heap_diagnostic_error = "worker heap snapshot: " + str(diagnostic_exc)
            self.failure_stage = "Wi-Fi adapter initialization"
            wlan = _wlan(self.app)
            while not self.cancel_requested:
                # Do not keep the previous native result tuples alive during
                # the next WLAN.scan() allocation.
                self.results = []
                self.app.wifi_scan_results = self.results
                self.display_labels = []
                self.heap_free_before = None
                self.heap_free_native_after = None
                self.heap_free_processed_after = None
                self.heap_diagnostic_error = ""
                self.raw_result_count = 0
                self.failure_stage = "Pre-scan heap snapshot"
                try:
                    _, _, diagnostic_error = heap_snapshot(collect=True)
                    if diagnostic_error:
                        self.heap_diagnostic_error = diagnostic_error
                except Exception as diagnostic_exc:
                    self.heap_diagnostic_error = "pre-scan heap snapshot: " + str(diagnostic_exc)
                self.failure_stage = "WLAN.scan()"
                try:
                    raw = wlan.scan()
                except Exception as exc:
                    self.failure_stage = getattr(wlan, "last_stage", self.failure_stage)
                    self.heap_free_before = getattr(wlan, "heap_free_before", None)
                    self.heap_free_native_after = getattr(wlan, "heap_free_after", None)
                    self.heap_diagnostic_error = (self.heap_diagnostic_error + "; "
                        if self.heap_diagnostic_error else "") + getattr(wlan, "heap_diagnostic_error", "")
                    try:
                        self.heap_free_processed_after, _, diagnostic_error = heap_snapshot(collect=True)
                        if diagnostic_error:
                            self.heap_diagnostic_error += "; " + diagnostic_error
                    except Exception as diagnostic_exc:
                        self.heap_diagnostic_error += "; post-failure heap snapshot: " + str(diagnostic_exc)
                    raise
                if self.cancel_requested:
                    del raw
                    break
                self.heap_free_before = getattr(wlan, "heap_free_before", None)
                self.heap_free_native_after = getattr(wlan, "heap_free_after", None)
                self.raw_result_count = getattr(wlan, "raw_result_count", 0)
                self.failure_stage = "Wi-Fi scan result processing"
                records, total_found = bounded_scan_results(raw, self.result_limit)
                del raw
                try:
                    self.heap_free_processed_after, _, diagnostic_error = heap_snapshot(collect=True)
                    if diagnostic_error:
                        self.heap_diagnostic_error = diagnostic_error
                except Exception as diagnostic_exc:
                    self.heap_diagnostic_error = "post-processing heap snapshot: " + str(diagnostic_exc)
                    self.heap_free_processed_after = None
                self.results = records
                self.app.wifi_scan_results = records
                self.total_found = total_found
                if self.scan_count < 0x7FFFFFFF:
                    self.scan_count += 1
                self.last_update = ticks_ms()
                self.version += 1
                if not self.live:
                    self.status = "Complete: showing %d of %d APs" % (len(records), total_found)
                    break
                self.status = "Live: showing %d of %d APs; SEL stops" % (len(records), total_found)
                # Yield in the worker, never in the UI/input loop.
                import time
                for _ in range(self.live_interval_ms // 100):
                    if self.cancel_requested:
                        break
                    time.sleep_ms(100)
            if self.cancel_requested:
                self.status = "Scan stopped"
        except Exception as exc:
            self.error = self.failure_stage + ": " + wifi_error_text(exc)
            self.status = "Scan failed"
        finally:
            self.version += 1
            self.running = False
            _release(self.app, "wifi_scan")

    def update(self, app):
        now = ticks_ms()
        if self.version != self.rendered_version:
            self.rendered_version = self.version
            return True
        if self.display_labels:
            self.selected = max(0, min(self.selected, len(self.display_labels) - 1))
            scroll = max(0, min(self.selected - 5, len(self.display_labels) - 6))
            app.display.update_marquee(self, self.display_labels[self.selected], self.selected, scroll)
        return False

    def _visible(self):
        return filter_results(sort_results(self.results, self.sort_mode), self.query)

    def render(self, app):
        self.rendered_version = self.version
        if self.error:
            app.display.render_document("Wi-Fi Scan", [self.status, self.error,
                "Free pre-thread: " + _heap_kb(self.heap_free_pre_thread),
                "Free worker start: " + _heap_kb(self.heap_free_worker_start),
                "Free pre-scan: " + _heap_kb(self.heap_free_before),
                "Free post-scan: " + _heap_kb(self.heap_free_native_after),
                "Free processed: " + _heap_kb(self.heap_free_processed_after),
                "Heap diag: " + (self.heap_diagnostic_error or "OK")], 0, "LEFT: Back")
            return
        if not self.started:
            app.display.render_lines("AP Scanner", ["SELECT: Scan", "RIGHT: Sort order"], footer="LEFT: Back")
            return
        if not self.results:
            app.display.render_document("AP Scanner", [self.status,
                "Free pre-thread: " + _heap_kb(self.heap_free_pre_thread),
                "Free worker start: " + _heap_kb(self.heap_free_worker_start),
                "Free pre-scan: " + _heap_kb(self.heap_free_before),
                "Free post-scan: " + _heap_kb(self.heap_free_native_after),
                "Free processed: " + _heap_kb(self.heap_free_processed_after),
                "Heap diag: " + (self.heap_diagnostic_error or "OK")], 0,
                "SEL Start/Stop")
            return
        rows = self._visible()
        if not rows:
            app.display.render_lines("AP Scanner", ["No filter matches", self.query], footer="LEFT: Back")
            return
        self.selected = max(0, min(self.selected, len(rows) - 1))
        labels = ["%s %ddBm C%d" % (row["display_ssid"], row["rssi"], row["channel"])
                  for row in rows]
        self.display_labels = labels
        scroll = max(0, min(self.selected - 5, len(labels) - 6))
        app.display.render_lines("AP %d/%d %s" % (len(rows), self.total_found,
                                                   self.sort_mode), labels, self.selected, scroll,
                                 "SEL Details R Sort", marquee_key=self)

    def handle(self, app, button):
        if button == "left":
            app.navigation.back()
            return True
        if button in ("select", "right"):
            if button == "select":
                if self.running:
                    self.cancel_requested = True
                    self.live = False
                    self.status = "Stopping after current scan"
                    return True
                if not self.results or not self.started:
                    self._start_worker()
                    return True
                visible = self._visible()
                if not visible:
                    return True
                row = visible[self.selected]
                app.navigation.open(InformationScreen("Network Details",
                    _record_text(row) + "\n\n" + self._diagnostic_text()))
                return True
            modes = ("rssi", "name", "channel")
            self.sort_mode = modes[(modes.index(self.sort_mode) + 1) % len(modes)]
            return True
        if button in ("up", "down") and self.results:
            visible = self._visible()
            if not visible:
                return True
            self.selected = max(0, min(len(visible) - 1,
                                       self.selected + (-1 if button == "up" else 1)))
            return True
        return False

    def on_exit(self, app):
        if self.running:
            self.cancel_requested = True
            self.live = False

    def _diagnostic_text(self):
        return ("Scan total: %d; retained: %d\n"
                "Heap free pre-thread/worker/pre-scan: %s / %s / %s\n"
                "Heap free post-scan/processed: %s / %s\nHeap diag: %s" %
                (self.total_found, len(self.results), _heap_kb(self.heap_free_pre_thread),
                 _heap_kb(self.heap_free_worker_start), _heap_kb(self.heap_free_before),
                 _heap_kb(self.heap_free_native_after), _heap_kb(self.heap_free_processed_after),
                 self.heap_diagnostic_error or "OK"))


def _record_text(row):
    return ("SSID: %s\nBSSID: %s\nRSSI: %d dBm\nChannel: %d\nSecurity: %s\nHidden: %s" %
            (row.get("display_ssid", "<hidden>"), row.get("bssid", "Unavailable"),
             row.get("rssi", -127), row.get("channel", 0),
             row.get("security_name", "Unknown"), "Yes" if row.get("hidden") else "No"))


class WiFiStatusScreen(Screen):
    def __init__(self, monitor=False):
        self.monitor = monitor
        self.lines = []
        self.last_refresh = 0

    def _collect(self, app):
        wlan = _wlan(app)
        active = wlan.active()
        connected = wlan.isconnected() if active else False
        self.lines = ["Radio: " + ("ON" if active else "OFF"),
                      "Status: " + ("Connected" if connected else "Not connected")]
        if connected:
            values = wlan.ifconfig()
            self.lines.extend(["IP: " + str(values[0]), "Gateway: " + str(values[2]),
                               "DNS: " + str(values[3])])
            try:
                self.lines.append("RSSI: %s dBm" % wlan.rssi())
            except Exception:
                self.lines.append("RSSI: Unavailable")
        self.last_refresh = ticks_ms()

    def update(self, app):
        if not self.monitor or ticks_diff(ticks_ms(), self.last_refresh) < 1000:
            return False
        try:
            self._collect(app)
        except Exception as exc:
            self.lines = ["Wi-Fi unavailable", str(exc)]
        return True

    def render(self, app):
        try:
            self._collect(app)
        except Exception as exc:
            self.lines = ["Wi-Fi unavailable", str(exc)]
        app.display.render_document("Wi-Fi Monitor", app.display.wrap_lines(self.lines), 0,
                                    "LEFT: Back")

    def handle(self, app, button):
        if button == "left":
            app.navigation.back()
            return True
        return False


class WiFiAnalysisScreen(Screen):
    def __init__(self, kind):
        self.kind = kind
        self.rows = []

    def render(self, app):
        records = getattr(app, "wifi_scan_results", [])
        info = statistics(records)
        if self.kind == "channels":
            lines = ["APs: %d" % info["count"]]
            channels = info["channels"]
            for channel in sorted(channels)[:10]:
                lines.append("Ch %02d: %s %d" % (channel, "#" * min(8, channels[channel]), channels[channel]))
            title = "Channel Usage"
        elif self.kind == "signals":
            bands = info["signal"]
            lines = ["Excellent: %d" % bands["excellent"], "Good: %d" % bands["good"],
                     "Fair: %d" % bands["fair"], "Weak: %d" % bands["weak"]]
            title = "Signal Distribution"
        elif self.kind == "open":
            lines = ["Open APs: %d" % info["open_count"]]
            lines.extend([row["display_ssid"] + " Ch" + str(row["channel"])
                          for row in records if row["open"]][:8])
            title = "Open AP Warnings"
            if info["open_count"] == 0:
                lines.append("None in last scan")
        elif self.kind == "security":
            lines = ["Security summary:"]
            for name in sorted(info["security"]):
                lines.append("%s: %d" % (name, info["security"][name]))
            if not info["security"]:
                lines.append("Run a scan first")
            title = "Encryption Info"
        elif self.kind == "duplicates":
            lines = ["Repeated SSIDs:"] + info["duplicate_ssids"][:9]
            title = "Duplicate SSIDs"
            if not info["duplicate_ssids"]:
                lines.append("None in last scan")
        elif self.kind == "strength":
            lines = ["APs: %d" % info["count"]]
            for label, row in (("Strongest", info["strongest"]), ("Weakest", info["weakest"])):
                lines.append(label + ": " + ("n/a" if row is None else
                             "%s %d dBm" % (row["display_ssid"], row["rssi"])))
            title = "Signal Summary"
        else:
            lines = ["Networks: %d" % info["count"], "Open: %d" % info["open_count"],
                     "Channels: %d" % len(info["channels"]),
                     "Duplicate SSIDs: %d" % len(info["duplicate_ssids"])]
            title = "Network Statistics"
        if self.kind == "channels":
            app.display.render_lines(title, ["APs: %d" % info["count"],
                "2.4GHz channel load"], footer="LEFT: Back")
            display = app.display.display
            bottom = min(110, app.display.height - 18)
            display.hline(4, bottom, 116, 1)
            maximum = max(list(info["channels"].values()) or [1])
            for channel in range(1, 15):
                count = info["channels"].get(channel, 0)
                height = (count * 54) // maximum if count else 0
                x = 5 + (channel - 1) * 8
                if height:
                    display.fill_rect(x, bottom - height, 5, height, 1)
            display.show()
        elif self.kind == "signals":
            app.display.render_lines(title, ["RSSI groups", "Excellent / Good", "Fair / Weak"],
                                     footer="LEFT: Back")
            display = app.display.display
            bands = info["signal"]
            values = (bands["excellent"], bands["good"], bands["fair"], bands["weak"])
            maximum = max(list(values) or [1])
            bottom = min(110, app.display.height - 18)
            display.hline(8, bottom, 112, 1)
            for index, count in enumerate(values):
                height = (count * 48) // maximum if count else 0
                if height:
                    display.fill_rect(16 + index * 26, bottom - height, 16, height, 1)
            display.show()
        else:
            app.display.render_document(title, lines, 0, "LEFT: Back")

    def handle(self, app, button):
        if button == "left":
            app.navigation.back()
            return True
        return False


class SavedScanScreen(Screen):
    def __init__(self):
        self.sessions = load_sessions()
        self.selected = 0
        self.message = ""

    def render(self, app):
        rows = ["Save latest scan"] + ["Saved scan %d (%d APs)" %
                (index + 1, len(item.get("aps", []))) for index, item in enumerate(self.sessions)]
        if self.message:
            rows.append(self.message)
        app.display.render_lines("Saved Scans", rows, self.selected,
                                 max(0, self.selected - 5), "SEL Open/Save R Export", marquee_key=self)

    def handle(self, app, button):
        if button == "left":
            app.navigation.back()
        elif button in ("up", "down"):
            count = len(self.sessions) + 1
            self.selected = max(0, min(count - 1,
                                       self.selected + (-1 if button == "up" else 1)))
        elif button == "select":
            if self.selected == 0:
                records = getattr(app, "wifi_scan_results", [])
                if not records:
                    self.message = "Run a scan first"
                else:
                    self.message = "Saved" if save_session(records, ticks_ms()) else "Storage unavailable"
                    self.sessions = load_sessions()
            else:
                index = self.selected - 1
                if index < len(self.sessions):
                    lines = [_record_text(row) for row in self.sessions[index].get("aps", [])[:12]]
                    app.navigation.open(InformationScreen("Saved APs", "\n\n".join(lines)))
                    return True
        elif button == "right":
            records = getattr(app, "wifi_scan_results", [])
            self.message = "Exported wifi_scan.csv" if records and export_csv(records) else "Export unavailable"
        else:
            return False
        return True


class NetworkFilterScreen(Screen):
    """Simple joystick character picker for filtering the latest AP scan."""
    CHARS = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."

    def __init__(self):
        self.query = ""
        self.char_index = 0

    def render(self, app):
        app.display.render_document("Filter APs", ["Query: " + (self.query or "(empty)"),
            "Character: " + self.CHARS[self.char_index],
            "UP/DN choose char", "RIGHT add", "LEFT delete", "SELECT search"], 0,
            "L Delete/Back R Add")

    def handle(self, app, button):
        if button == "up":
            self.char_index = (self.char_index - 1) % len(self.CHARS)
        elif button == "down":
            self.char_index = (self.char_index + 1) % len(self.CHARS)
        elif button == "right":
            if len(self.query) < 16:
                self.query += self.CHARS[self.char_index]
        elif button == "left":
            if self.query:
                self.query = self.query[:-1]
            else:
                app.navigation.back()
        elif button == "select":
            records = getattr(app, "wifi_scan_results", [])
            if records:
                app.navigation.open(NetworkScanScreen(app, initial_results=records,
                                                      query=self.query))
            else:
                app.navigation.open(InformationScreen("Filter APs", "Run a network scan first."))
        else:
            return False
        return True


class WiFiDiagnosticsScreen(Screen):
    def __init__(self, kind):
        self.kind = kind

    def render(self, app):
        try:
            wlan = _wlan(app)
            if not wlan.isconnected():
                lines = ["Not connected", "Join a network manually"]
            else:
                values = wlan.ifconfig()
                if self.kind == "dhcp":
                    lines = ["DHCP lease:", "IP " + str(values[0]), "Mask " + str(values[1]),
                             "Gateway " + str(values[2]), "DNS " + str(values[3])]
                elif self.kind == "dns":
                    lines = ["DNS server: " + str(values[3]), "Resolution test not run"]
                elif self.kind == "connectivity":
                    lines = ["STA connected", "IP address assigned", "Gateway " + str(values[2]),
                             "ICMP ping unavailable"]
                else:
                    lines = ["Gateway: " + str(values[2])]
        except Exception as exc:
            lines = ["Unavailable", str(exc)]
        app.display.render_document("Network Diagnostic", lines, 0, "LEFT: Back")

    def handle(self, app, button):
        if button == "left":
            app.navigation.back()
            return True
        return False


class DNSResolutionScreen(Screen):
    """Explicit, worker-thread resolver test; no socket call blocks joystick input."""
    def __init__(self):
        self.status = "SELECT to resolve micropython.org"
        self.running = False
        self.cancelled = False
        self.version = 0
        self.rendered_version = 0

    def _worker(self, app):
        try:
            import socket
            values = socket.getaddrinfo("micropython.org", 80)
            if not self.cancelled:
                address = values[0][-1][0] if values else "No address returned"
                self.status = "Resolved: " + str(address)
        except Exception as exc:
            if not self.cancelled:
                self.status = "DNS failed: " + str(exc)
        finally:
            self.running = False
            self.version += 1
            _release(app, "wifi_dns")

    def update(self, app):
        if self.version != self.rendered_version:
            self.rendered_version = self.version
            return True
        return False

    def render(self, app):
        self.rendered_version = self.version
        app.display.render_document("DNS Test", [self.status,
            "Uses the current network resolver."], 0, "LEFT: Back")

    def handle(self, app, button):
        if button == "left":
            app.navigation.back()
            return True
        if button != "select" or self.running:
            return False
        if not _lease(app, "wifi_dns"):
            self.status = "Radio busy with another scan"
            return True
        try:
            wlan = _wlan(app)
            if not wlan.isconnected():
                raise RuntimeError("Connect to Wi-Fi first")
            import _thread
            self.running = True
            self.cancelled = False
            self.status = "Resolving..."
            _thread.start_new_thread(self._worker, (app,))
        except Exception as exc:
            self.status = "Unavailable: " + str(exc)
            self.running = False
            _release(app, "wifi_dns")
        return True

    def on_exit(self, app):
        if self.running:
            self.cancelled = True



class CSIActivityScreen(Screen):
    """Aggregate-only CSI counter. Never retains MAC addresses or CSI samples."""
    def __init__(self):
        self.wlan = None
        self.active = False
        self.frames = 0
        self.dropped = 0
        self.channels = {}
        self.rssi_sum = 0
        self.rssi_count = 0
        self.error = "SELECT to monitor; connected Wi-Fi required"
        self.last_refresh = 0
        self.csi_attempted = False

    def _start(self, app):
        if not _lease(app, "wifi_csi"):
            self.error = _radio_busy_text(app, "Radio busy with another scan")
            return
        try:
            self.wlan = _wlan(app)
            if not self.wlan.isconnected():
                raise RuntimeError("Connect to Wi-Fi first; CSI needs incoming traffic")
            for name in ("csi_enable", "csi_read", "csi_available", "csi_dropped", "csi_disable"):
                if not hasattr(self.wlan.interface, name):
                    raise RuntimeError("CSI API unavailable in this firmware")
            size = app.settings.get("wifi_csi_buffer") if getattr(app, "settings", None) else 8
            self.csi_attempted = True
            self.wlan.interface.csi_enable(size or 8)
            self.active = True
            self.error = "CSI active; aggregate counters only"
        except Exception as exc:
            self.error = str(exc)
            if self.csi_attempted and self.wlan is not None and \
                    hasattr(self.wlan.interface, "csi_disable"):
                try:
                    self.wlan.interface.csi_disable()
                except Exception as cleanup_error:
                    self.error += "; CSI cleanup failed: " + str(cleanup_error)
                    _block_radio_if_uncertain(app, "CSI state uncertain after cleanup error")
            _release(app, "wifi_csi")

    def update(self, app):
        if not self.active:
            return False
        try:
            interface = self.wlan.interface
            count = min(4, interface.csi_available())
            changed = count > 0
            for _ in range(count):
                frame = interface.csi_read()
                if frame is None:
                    break
                # Discard frame[2] (MAC) and frame[5] (raw CSI) immediately.
                rssi, channel = int(frame[0]), int(frame[1])
                if self.frames < 0x7FFFFFFF:
                    self.frames += 1
                if self.rssi_count >= 256:
                    self.rssi_sum = 0
                    self.rssi_count = 0
                self.rssi_sum += rssi
                self.rssi_count += 1
                count = self.channels.get(channel, 0)
                self.channels[channel] = count + 1 if count < 0x7FFFFFFF else count
            dropped = interface.csi_dropped()
            changed = changed or dropped != self.dropped
            self.dropped = dropped
            now = ticks_ms()
            if changed and ticks_diff(now, self.last_refresh) >= 500:
                self.last_refresh = now
                return True
            return False
        except Exception as exc:
            self.error = "CSI error: " + str(exc)
            self._stop(app)
            return True

    def _stop(self, app):
        if self.active and self.wlan is not None:
            try:
                self.wlan.interface.csi_disable()
            except Exception as exc:
                self.error = "CSI cleanup failed: " + str(exc)
                _block_radio_if_uncertain(app, "CSI state uncertain after cleanup error")
        self.active = False
        self.wlan = None
        _release(app, "wifi_csi")

    def render(self, app):
        average = self.rssi_sum // self.rssi_count if self.rssi_count else 0
        lines = [self.error, "Frames: %d" % self.frames,
                 "Dropped: %d" % self.dropped,
                 "Avg RSSI: %d dBm" % average if self.rssi_count else "Avg RSSI: n/a"]
        for channel in sorted(self.channels)[:4]:
            lines.append("Ch %d: %d" % (channel, self.channels[channel]))
        app.display.render_document("CSI Monitor", lines, 0,
                                    "SEL Stop" if self.active else "SEL Start L Back")

    def handle(self, app, button):
        if button == "left":
            if self.active:
                self._stop(app)
            app.navigation.back()
            return True
        if button == "select":
            if self.active:
                self._stop(app)
            else:
                self._start(app)
            return True
        return False

    def on_exit(self, app):
        if self.active:
            self._stop(app)
