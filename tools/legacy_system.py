"""System tool integration point."""
def open_tool(app):
    from core.screen_manager import InformationScreen
    import sys
    app.navigation.open(InformationScreen("Device", "ESP32-S3\nMicroPython " + getattr(sys, "version", "unknown")))
