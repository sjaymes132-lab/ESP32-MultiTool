"""GPS menu with NMEA-backed views and honest no-fix/configuration states."""
from tools.common import submenu, show_message
from tools.gps.screens import GPSDataScreen


def _open(fields=None, raw=False):
    def action(app):
        app.hardware.initialise("gps")
        app.navigation.open(GPSDataScreen(fields, raw))
    return action


def build_menu(app):
    labels = ["GPS Status", "Live Coordinates", "Satellite Information", "Speed", "Altitude",
              "Date and Time", "Fix Information", "Raw NMEA Monitor", "GPS Configuration"]
    actions = {
        "GPS Status": _open(["Latitude", "Longitude", "Satellites"]),
        "Live Coordinates": _open(["Latitude", "Longitude", "Altitude"]),
        "Satellite Information": _open(["Satellites"]),
        "Speed": _open(["Speed"]),
        "Altitude": _open(["Altitude"]),
        "Date and Time": _open(["UTC", "Date"]),
        "Fix Information": _open(["Satellites", "UTC", "Date"]),
        "Raw NMEA Monitor": _open(raw=True),
        "GPS Configuration": show_message("GPS Config", "Set UART ID, TX, RX and baud in config.py. No pins or baud are assumed."),
    }
    return submenu("GPS", labels, actions)
