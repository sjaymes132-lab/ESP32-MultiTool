"""Small bounded storage for explicitly saved Wi-Fi AP scan snapshots."""
try:
    import ujson as json
except ImportError:
    import json

PATH = "wifi_scans.json"
MAX_SESSIONS = 4
MAX_APS = 24
MAX_FILE_BYTES = 16384


def load_sessions():
    try:
        with open(PATH, "r") as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            return []
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        sessions = []
        for item in data[:MAX_SESSIONS]:
            if not isinstance(item, dict) or not isinstance(item.get("aps", []), list):
                continue
            aps = []
            for row in item.get("aps", [])[:MAX_APS]:
                if isinstance(row, dict):
                    aps.append(row)
            sessions.append({"time_ms": item.get("time_ms", 0), "aps": aps})
        return sessions
    except Exception:
        return []


def save_session(records, timestamp_ms):
    sessions = load_sessions()
    clean = []
    for row in records[:MAX_APS]:
        clean.append({"ssid": row.get("ssid", ""), "bssid": row.get("bssid", ""),
                      "channel": int(row.get("channel", 0)),
                      "rssi": int(row.get("rssi", -127)),
                      "security": row.get("security_name", "Unknown"),
                      "hidden": bool(row.get("hidden", False))})
    sessions.insert(0, {"time_ms": int(timestamp_ms), "aps": clean})
    try:
        with open(PATH, "w") as stream:
            stream.write(json.dumps(sessions[:MAX_SESSIONS]))
        return True
    except Exception:
        return False


def export_csv(records, path="wifi_scan.csv"):
    try:
        with open(path, "w") as stream:
            stream.write("ssid,bssid,channel,rssi_dbm,security,hidden\n")
            for row in records[:MAX_APS]:
                values = (row.get("ssid", ""), row.get("bssid", ""),
                          row.get("channel", 0), row.get("rssi", -127),
                          row.get("security_name", "Unknown"), row.get("hidden", False))
                escaped = []
                for value in values:
                    text = str(value).replace('"', '""')
                    escaped.append('"' + text + '"')
                stream.write(",".join(escaped) + "\n")
        return True
    except Exception:
        return False
