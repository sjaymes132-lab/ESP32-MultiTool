"""About screen integration example."""
def open_tool(app):
    from core.screen_manager import InformationScreen
    app.navigation.open(InformationScreen("About", "ESP MULTI TOOL\nESP32-S3 / SH1107"))
