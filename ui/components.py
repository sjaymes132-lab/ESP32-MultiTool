"""Small factories for reusable UI actions."""
from core.screen_manager import PlaceholderScreen, InformationScreen


def placeholder(title):
    return lambda app: app.navigation.open(PlaceholderScreen(title))


def info(title, content):
    return lambda app: app.navigation.open(InformationScreen(title, content))

