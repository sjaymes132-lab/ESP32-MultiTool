"""NRF24 tool menu with two independently configured module slots."""
from ui.screens import MenuEntry
from tools.common import submenu, show_message
from tools.nrf24.screens import ModuleStatusScreen, InitialiseScreen
from config import NRF24_MODULES


def _module_menu(index):
    values = NRF24_MODULES[index]
    name = values["name"]
    record = "nrf24_%d" % (index + 1)
    actions = {
        "Module Status": lambda app: app.navigation.open(ModuleStatusScreen(name, record, values)),
        "Module Configuration": show_message(name + " Config", "Edit external pin settings in config.py. No pins have been assumed."),
        "Initialise Module": lambda app: app.navigation.open(InitialiseScreen(name, record)),
        "Register Information": show_message("Registers", "Requires a configured module and compatible driver."),
        "Communication Test": show_message("NRF24 Test", "Requires configured hardware and a compatible driver."),
        "Packet Monitor": show_message("Packet Monitor", "Receive functionality is not implemented."),
        "Receive Mode": show_message("Receive Mode", "Receive functionality is not implemented."),
        "Transmit Test": show_message("Transmit Test", "No transmission is performed by this framework."),
    }
    labels = ["Module Status", "Module Configuration", "Initialise Module", "Register Information",
              "Communication Test", "Packet Monitor", "Receive Mode", "Transmit Test"]
    return submenu(name, labels, actions)


def build_menu(app):
    entries = [MenuEntry("Module 1", lambda a: a.navigation.open(_module_menu(0))),
               MenuEntry("Module 2", lambda a: a.navigation.open(_module_menu(1))),
               MenuEntry("Back", lambda a: a.navigation.back())]
    return submenu("NRF24", [entry.label for entry in entries[:-1]],
                   dict((entry.label, entry.action) for entry in entries[:-1]))
