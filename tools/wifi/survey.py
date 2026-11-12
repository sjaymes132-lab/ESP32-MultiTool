"""Opt-in AP-only survey; coordinates are recorded only with a fresh GPS fix."""
try:
    import ujson as json
except ImportError:
    import json
from core.screen_manager import Screen, InformationScreen, ConfirmationScreen
from tools.wifi.screens import _wlan, _lease, _release
from tools.wifi.analysis import bounded_scan_results
try:
    from time import ticks_ms, ticks_diff
except ImportError:
    import time
    ticks_ms = lambda: int(time.time() * 1000)
    ticks_diff = lambda newer, older: newer - older

MAX_SESSIONS = 4
MAX_OBSERVATIONS = 64
MAX_SESSION_BYTES = 16384


def load_sessions():
    sessions = []
    for index in range(MAX_SESSIONS):
        try:
            with open("survey_%d.json" % index, "r") as stream:
                raw = stream.read(MAX_SESSION_BYTES + 1)
            if len(raw) > MAX_SESSION_BYTES:
                continue
            item = json.loads(raw)
            if not isinstance(item, dict) or not isinstance(item.get("observations", []), list):
                continue
            bounded = []
            total = 0
            for point in item.get("observations", []):
                if not isinstance(point, dict) or not isinstance(point.get("aps", []), list):
                    continue
                aps = []
                for ap in point.get("aps", []):
                    if total >= MAX_OBSERVATIONS:
                        break
                    if isinstance(ap, dict):
                        aps.append(ap)
                        total += 1
                if aps:
                    copied = {"time_ms": point.get("time_ms", 0), "aps": aps}
                    for key in ("latitude", "longitude", "altitude_m"):
                        if key in point:
                            copied[key] = point[key]
                    bounded.append(copied)
                if total >= MAX_OBSERVATIONS:
                    break
            sessions.append({"geotagged": bool(item.get("geotagged", False)),
                             "observations": bounded})
        except Exception:
            pass
    return sessions


def save_session(session):
    try:
        try:
            with open("survey_index.txt", "r") as stream:
                index = int(stream.read()) % MAX_SESSIONS
        except Exception:
            index = 0
        with open("survey_%d.json" % index, "w") as stream:
            stream.write(json.dumps(session))
        with open("survey_index.txt", "w") as stream:
            stream.write(str((index + 1) % MAX_SESSIONS))
        return True
    except Exception:
        return False


def delete_sessions():
    import os
    removed = 0
    for index in range(MAX_SESSIONS):
        path = "survey_%d.json" % index
        try:
            os.remove(path)
            removed += 1
        except OSError:
            pass
    try:
        os.remove("survey_index.txt")
    except OSError:
        pass
    return removed


def observation_count(session):
    count = 0
    for point in session.get("observations", []):
        count += len(point.get("aps", []))
        if count >= MAX_OBSERVATIONS:
            return MAX_OBSERVATIONS
    return count


def export_session(session, path="wifi_survey.csv"):
    try:
        with open(path, "w") as stream:
            stream.write("ssid,bssid,channel,rssi_dbm,latitude,longitude\n")
            for point in session.get("observations", [])[:MAX_OBSERVATIONS]:
                for ap in point.get("aps", []):
                    values = (ap.get("ssid", ""), ap.get("bssid", ""), ap.get("channel", 0),
                              ap.get("rssi", -127), point.get("latitude", ""),
                              point.get("longitude", ""))
                    stream.write(",".join('"' + str(value).replace('"', '""') + '"'
                                          for value in values) + "\n")
        return True
    except Exception:
        return False


class WardriveScreen(Screen):
    def __init__(self, geotag=True):
        self.geotag = geotag
        self.gps = None
        self.wlan = None
        self.running = False
        self.lease_held = False
        self.waiting_fix = False
        self.stop_requested = False
        self.pending = None
        self.session = {"geotagged": geotag, "observations": []}
        self.status = "SELECT to start survey"
        self.saved = False
        self.latest_fix = None
        self.gps_error = ""

    def _fix(self):
        if self.gps is None:
            return None
        try:
            self.gps.poll()
            self.gps_error = ""
        except Exception as exc:
            self.gps_error = str(exc)
            return None
        data = self.gps.parser.data
        last = self.gps.last_valid_fix_ms
        if not data.get("fix") or last is None or ticks_diff(ticks_ms(), last) > 5000:
            return None
        return (data.get("latitude"), data.get("longitude"), data.get("altitude_m"))

    def _start_worker(self, app):
        if not self.lease_held:
            if not _lease(app, "wifi_survey"):
                reason = getattr(getattr(app, "radio", None), "failure_reason", None)
                self.status = "Radio unavailable: " + reason if reason else "Radio busy; survey waiting to start"
                return False
            self.lease_held = True
        try:
            import _thread
            self.running = True
            self.waiting_fix = False
            self.status = "Survey active; SEL stops"
            _thread.start_new_thread(self._worker, (app,))
        except Exception as exc:
            self.running = False
            self.status = "Thread support unavailable: " + str(exc)
            _release(app, "wifi_survey")
            self.lease_held = False
            return False
        return True

    def _begin(self, app):
        if not _lease(app, "wifi_survey"):
            reason = getattr(getattr(app, "radio", None), "failure_reason", None)
            self.status = "Radio unavailable: " + reason if reason else "Radio busy with another scan"
            return
        self.lease_held = True
        try:
            self.wlan = _wlan(app)
            if self.geotag:
                self.gps = app.hardware.initialise("gps")
                if self.gps is None:
                    raise RuntimeError(app.hardware.error("gps") or "GPS unavailable")
                if self._fix() is None:
                    if self.gps_error:
                        raise RuntimeError("GPS unavailable: " + self.gps_error)
                    self.waiting_fix = True
                    self.status = "NO GPS FIX; waiting before any location logging"
                    _release(app, "wifi_survey")
                    self.lease_held = False
                    return
            self._start_worker(app)
        except Exception as exc:
            self.status = "Unavailable: " + str(exc)
            _release(app, "wifi_survey")
            self.lease_held = False

    def _worker(self, app):
        import gc
        import time
        try:
            while not self.stop_requested and observation_count(self.session) < MAX_OBSERVATIONS:
                raw = self.wlan.scan()
                records, _total = bounded_scan_results(raw, 24)
                del raw
                gc.collect()
                if not self.stop_requested:
                    self.pending = (records, ticks_ms())
                delay = (app.settings.get("wifi_live_interval_ms") or 2000) // 100
                for _ in range(delay):
                    if self.stop_requested:
                        break
                    time.sleep_ms(100)
            if observation_count(self.session) >= MAX_OBSERVATIONS:
                self.status = "Survey observation limit reached"
                self.stop_requested = True
        except Exception as exc:
            self.status = "Survey failed: " + str(exc)
        finally:
            self.running = False
            if self.lease_held:
                _release(app, "wifi_survey")
                self.lease_held = False

    def update(self, app):
        changed = False
        if self.waiting_fix:
            self.latest_fix = self._fix()
            if self.gps_error:
                self.status = "GPS unavailable: " + self.gps_error
                self.waiting_fix = False
                _release(app, "wifi_survey")
                self.lease_held = False
                changed = True
            if self.latest_fix is not None:
                self._start_worker(app)
                changed = True
        elif self.geotag and self.running:
            # Poll the existing shared GPS driver; never construct a second UART.
            self.latest_fix = self._fix()
            if self.gps_error:
                self.status = "GPS unavailable; stopping survey"
                self.stop_requested = True
        if self.pending is not None:
            records, stamp = self.pending
            self.pending = None
            point = {"time_ms": stamp, "aps": []}
            fix = self.latest_fix if self.geotag else None
            if self.geotag and fix is None:
                self.status = "NO GPS FIX; skipped this sample"
            else:
                if fix is not None:
                    point["latitude"], point["longitude"], point["altitude_m"] = fix
                remaining = MAX_OBSERVATIONS - observation_count(self.session)
                for row in records[:remaining]:
                    point["aps"].append({"ssid": row["ssid"], "bssid": row["bssid"],
                                         "channel": row["channel"], "rssi": row["rssi"],
                                         "security": row["security_name"]})
                if point["aps"]:
                    self.session["observations"].append(point)
                    changed = True
        if self.stop_requested and not self.running and not self.saved:
            self.saved = True
            self.status = "Saved" if save_session(self.session) else "Stopped; storage unavailable"
            changed = True
        return changed

    def render(self, app):
        count = sum(len(point.get("aps", [])) for point in self.session["observations"])
        lines = [self.status, "Samples: %d" % len(self.session["observations"]),
                 "AP observations: %d" % count,
                 "Mode: GPS" if self.geotag else "Mode: no geotag"]
        if self.geotag and self.gps is not None and self.latest_fix is None:
            lines.append("NO GPS FIX")
        app.display.render_document("AP Survey", lines, 0,
                                    "SEL Stop" if self.running or self.waiting_fix else "SEL Start L Back")

    def handle(self, app, button):
        if button == "left":
            if self.running or self.waiting_fix:
                self.stop_requested = True
                self.waiting_fix = False
                if not self.running:
                    self.update(app)
            app.navigation.back()
            return True
        if button == "select":
            if self.running or self.waiting_fix:
                was_waiting = self.waiting_fix
                self.stop_requested = True
                self.waiting_fix = False
                if was_waiting and self.lease_held:
                    _release(app, "wifi_survey")
                    self.lease_held = False
                self.status = "Stopping after current scan"
            elif not self.saved:
                self._begin(app)
            else:
                self.status = "Survey saved; leave and reopen to start another"
            return True
        return False

    def on_exit(self, app):
        if self.running or self.waiting_fix:
            self.stop_requested = True
            self.waiting_fix = False
        if not self.saved and self.session["observations"]:
            self.saved = True
            save_session(self.session)
        if not self.running:
            _release(app, "wifi_survey")
            self.lease_held = False


class SavedSurveysScreen(Screen):
    def __init__(self):
        self.sessions = load_sessions()
        self.selected = 0
        self.status = ""

    def render(self, app):
        rows = ["Session %d: %d samples %s" % (i + 1,
                len(session.get("observations", [])),
                "GPS" if session.get("geotagged") else "NO GPS")
                for i, session in enumerate(self.sessions)]
        if not rows:
            rows = ["No saved surveys"]
        app.display.render_lines("Saved Surveys", rows, self.selected,
                                 max(0, self.selected - 5), "SEL View R Export L Back",
                                 marquee_key=self)

    def handle(self, app, button):
        if button == "left":
            app.navigation.back()
            return True
        if button in ("up", "down") and self.sessions:
            self.selected = max(0, min(len(self.sessions) - 1,
                self.selected + (-1 if button == "up" else 1)))
            return True
        if button == "select" and self.sessions:
            session = self.sessions[self.selected]
            lines = []
            for point in session.get("observations", [])[:8]:
                coords = ""
                if point.get("latitude") is not None:
                    coords = " %.4f,%.4f" % (point["latitude"], point["longitude"])
                for ap in point.get("aps", [])[:4]:
                    lines.append(ap["ssid"] or "<hidden>" + coords)
                    if coords:
                        lines.append(coords.strip())
            app.navigation.open(InformationScreen("Survey APs", "\n".join(lines) or "No observations"))
            return True
        if button == "right" and self.sessions:
            self.status = "Exported" if export_session(self.sessions[self.selected]) else "Export failed"
            app.navigation.open(InformationScreen("Survey Export", self.status + ": wifi_survey.csv"))
            return True
        return False


class GPSStatusScreen(Screen):
    def __init__(self):
        self.status = "SELECT to read GPS status"

    def render(self, app):
        app.display.render_document("Survey GPS", [self.status,
            "No fix is reported unless valid NMEA has arrived."], 0, "SEL Read L Back")

    def handle(self, app, button):
        if button == "left":
            app.navigation.back()
            return True
        if button != "select":
            return False
        gps = app.hardware.initialise("gps")
        if gps is None:
            self.status = "Unavailable: " + (app.hardware.error("gps") or "GPS not configured")
        else:
            try:
                gps.poll()
                data = gps.parser.data
                if data.get("fix") and gps.last_valid_fix_ms is not None and \
                        ticks_diff(ticks_ms(), gps.last_valid_fix_ms) <= 5000:
                    self.status = "Fix: %.5f, %.5f" % (data["latitude"], data["longitude"])
                else:
                    self.status = "NO GPS FIX"
            except Exception as exc:
                self.status = "GPS unavailable: " + str(exc)
        return True


class SurveyStatisticsScreen(Screen):
    def render(self, app):
        sessions = load_sessions()
        aps = sum(len(point.get("aps", [])) for session in sessions
                  for point in session.get("observations", []))
        app.display.render_document("Survey Stats", ["Sessions: %d" % len(sessions),
            "AP observations: %d" % aps, "No client identities are collected."], 0, "LEFT: Back")

    def handle(self, app, button):
        if button == "left":
            app.navigation.back()
            return True
        return False

