"""Wi-Fi integration point. No Wi-Fi operations are performed."""
def open_tool(app):
    from core.screen_manager import PlaceholderScreen
    app.navigation.open(PlaceholderScreen("Wi-Fi"))
