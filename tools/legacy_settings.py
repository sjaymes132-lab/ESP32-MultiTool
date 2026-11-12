"""Settings tool integration point; shared settings UI is in ui.menu_builder."""
def open_tool(app):
    from core.screen_manager import PlaceholderScreen
    app.navigation.open(PlaceholderScreen("Settings"))
