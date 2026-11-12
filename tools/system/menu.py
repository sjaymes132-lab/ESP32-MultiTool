"""System menu actions wired to real MicroPython APIs where available."""
import gc
import sys
from ui.screens import MenuEntry
from ui.components import info
from core.system_info import device_lines, memory_lines, storage_lines
from core.screen_manager import ConfirmationScreen, InformationScreen, MessageScreen, InputMonitorScreen
from tools.common import submenu
from tools.system.screens import SystemMonitorScreen, DisplayDiagnosticScreen, BuzzerDiagnosticScreen, I2CScanScreen


def _hardware_lines(app):
    lines = ["OLED: READY", "Joystick: configured"]
    if app.sound.buzzer is None:
        lines.append("Buzzer: Unavailable")
        if app.sound.error:
            lines.append("PWM: " + app.sound.error)
    else:
        lines.append("Buzzer: " + ("Ready" if app.sound.enabled else "Ready; sound off"))
    lines.append("I2C: " + ("available" if app.display.i2c is not None else "Unavailable"))
    lines.extend(["I2C addresses:"] + ["0x%02X" % address for address in app.display.i2c_addresses])
    try:
        import machine
        lines.append("SPI API: " + ("Yes" if hasattr(machine, "SPI") else "Unavailable"))
        lines.append("UART API: " + ("Yes" if hasattr(machine, "UART") else "Unavailable"))
    except Exception:
        lines.extend(["SPI API: Unavailable", "UART API: Unavailable"])
    for name in ("wifi", "bluetooth", "nrf24_1", "nrf24_2", "cc1101_1", "cc1101_2", "gps"):
        if name in app.hardware.records:
            lines.append(name + ": " + app.hardware.status(name))
    return lines


def build_menu(app):
    def open_information(title, lines):
        app.navigation.open(InformationScreen(title, "\n".join(lines)))

    def device(_):
        open_information("Device Info", device_lines())

    def memory(_):
        open_information("Memory", memory_lines())

    def storage(_):
        open_information("Storage", storage_lines())

    def hardware(_):
        open_information("Hardware", _hardware_lines(app))

    def collect(_):
        gc.collect()
        app.navigation.open(MessageScreen("Garbage Collect", "Collection requested."))

    def restart(_):
        def do_restart():
            try:
                import machine
                machine.reset()
            except Exception as exc:
                return "Restart failed: " + str(exc)
        app.navigation.open(ConfirmationScreen("Restart?", "Restart this device?", do_restart))

    entries = [
        MenuEntry("Device Information", device),
        MenuEntry("Memory Information", memory),
        MenuEntry("Storage Information", storage),
        MenuEntry("Hardware Status", hardware),
        MenuEntry("I2C Bus Scan", lambda a: a.navigation.open(I2CScanScreen())),
        MenuEntry("System Monitor", lambda a: a.navigation.open(SystemMonitorScreen())),
        MenuEntry("Input Test", lambda a: a.navigation.open(InputMonitorScreen())),
        MenuEntry("Display Test", lambda a: a.navigation.open(DisplayDiagnosticScreen())),
        MenuEntry("Buzzer Test", lambda a: a.navigation.open(BuzzerDiagnosticScreen())),
        MenuEntry("Collect Garbage", collect),
        MenuEntry("Restart Device", restart),
        MenuEntry("Diagnostics Info", info("Diagnostics", "I2C scan checks responding addresses only. It cannot prove the full health of a device.")),
        MenuEntry("Back", lambda a: a.navigation.back()),
    ]
    return submenu("System", [entry.label for entry in entries[:-1]],
                   dict((entry.label, entry.action) for entry in entries[:-1]))
