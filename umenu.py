# SPDX-License-Identifier: GPL-3.0-or-later
# Repaired SH1107 adaptation of the original uMenu API. The supplied source
# identified itself as GPL-3.0-or-later; retain that license for this module.
"""Compact uMenu-compatible menu primitives for the SH1107 framebuffer."""


class MenuItem:
    def __init__(self, name, decorator="", visible=True):
        self.name = str(name)
        self.decorator = decorator
        self.visible = visible
        self.parent = None
        self.is_active = False

    def click(self):
        return self.parent

    def get_decorator(self):
        return str(self.decorator() if callable(self.decorator) else self.decorator)


class CallbackItem(MenuItem):
    def __init__(self, name, callback, decorator="", return_parent=True, visible=True):
        MenuItem.__init__(self, name, decorator, visible)
        self.callback = callback
        self.return_parent = return_parent

    def click(self):
        self.callback()
        return self.parent if self.return_parent else None


class InfoItem(MenuItem):
    pass


class SubMenuItem(MenuItem):
    def __init__(self, name, decorator="", visible=True):
        MenuItem.__init__(self, name, decorator, visible)
        self.menu = MenuScreen(name)

    def add(self, item):
        self.menu.add(item)
        return self

    def click(self):
        return self.menu


class BackItem(MenuItem):
    def __init__(self, parent):
        MenuItem.__init__(self, "Back")
        self.parent = parent


class MenuScreen:
    def __init__(self, title, parent=None):
        self.title = str(title)
        self.parent = parent
        self.items = []
        self.selected = 0

    def add(self, item):
        item.parent = self
        if isinstance(item, SubMenuItem):
            item.menu.parent = self
        self.items.append(item)
        return self

    def visible_items(self):
        return [item for item in self.items if item.visible]

    def count(self):
        return len(self.visible_items()) + (1 if self.parent is not None else 0)

    def get(self, index):
        items = self.visible_items()
        if self.parent is not None and index == len(items):
            return BackItem(self.parent)
        if index < 0 or index >= len(items):
            return None
        return items[index]

    def move(self, amount):
        if self.count():
            self.selected = max(0, min(self.count() - 1, self.selected + amount))

    def select(self):
        item = self.get(self.selected)
        if item is None:
            return self
        if isinstance(item, BackItem):
            return self.parent
        if isinstance(item, SubMenuItem):
            return item.menu
        return item.click() or self


class Menu:
    """Legacy menu controller; applications may instead use core.navigation."""
    def __init__(self, display, per_page=6, line_height=16, font_width=8, font_height=8):
        self.display = display
        self.per_page = per_page
        self.line_height = line_height
        self.font_width = font_width
        self.font_height = font_height
        self.current_screen = None
        self.main_screen = None

    def set_screen(self, screen):
        self.current_screen = screen
        if self.main_screen is None:
            self.main_screen = screen
        self.draw()

    def move(self, direction=1):
        self.current_screen.move(direction)
        self.draw()

    def click(self):
        self.current_screen = self.current_screen.select()
        self.draw()

    def back(self):
        if self.current_screen.parent is not None:
            self.current_screen = self.current_screen.parent
        self.draw()

    def reset(self):
        self.current_screen = self.main_screen
        self.draw()

    def draw(self):
        if self.current_screen is None:
            return
        d = self.display
        d.fill(0)
        title = self.current_screen.title[:16]
        d.text(title, 0, 0, 1)
        d.hline(0, 10, d.width, 1)
        count = self.current_screen.count()
        first = max(0, min(self.current_screen.selected - self.per_page + 1,
                           max(0, count - self.per_page)))
        for row in range(min(self.per_page, count - first)):
            index = first + row
            item = self.current_screen.get(index)
            item.is_active = index == self.current_screen.selected
            y = 16 + row * self.line_height
            if item.is_active:
                d.fill_rect(0, y, d.width, self.line_height, 1)
            text = (">" if item.is_active else " ") + item.name
            d.text(text[:16], 0, y + 4, 0 if item.is_active else 1)
        d.show()
