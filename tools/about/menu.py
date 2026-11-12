"""About menu for project and bundled driver licensing notes."""
from ui.screens import MenuEntry
from tools.common import submenu, show_message


def build_menu(app):
    entries = [MenuEntry("Project Info", show_message("ESP MULTI TOOL", "ESP32-S3 MicroPython\nSH1107 128x128")),
               MenuEntry("Licenses", show_message("Licenses", "SH1107: MIT\nuMenu adaptation: GPL-3.0-or-later")),
               MenuEntry("Back", lambda a: a.navigation.back())]
    return submenu("About", [entry.label for entry in entries[:-1]],
                   dict((entry.label, entry.action) for entry in entries[:-1]))
