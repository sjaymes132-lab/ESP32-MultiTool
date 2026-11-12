"""Single place to register tool packages and their menu entry order."""
TOOL_ORDER = ("WiFi", "Bluetooth", "NRF24", "CC1101", "GPS", "System", "Settings", "About")


def register_tools():
    from tools.wifi.menu import build_menu as wifi
    from tools.bluetooth.menu import build_menu as bluetooth
    from tools.nrf24.menu import build_menu as nrf24
    from tools.cc1101.menu import build_menu as cc1101
    from tools.gps.menu import build_menu as gps
    from tools.system.menu import build_menu as system
    from tools.settings.menu import build_menu as settings
    from tools.about.menu import build_menu as about
    return {"WiFi": wifi, "Bluetooth": bluetooth, "NRF24": nrf24,
            "CC1101": cc1101, "GPS": gps, "System": system,
            "Settings": settings, "About": about}
