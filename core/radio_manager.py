"""Non-blocking exclusive leases for shared ESP32 wireless scan operations."""


class RadioManager:
    """Serialize scan sessions while leaving ordinary connected-radio use alone."""
    def __init__(self):
        self.owner = None
        self.failure_reason = None
        try:
            import _thread
            self._lock = _thread.allocate_lock()
        except (ImportError, AttributeError):
            self._lock = None

    def _enter(self):
        if self._lock is not None:
            self._lock.acquire()

    def _leave(self):
        if self._lock is not None:
            self._lock.release()

    def acquire(self, owner):
        self._enter()
        try:
            if self.failure_reason is not None:
                return False
            if self.owner is None:
                self.owner = owner
                return True
            return self.owner == owner
        finally:
            self._leave()

    def release(self, owner):
        self._enter()
        try:
            if self.owner == owner:
                self.owner = None
                return True
            return False
        finally:
            self._leave()

    def busy(self):
        self._enter()
        try:
            return self.owner is not None
        finally:
            self._leave()

    def blocked(self):
        self._enter()
        try:
            return self.failure_reason is not None
        finally:
            self._leave()

    def block(self, reason):
        """Fail closed after a native radio error leaves hardware state uncertain."""
        self._enter()
        try:
            self.failure_reason = str(reason)
        finally:
            self._leave()
