"""Small shared factories for safe tool menu actions."""
from ui.screens import MenuEntry, MenuScreen
from core.screen_manager import MessageScreen, InformationScreen, PlaceholderScreen


def show_message(title, message):
    return lambda app: app.navigation.open(MessageScreen(title, message))


def show_info(title, lines):
    content = "\n".join(lines) if isinstance(lines, (list, tuple)) else str(lines)
    return lambda app: app.navigation.open(InformationScreen(title, content))


def submenu(title, labels, actions=None):
    actions = {} if actions is None else actions
    entries = [MenuEntry(label, actions.get(label, show_message(label,
               "Not available yet. Hardware access is not enabled."))) for label in labels]
    entries.append(MenuEntry("Back", lambda app: app.navigation.back()))
    return MenuScreen(title, entries)


def placeholder_screen(name):
    return lambda app: app.navigation.open(PlaceholderScreen(name))
