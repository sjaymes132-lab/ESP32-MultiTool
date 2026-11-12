"""NRF24 integration point. No radio operations are performed."""
def open_tool(app):
    from core.screen_manager import PlaceholderScreen
    app.navigation.open(PlaceholderScreen("NRF24"))
