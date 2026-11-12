"""Small root-menu builder; individual tool menus live in their own packages."""
from ui.screens import MenuScreen, MenuEntry
from tools.registry import TOOL_ORDER


def build_main_menu(app):
    entries = []
    for title in TOOL_ORDER:
        entries.append(MenuEntry(title, lambda current_app, name=title: current_app.open_tool(name)))
    return MenuScreen("ESP MULTI TOOL", entries)
