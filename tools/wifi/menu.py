"""Wi-Fi menus: passive AP analysis, connection diagnostics and safe monitoring."""
from tools.common import submenu, show_message, show_info
from tools.wifi.screens import (NetworkScanScreen, WiFiStatusScreen, WiFiAnalysisScreen,
                                SavedScanScreen, WiFiDiagnosticsScreen, CSIActivityScreen)
from tools.wifi.screens import NetworkFilterScreen
from tools.wifi.screens import DNSResolutionScreen
from tools.wifi.network_scan import LocalNetworkScanScreen, export_results
from tools.wifi.survey import WardriveScreen, SavedSurveysScreen, GPSStatusScreen, SurveyStatisticsScreen, delete_sessions
from core.screen_manager import InformationScreen
from core.screen_manager import ConfirmationScreen
from tools.settings.screens import NumericSettingScreen


def _open(screen_factory):
    return lambda app: app.navigation.open(screen_factory())


def _current_scan(app, title="AP Results"):
    rows = getattr(app, "wifi_scan_results", [])
    if not rows:
        show_info(title, "Run an AP scan first.")(app)
        return
    app.navigation.open(NetworkScanScreen(app, initial_results=rows))


def _group(title, labels, actions):
    return lambda app: app.navigation.open(submenu(title, labels, actions))


def _wifi_settings(app):
    def numeric(title, key, low, high, step, suffix):
        return lambda a: a.navigation.open(NumericSettingScreen(title, key, low, high, step, suffix, a))
    app.navigation.open(submenu("Wi-Fi Settings", ["Live Scan Interval", "Max AP Results", "CSI Buffer Size"], {
        "Live Scan Interval": numeric("Scan Interval", "wifi_live_interval_ms", 2000, 10000, 500, " ms"),
        "Max AP Results": numeric("AP Result Limit", "wifi_result_limit", 1, 24, 1, " APs"),
        "CSI Buffer Size": numeric("CSI Buffer", "wifi_csi_buffer", 4, 16, 4, " frames"),
    }))


def _network_inventory(app):
    rows = getattr(app, "local_service_results", [])
    text = "\n".join([row["ip"] + ": " + ", ".join(row["services"])
                      for row in rows]) if rows else "No responding services in the latest scan."
    app.navigation.open(InformationScreen("Local Inventory", text))


def _export_networks(app):
    ok = export_results(getattr(app, "local_service_results", []))
    app.navigation.open(InformationScreen("Export", "Saved local_services.csv" if ok else "No results or storage unavailable."))


def build_menu(app):
    scan = lambda a: a.navigation.open(NetworkScanScreen(a))
    live_scan = lambda a: a.navigation.open(NetworkScanScreen(a, live=True))
    actions = {
        "Access Point Scanner": _group("AP Scanner", [
            "Scan Networks", "Live Scan", "Network Details", "Signal Strength",
            "Encryption Information", "Channel Information", "Search / Filter",
            "Saved Scan Results"], {
            "Scan Networks": scan,
            "Live Scan": live_scan,
            "Network Details": lambda a: _current_scan(a, "Network Details"),
            "Signal Strength": _open(lambda: WiFiAnalysisScreen("strength")),
            "Encryption Information": _open(lambda: WiFiAnalysisScreen("security")),
            "Channel Information": _open(lambda: WiFiAnalysisScreen("channels")),
            "Search / Filter": _open(NetworkFilterScreen),
            "Saved Scan Results": _open(SavedScanScreen),
        }),
        "Network Analyzer": _group("Network Analyzer", [
            "Channel Analyzer", "Channel Congestion", "Signal Distribution",
            "Duplicate SSID Detection", "Open Network Detection", "Network Statistics"], {
            "Channel Analyzer": _open(lambda: WiFiAnalysisScreen("channels")),
            "Channel Congestion": _open(lambda: WiFiAnalysisScreen("channels")),
            "Signal Distribution": _open(lambda: WiFiAnalysisScreen("signals")),
            "Duplicate SSID Detection": _open(lambda: WiFiAnalysisScreen("duplicates")),
            "Open Network Detection": _open(lambda: WiFiAnalysisScreen("open")),
            "Network Statistics": _open(lambda: WiFiAnalysisScreen("statistics")),
        }),
        "Wi-Fi Monitor": _group("Wi-Fi Monitor", [
            "Connection Status", "Signal Monitor", "Connection Quality",
            "IP Information", "Traffic Statistics"], {
            "Connection Status": _open(lambda: WiFiStatusScreen()),
            "Signal Monitor": _open(lambda: WiFiStatusScreen(monitor=True)),
            "Connection Quality": _open(lambda: WiFiStatusScreen(monitor=True)),
            "IP Information": _open(lambda: WiFiDiagnosticsScreen("dhcp")),
            "Traffic Statistics": show_message("Traffic Statistics",
                "Per-flow traffic counters are not exposed by this MicroPython WLAN API."),
        }),
        "Network Diagnostics": _group("Network Diagnostics", [
            "Gateway Information", "DNS Information", "DHCP Information",
            "Connectivity Test", "Ping Test", "DNS Resolution Test"], {
            "Gateway Information": _open(lambda: WiFiDiagnosticsScreen("gateway")),
            "DNS Information": _open(lambda: WiFiDiagnosticsScreen("dns")),
            "DHCP Information": _open(lambda: WiFiDiagnosticsScreen("dhcp")),
            "Connectivity Test": _open(lambda: WiFiDiagnosticsScreen("connectivity")),
            "Ping Test": show_message("Ping Test", "ICMP ping is not provided by the standard MicroPython WLAN API."),
            "DNS Resolution Test": _open(DNSResolutionScreen),
        }),
        "Network Scanner": _group("Local Network Scanner", [
            "Current Network", "Discover Hosts", "Service Discovery",
            "Device Inventory", "Export Results"], {
            "Current Network": _open(lambda: WiFiDiagnosticsScreen("dhcp")),
            "Discover Hosts": _open(LocalNetworkScanScreen),
            "Service Discovery": _open(LocalNetworkScanScreen),
            "Device Inventory": _network_inventory,
            "Export Results": _export_networks,
        }),
        "Wi-Fi Security": _group("Wi-Fi Security", [
            "Open Network Warnings", "Duplicate AP Detection",
            "Suspicious Configuration Detection", "Deauthentication Activity Detection",
            "Security Summary"], {
            "Open Network Warnings": _open(lambda: WiFiAnalysisScreen("open")),
            "Duplicate AP Detection": _open(lambda: WiFiAnalysisScreen("duplicates")),
            "Suspicious Configuration Detection": show_message("Configuration Check",
                "Only advertised SSID, channel and security metadata are available; no active tests are performed."),
            "Deauthentication Activity Detection": show_message("Deauth Monitor",
                "Raw management-frame monitoring is not exposed by WLAN.scan(). This feature requires a validated native extension."),
            "Security Summary": _open(lambda: WiFiAnalysisScreen("statistics")),
        }),
        "Wi-Fi Sniffers": _group("Passive Wi-Fi Monitor", [
            "Beacon Statistics", "Management Frame Statistics", "Channel Activity",
            "Packet Counters", "Defensive Monitoring"], {
            "Beacon Statistics": _open(lambda: WiFiAnalysisScreen("statistics")),
            "Management Frame Statistics": show_message("Management Frames",
                "Frame-level monitoring is not exposed by WLAN.scan(); no raw frames are collected."),
            "Channel Activity": _open(lambda: CSIActivityScreen()),
            "Packet Counters": _open(lambda: CSIActivityScreen()),
            "Defensive Monitoring": _open(lambda: CSIActivityScreen()),
        }),
        "Remote ID": _group("Remote ID", ["Detect Broadcasts", "Live Information", "Detection Status"], {
            "Detect Broadcasts": show_message("Remote ID", "A validated OpenDroneID decoder is not included. No broadcast is classified without a verified parser."),
            "Live Information": show_message("Remote ID", "No supported Remote ID decoder is available."),
            "Detection Status": show_message("Remote ID", "Detection unavailable; compatible BLE advertisement parsing is not validated."),
        }),
        "Wardrive": _group("AP Survey", ["Start AP Survey", "Start Non-geotagged Survey",
            "GPS Status", "Survey Statistics", "View Saved Sessions", "Export Survey",
            "Delete Survey Sessions"], {
            "Start AP Survey": _open(lambda: WardriveScreen(geotag=True)),
            "GPS Status": _open(GPSStatusScreen),
            "Survey Statistics": _open(SurveyStatisticsScreen),
            "View Saved Sessions": _open(SavedSurveysScreen),
            "Export Survey": _open(SavedSurveysScreen),
            "Delete Survey Sessions": lambda a: a.navigation.open(ConfirmationScreen(
                "Delete Surveys", "Delete all saved AP survey sessions?", delete_sessions)),
            "Start Non-geotagged Survey": _open(lambda: WardriveScreen(geotag=False)),
        }),
        "Saved Networks": _group("Saved Networks", ["View Profiles", "Connect", "Disconnect", "Remove Profile"], {
            "View Profiles": show_message("Saved Networks", "This app does not store Wi-Fi credentials or profiles."),
            "Connect": show_message("Connect", "No saved profile is available. Credential entry and connection are not implemented."),
            "Disconnect": show_message("Disconnect", "Disconnect is not automatic; use the device/router controls for the current connection."),
            "Remove Profile": show_message("Profiles", "No credentials or saved profiles are stored."),
        }),
        "Wi-Fi Settings": _wifi_settings,
    }
    labels = ["Access Point Scanner", "Network Analyzer", "Wi-Fi Monitor",
              "Network Diagnostics", "Network Scanner", "Wi-Fi Security",
              "Wi-Fi Sniffers", "Remote ID", "Wardrive", "Saved Networks", "Wi-Fi Settings"]
    return submenu("WiFi", labels, actions)
