"""Pure helpers for normalising and analysing MicroPython WLAN scan results."""

SECURITY_NAMES = ("Open", "WEP", "WPA-PSK", "WPA2-PSK", "WPA/WPA2")


def _decode(value):
    if isinstance(value, bytes):
        try:
            return value.decode()
        except Exception:
            return ""
    try:
        return str(value) if value is not None else ""
    except Exception:
        return ""


def _bssid(value):
    if isinstance(value, (bytes, bytearray)):
        return ":".join("%02X" % byte for byte in value)
    return _decode(value)


def normalise_record(item):
    """Convert the documented (ssid,bssid,channel,rssi,security,hidden) tuple."""
    try:
        if isinstance(item, dict):
            ssid = _decode(item.get("ssid", ""))
            bssid = _bssid(item.get("bssid", ""))
            channel = int(item.get("channel", 0))
            rssi = int(item.get("rssi", -127))
            security = int(item.get("security", -1))
            hidden = bool(item.get("hidden", not bool(ssid)))
        else:
            if len(item) < 6:
                return None
            ssid = _decode(item[0])
            bssid = _bssid(item[1])
            channel = int(item[2])
            rssi = int(item[3])
            security = int(item[4])
            hidden = bool(item[5])
        if channel < 0 or channel > 196:
            channel = 0
        security_name = SECURITY_NAMES[security] if 0 <= security < len(SECURITY_NAMES) else "Unknown"
        return {"ssid": ssid, "display_ssid": ssid or "<hidden>",
                "bssid": bssid, "channel": channel, "rssi": rssi,
                "security": security, "security_name": security_name,
                "open": security == 0, "hidden": hidden}
    except (TypeError, ValueError, IndexError):
        return None


def normalise_results(items, limit=24):
    results = []
    for item in items:
        if len(results) >= limit:
            break
        record = normalise_record(item)
        if record is not None:
            results.append(record)
    return results


def bounded_scan_results(items, limit=24):
    """Consume the WLAN scan list into a bounded strongest-signal result set.

    All returned rows are examined so callers can report the total. When the
    input is the mutable list returned by WLAN.scan(), each processed tuple is
    cleared immediately to reduce peak overlap between raw and normalized
    records. The strongest ``limit`` valid APs are retained, not an arbitrary
    first slice.
    """
    limit = max(0, int(limit))
    records = []
    total = 0
    try:
        item_count = len(items)
    except TypeError:
        item_count = 0
    for index in range(item_count):
        item = items[index]
        record = normalise_record(item)
        if record is not None:
            total += 1
            if len(records) < limit:
                records.append(record)
            elif limit:
                weakest = 0
                for position in range(1, len(records)):
                    if records[position]["rssi"] < records[weakest]["rssi"]:
                        weakest = position
                if record["rssi"] > records[weakest]["rssi"]:
                    records[weakest] = record
        try:
            items[index] = None
        except (TypeError, AttributeError):
            pass
    return records, total


def sort_results(records, mode="rssi"):
    if mode == "name":
        return sorted(records, key=lambda row: (row["ssid"].lower(), row["bssid"]))
    if mode == "channel":
        return sorted(records, key=lambda row: (row["channel"], -row["rssi"]))
    return sorted(records, key=lambda row: row["rssi"], reverse=True)


def filter_results(records, query):
    query = _decode(query).lower().strip()
    if not query:
        return list(records)
    return [row for row in records if query in row["ssid"].lower() or
            query in row["bssid"].lower() or query in row["security_name"].lower()]


def statistics(records):
    channels = {}
    names = {}
    security = {}
    signal = {"excellent": 0, "good": 0, "fair": 0, "weak": 0}
    strongest = None
    weakest = None
    open_count = 0
    for row in records:
        channel = row["channel"]
        channels[channel] = channels.get(channel, 0) + 1
        if row["ssid"]:
            names[row["ssid"].lower()] = names.get(row["ssid"].lower(), 0) + 1
        open_count += 1 if row["open"] else 0
        security_name = row["security_name"]
        security[security_name] = security.get(security_name, 0) + 1
        rssi = row["rssi"]
        if rssi >= -50:
            signal["excellent"] += 1
        elif rssi >= -65:
            signal["good"] += 1
        elif rssi >= -80:
            signal["fair"] += 1
        else:
            signal["weak"] += 1
        if strongest is None or rssi > strongest["rssi"]:
            strongest = row
        if weakest is None or rssi < weakest["rssi"]:
            weakest = row
    duplicates = [name for name, count in names.items() if count > 1]
    return {"count": len(records), "channels": channels, "signal": signal,
            "open_count": open_count, "duplicate_ssids": duplicates,
            "security": security, "strongest": strongest, "weakest": weakest}
