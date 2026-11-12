"""ESP MULTI TOOL application entry point for ESP32-S3 MicroPython."""
import time
from core.display_manager import DisplayManager
from core.input_manager import InputManager
from core.sound import SoundManager
from core.app import App
from ui.menu_builder import build_main_menu
from core.hardware_manager import HardwareManager
from core.settings_manager import SettingsManager
from hardware.gps.driver import GPSDriver
from hardware.nrf24.driver import NRF24Driver
from hardware.cc1101.driver import CC1101Driver
from hardware.wifi.driver import WiFiAdapter
from hardware.bluetooth.driver import BLEAdapter
import config


def main():
    display = DisplayManager.from_hardware()
    input_manager = InputManager()
    sound = SoundManager()
    hardware = HardwareManager()
    hardware.register("wifi", WiFiAdapter)
    hardware.register("bluetooth", BLEAdapter)
    gps_configured = (config.GPS_UART_ID is not None and config.GPS_TX_PIN is not None and
                      config.GPS_RX_PIN is not None and config.GPS_BAUDRATE is not None)
    hardware.register("gps", lambda: GPSDriver(), gps_configured)
    for index, values in enumerate(config.NRF24_MODULES):
        configured = all(values.get(key) is not None for key in ("spi_id", "sck", "mosi", "miso", "csn", "ce"))
        hardware.register("nrf24_%d" % (index + 1), lambda module=values: NRF24Driver(module), configured)
    for index, values in enumerate(config.CC1101_MODULES):
        configured = all(values.get(key) is not None for key in ("spi_id", "sck", "mosi", "miso", "csn"))
        hardware.register("cc1101_%d" % (index + 1), lambda module=values: CC1101Driver(module), configured)
    app = App(display, input_manager, sound, SettingsManager(), hardware)
    # The registry imports menus only; it does not initialise optional hardware.
    from tools.registry import register_tools
    app.tools = register_tools()
    app.start(build_main_menu(app))
    while True:
        app.update()
        time.sleep_ms(10)


if __name__ == "__main__":
    main()
