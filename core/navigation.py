"""Bounded navigation stack preserving parent menu selections."""
class Navigation:
    def __init__(self, app, root, max_depth=12):
        self.app = app
        self.stack = [(root, None)]
        self.max_depth = max_depth

    @property
    def current(self):
        return self.stack[-1][0]

    def open(self, screen):
        if len(self.stack) >= self.max_depth:
            print("Navigation stack limit reached")
            return
        self.stack.append((screen, None))
        self.app.invalidate()

    def back(self):
        if len(self.stack) > 1:
            old = self.stack.pop()[0]
            old.on_exit(self.app)
        self.app.invalidate()

    def replace(self, screen):
        old = self.stack.pop()[0]
        old.on_exit(self.app)
        self.stack.append((screen, None))
        self.app.invalidate()
