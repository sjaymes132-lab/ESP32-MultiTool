"""GPS integration point. No receiver or parsing operations are performed."""
def open_tool(app):
    from core.screen_manager import PlaceholderScreen
    app.navigation.open(PlaceholderScreen("GPS"))
