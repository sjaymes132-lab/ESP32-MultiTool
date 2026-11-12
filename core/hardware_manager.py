"""Central, lazy hardware registry with guarded module lifecycles."""

UNINITIALISED = "UNINITIALISED"
INITIALISING = "INITIALISING"
READY = "READY"
FAILED = "FAILED"
STOPPING = "STOPPING"
NOT_CONFIGURED = "NOT_CONFIGURED"
DISABLED = "DISABLED"

# Compatibility aliases for existing integrations.
NOT_INITIALISED = UNINITIALISED
ERROR = FAILED

try:
    import _thread
    _LOCK = _thread.allocate_lock
except (ImportError, AttributeError):
    _LOCK = None


class HardwareRecord:
    def __init__(self, name, factory, configured=True):
        self.name = name
        self.factory = factory
        self.configured = configured
        self.status = UNINITIALISED if configured else NOT_CONFIGURED
        self.instance = None
        self.error = ""
        self.error_type = ""


class HardwareManager:
    """Own hardware instances and serialize state changes, not driver calls."""

    def __init__(self):
        self.records = {}
        self.i2c_addresses = []
        try:
            self._lock = _LOCK() if _LOCK is not None else None
        except Exception:
            self._lock = None

    def _acquire(self):
        if self._lock is not None:
            self._lock.acquire()

    def _release(self):
        if self._lock is not None:
            self._lock.release()

    def register(self, name, factory, configured=True):
        self._acquire()
        try:
            self.records[name] = HardwareRecord(name, factory, configured)
        finally:
            self._release()

    def initialise(self, name):
        """Initialize at most once; callers encountering a transition do not wait."""
        self._acquire()
        try:
            record = self.records.get(name)
            if record is None:
                return None
            if record.status == READY:
                return record.instance
            if record.status in (FAILED, INITIALISING, STOPPING, NOT_CONFIGURED, DISABLED):
                return None
            if not record.configured:
                record.status = NOT_CONFIGURED
                return None
            record.status = INITIALISING
            record.error = ""
            record.error_type = ""
            factory = record.factory
        finally:
            self._release()

        try:
            instance = factory()
            if instance is None:
                raise RuntimeError("Driver returned no device")
        except Exception as exc:
            self._acquire()
            try:
                record.instance = None
                record.status = FAILED
                record.error = str(exc)
                record.error_type = type(exc).__name__
            finally:
                self._release()
            return None

        self._acquire()
        try:
            record.instance = instance
            record.status = READY
            record.error = ""
            record.error_type = ""
        finally:
            self._release()
        return instance

    def fail(self, name, error):
        """Cache an operation-level driver failure without dropping its native handle."""
        self._acquire()
        try:
            record = self.records.get(name)
            if record is None or record.status not in (READY, FAILED):
                return False
            record.status = FAILED
            record.error = str(error)
            record.error_type = type(error).__name__
            return True
        finally:
            self._release()

    def get(self, name):
        self._acquire()
        try:
            record = self.records.get(name)
            return record.instance if record and record.status == READY else None
        finally:
            self._release()

    def status(self, name):
        self._acquire()
        try:
            record = self.records.get(name)
            return record.status if record else DISABLED
        finally:
            self._release()

    def error(self, name):
        self._acquire()
        try:
            record = self.records.get(name)
            return record.error if record else "Unknown hardware module"
        finally:
            self._release()

    def error_detail(self, name):
        """Return the cached exception type and message for diagnostics."""
        self._acquire()
        try:
            record = self.records.get(name)
            if record is None:
                return "Unknown hardware module"
            if not record.error:
                return ""
            return (record.error_type + ": " if record.error_type else "") + record.error
        finally:
            self._release()

    def deinitialise(self, name):
        """Stop a ready or failed instance once; never race an init/stop transition."""
        self._acquire()
        try:
            record = self.records.get(name)
            if record is None or record.status in (INITIALISING, STOPPING):
                return False
            if record.status == NOT_CONFIGURED or record.instance is None:
                return False
            if record.status not in (READY, FAILED):
                return False
            instance = record.instance
            record.status = STOPPING
        finally:
            self._release()

        try:
            close = getattr(instance, "deinit", None)
            if close is None:
                close = getattr(instance, "close", None)
            if close is not None:
                close()
        except Exception as exc:
            self._acquire()
            try:
                record.status = FAILED
                record.error = str(exc)
                record.error_type = type(exc).__name__
            finally:
                self._release()
            return False

        self._acquire()
        try:
            record.instance = None
            record.status = UNINITIALISED if record.configured else NOT_CONFIGURED
            record.error = ""
            record.error_type = ""
        finally:
            self._release()
        return True
