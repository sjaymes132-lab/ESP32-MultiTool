"""BLE observation tools using one shared, defensive scan implementation."""
from core.screen_manager import InformationScreen, Screen, SelectableListScreen
from tools.common import submenu, show_message
from tools.bluetooth.screens import BLEScanScreen, BLEInitTestScreen, status_lines, observation_text
from tools.settings.screens import NumericSettingScreen


def _open(screen):
    return lambda app: app.navigation.open(screen())


def _scan(app, live=False, ibeacon=False):
    app.navigation.open(BLEScanScreen(app, live=live, ibeacon_only=ibeacon))


def _info(app, title, message):
    app.navigation.open(InformationScreen(title, message))


def _beacon_info(app, field):
    rows = [row for row in getattr(app, "ble_devices", [])
            if row.get("advertisement", {}).get("ibeacon")]
    if not rows:
        _info(app, "iBeacon", "No iBeacon advertisements in the current temporary scan results.")
        return
    row = rows[0]
    beacon = row["advertisement"]["ibeacon"]
    if field == "uuid":
        content = "UUID: " + beacon["uuid"]
    elif field == "major_minor":
        content = "Major: %d\nMinor: %d" % (beacon["major"], beacon["minor"])
    else:
        distance = 10 ** ((beacon["tx_power"] - row["rssi"]) / 20.0)
        content = "TX power: %d dBm\nRSSI: %d dBm\nApprox: %.1f m (very rough)" % (
            beacon["tx_power"], row["rssi"], distance)
    _info(app, "iBeacon", content)


def _detection(app, kind):
    records = getattr(app, "ble_devices", [])
    if kind == "flipper":
        matches = [row for row in records if "flipper" in row.get("name", "").lower()]
        if matches:
            text = "Possible name match only; low confidence.\n" + observation_text(matches[0])
        else:
            text = "No name match in temporary observations. This is not a definitive detector."
        _info(app, "Possible Flipper", text)
    else:
        _info(app, kind, "No validated signature parser is included. The device will not be classified from generic Apple/vendor data alone.")


def _stats(app, title="BLE Statistics"):
    rows = getattr(app, "ble_devices", [])
    makers = {}
    beacons = 0
    rssi_total = 0
    for row in rows:
        info = row.get("advertisement", {})
        maker = info.get("manufacturer", "Unknown") or "Unknown"
        makers[maker] = makers.get(maker, 0) + 1
        beacons += 1 if info.get("ibeacon") else 0
        rssi_total += row.get("rssi", 0)
    avg = rssi_total // len(rows) if rows else 0
    _info(app, title, "Temporary observations: %d\niBeacons: %d\nMean latest RSSI: %d dBm\nQueue results are RAM-only." %
          (len(rows), beacons, avg))


def _settings_menu(app):
    def numeric(title, key, minimum, maximum, step, suffix):
        return lambda a: a.navigation.open(NumericSettingScreen(title, key, minimum, maximum, step, suffix, a))
    entries = ["Scan Duration", "Scan Interval", "Scan Window", "Max Observations"]
    actions = {
        "Scan Duration": numeric("BLE Duration", "ble_scan_duration_ms", 1000, 30000, 1000, " ms"),
        "Scan Interval": numeric("BLE Interval", "ble_scan_interval_us", 100000, 2000000, 100000, " us"),
        "Scan Window": numeric("BLE Window", "ble_scan_window_us", 10000, 100000, 5000, " us"),
        "Max Observations": show_message("Observation Limit", "The in-memory observation limit is fixed at 24 to bound RAM."),
    }
    app.navigation.open(submenu("Bluetooth Settings", entries, actions))


class BLEFilterInputScreen(Screen):
    CHARS = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."

    def __init__(self):
        self.query = ""
        self.char_index = 0

    def render(self, app):
        app.display.render_document("Filter BLE", ["Query: " + (self.query or "(empty)"),
            "Character: " + self.CHARS[self.char_index], "UP/DN choose",
            "RIGHT add", "LEFT delete", "SELECT search"], 0, "L Delete/Back R Add")

    def handle(self, app, button):
        if button == "left":
            if self.query:
                self.query = self.query[:-1]
            else:
                app.navigation.back()
        elif button == "up":
            self.char_index = (self.char_index - 1) % len(self.CHARS)
        elif button == "down":
            self.char_index = (self.char_index + 1) % len(self.CHARS)
        elif button == "right":
            if len(self.query) < 16:
                self.query += self.CHARS[self.char_index]
        elif button == "select":
            query = self.query.lower().strip()
            matches = []
            for row in getattr(app, "ble_devices", []):
                info = row.get("advertisement", {})
                searchable = (row.get("name", "") + " " + row.get("address", "") + " " +
                              info.get("manufacturer", "") + " " +
                              " ".join(info.get("service_uuids", []))).lower()
                if not query or query in searchable:
                    matches.append(row)
            labels = ["%s %ddBm %s" % (row.get("name") or "BLE", row.get("rssi", -127),
                      row.get("address", "")[-8:]) for row in matches]
            if not matches:
                app.navigation.open(InformationScreen("BLE Filter", "No temporary observations match."))
            else:
                def show(item):
                    index = labels.index(item)
                    app.navigation.open(InformationScreen("BLE Device", observation_text(matches[index])))
                app.navigation.open(SelectableListScreen("BLE Matches", labels, show))
            return True
        else:
            return False
        return True


def build_menu(app):
    groups = {
        "Bluetooth Analyzer": submenu("BLE Analyzer", [
            "Scan Devices", "Live Discovery", "Device Details", "RSSI Monitor",
            "Advertisement Information", "Device Statistics", "Search Observations"], {
            "Scan Devices": lambda a: _scan(a),
            "Live Discovery": lambda a: _scan(a, live=True),
            "Device Details": lambda a: _scan(a),
            "RSSI Monitor": lambda a: _scan(a, live=True),
            "Advertisement Information": lambda a: _scan(a),
            "Device Statistics": _stats,
            "Search Observations": lambda a: a.navigation.open(BLEFilterInputScreen()),
        }),
        "Bluetooth Sniffer": submenu("Passive BLE", [
            "Passive BLE Scan", "Advertisement Monitor", "Manufacturer Data",
            "Service UUID Detection", "Signal Statistics", "Export Observations"], {
            "Passive BLE Scan": lambda a: _scan(a),
            "Advertisement Monitor": lambda a: _scan(a, live=True),
            "Manufacturer Data": lambda a: _scan(a),
            "Service UUID Detection": lambda a: _scan(a),
            "Signal Statistics": _stats,
            "Export Observations": show_message("Export", "Raw device identifiers and advertisements are not persisted or exported."),
        }),
        "Device Detection": submenu("Privacy Detection", [
            "Flipper-Related Detection", "AirTag Detection", "AirTag Monitor",
            "iBeacon Detection", "Card Skimmer Detection", "Flock Signature Detection",
            "Meta Device Detection"], {
            "Flipper-Related Detection": lambda a: _detection(a, "flipper"),
            "AirTag Detection": lambda a: _detection(a, "Possible Tracker"),
            "AirTag Monitor": show_message("Tracker Safety", "No validated AirTag signature parser is included. This tool does not follow or persistently identify devices."),
            "iBeacon Detection": lambda a: _scan(a, ibeacon=True),
            "Card Skimmer Detection": lambda a: _detection(a, "Card Skimmer"),
            "Flock Signature Detection": lambda a: _detection(a, "Flock Signature"),
            "Meta Device Detection": lambda a: _detection(a, "Meta Device"),
        }),
        "iBeacon Tools": submenu("iBeacon", ["Beacon Scanner", "UUID Viewer",
            "Major / Minor Viewer", "TX Power Information"], {
            "Beacon Scanner": lambda a: _scan(a, ibeacon=True),
            "UUID Viewer": lambda a: _beacon_info(a, "uuid"),
            "Major / Minor Viewer": lambda a: _beacon_info(a, "major_minor"),
            "TX Power Information": lambda a: _beacon_info(a, "tx"),
        }),
        "Fox Hunt": submenu("Own Beacon Finder", ["Select Own Test Beacon", "Signal Monitor", "Signal History"], {
            "Select Own Test Beacon": show_message("Own Test Beacon", "Run a scan and select only a beacon you own. Persistent device tracking is disabled."),
            "Signal Monitor": show_message("Signal Monitor", "A focused own-beacon monitor is not implemented; use RSSI Monitor for temporary observations."),
            "Signal History": show_message("Signal History", "Signal histories are not persisted."),
        }),
        "Bluetooth Diagnostics": submenu("BLE Diagnostics", [
            "Adapter Status", "BLE Initialization Test", "Scan Test",
            "IRQ Statistics", "Lifecycle Diagnostics"], {
            "Adapter Status": lambda a: _info(a, "BLE Status", "\n".join(status_lines(a))),
            "BLE Initialization Test": _open(BLEInitTestScreen),
            "Scan Test": lambda a: _scan(a),
            "IRQ Statistics": _stats,
            "Lifecycle Diagnostics": lambda a: _info(a, "BLE Lifecycle", "Radio activation precedes IRQ registration and scanning. Only one scan is allowed at a time. Failures remain cached until device restart."),
        }),
        "Bluetooth Settings": _settings_menu,
    }
    labels = ["Bluetooth Analyzer", "Bluetooth Sniffer", "Device Detection",
              "iBeacon Tools", "Fox Hunt", "Bluetooth Diagnostics", "Bluetooth Settings"]
    actions = {}
    for name in labels:
        if name == "Bluetooth Settings":
            actions[name] = _settings_menu
        else:
            screen = groups[name]
            actions[name] = lambda a, value=screen: a.navigation.open(value)
    return submenu("Bluetooth", labels, actions)
