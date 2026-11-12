"""CC1101 menu for two independent configuration slots."""
from ui.screens import MenuEntry
from tools.common import submenu, show_message
from tools.cc1101.screens import ModuleStatusScreen, InitialiseScreen
from config import CC1101_MODULES


def _module_menu(index):
    values = CC1101_MODULES[index]
    name = values["name"]
    record = "cc1101_%d" % (index + 1)
    actions = {
        "Module Status": lambda app: app.navigation.open(ModuleStatusScreen(name, record, values)),
        "Module Configuration": show_message(name + " Config", "Edit external pin settings in config.py. No pins have been assumed."),
        "Initialise Module": lambda app: app.navigation.open(InitialiseScreen(name, record)),
        "Register Information": show_message("Registers", "Requires a configured module and compatible driver."),
        "Frequency Configuration": show_message("Frequency", "Requires the CC1101 driver; no radio setting is applied."),
        "Modulation Settings": show_message("Modulation", "Requires the CC1101 driver; no radio setting is applied."),
        "Receive Mode": show_message("Receive Mode", "Receive functionality is not implemented."),
        "Signal Information": show_message("Signal Info", "No signal data is collected."),
        "Communication Test": show_message("CC1101 Test", "Requires configured hardware and a compatible driver."),
    }
    labels = ["Module Status", "Module Configuration", "Initialise Module", "Register Information",
              "Frequency Configuration", "Modulation Settings", "Receive Mode", "Signal Information", "Communication Test"]
    return submenu(name, labels, actions)


def build_menu(app):
    entries = [MenuEntry("Module 1", lambda a: a.navigation.open(_module_menu(0))),
               MenuEntry("Module 2", lambda a: a.navigation.open(_module_menu(1))),
               MenuEntry("Back", lambda a: a.navigation.back())]
    return submenu("CC1101", [entry.label for entry in entries[:-1]],
                   dict((entry.label, entry.action) for entry in entries[:-1]))
