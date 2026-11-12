"""Application coordinator shared by UI and future tools."""
import config
from core.navigation import Navigation
from core.screen_manager import MessageScreen, InputMonitorScreen
from core.music_player import MusicPlayer
from core.settings_manager import SettingsManager
from core.hardware_manager import HardwareManager
from core.radio_manager import RadioManager
try:
    from time import ticks_ms
except ImportError:
    import time
    ticks_ms = lambda: int(time.time() * 1000)


class App:
    def __init__(self, display, input_manager, sound, settings=None, hardware=None):
        self.display = display
        self.input = input_manager
        self.sound = sound
        self.music = MusicPlayer(sound)
        self.settings = SettingsManager() if settings is None else settings
        self.hardware = HardwareManager() if hardware is None else hardware
        self.radio = RadioManager()
        self.navigation = None
        self.dirty = True
        self.tools = {}
        self.ble_devices = []
        self.wifi_scan_results = []
        self.local_service_results = []
        self.started_at = ticks_ms()
        self.input_failed = False

    def start(self, root):
        self.navigation = Navigation(self, root)
        try:
            self.settings.apply(self)
        except Exception as exc:
            print("Settings apply warning:", exc)
        self.invalidate()

    def invalidate(self):
        self.dirty = True

    def show_message(self, title, message):
        self.navigation.open(MessageScreen(title, message))

    def open_tool(self, name):
        """Integration contract: registered module.open_tool(app) owns a Screen via navigation."""
        opener = self.tools.get(name)
        if opener is None:
            from core.screen_manager import PlaceholderScreen
            self.navigation.open(PlaceholderScreen(name))
            return
        try:
            if callable(opener):
                screen = opener(self)
                if screen is not None:
                    self.navigation.open(screen)
            elif hasattr(opener, "build_menu"):
                self.navigation.open(opener.build_menu(self))
            else:
                raise TypeError("Tool must be an open_tool(app) function or menu builder")
        except Exception as exc:
            self.show_message("Tool error", str(exc))

    def update(self):
        try:
            if self.music.update():
                self.invalidate()
        except Exception as exc:
            self.music.stop()
            self.sound.enabled = False
            self.sound.error = str(exc)
            self.show_message("Music Error", str(exc))
        try:
            if self.navigation.current.update(self):
                self.invalidate()
        except Exception as exc:
            self.show_message("Update error", str(exc))
        if self.input_failed:
            events = []
        else:
            try:
                events = self.input.poll()
            except Exception as exc:
                print("Input polling error:", exc)
                self.input_failed = True
                self.show_message("Input Error", str(exc))
                events = []
        changed = False
        for button, event in events:
            if event == "release":
                if isinstance(self.navigation.current, InputMonitorScreen):
                    self.invalidate()
                continue
            if event not in ("press", "repeat"):
                continue
            if event == "press":
                self.sound.play()
            try:
                handled = self.navigation.current.handle(self, button)
                changed = changed or handled
            except Exception as exc:
                self.show_message("Screen error", str(exc))
                changed = True
            # Handle only one action each poll, even in a noisy/ambiguous condition.
            if changed:
                break
        if self.dirty or changed:
            self.navigation.current.render(self)
            self.dirty = False
        try:
            self.sound.update()
        except Exception as exc:
            self.sound.error = str(exc)
            self.sound.enabled = False

