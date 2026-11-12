"""BLE integration point. No Bluetooth operations are performed."""
def open_tool(app):
    from core.screen_manager import PlaceholderScreen
    app.navigation.open(PlaceholderScreen("Bluetooth / BLE"))
