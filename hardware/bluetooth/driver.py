"""Lazy BLE API wrapper; scanning starts only on an explicit user request."""


def _error_details(exc):
    name = type(exc).__name__
    args = getattr(exc, "args", ())
    if name == "OSError" and args and isinstance(args[0], int):
        return "OSError errno %d: %s" % (args[0], str(exc))
    return name + ": " + str(exc)


class BLEAdapter:
    def __init__(self):
        print("BLE stage: importing bluetooth")
        try:
            import bluetooth
        except Exception as exc:
            raise RuntimeError("BLE module import failed; " + _error_details(exc))
        if not hasattr(bluetooth, "BLE"):
            raise RuntimeError("BLE API unavailable in this firmware")
        try:
            print("BLE stage: constructing bluetooth.BLE()")
            self.interface = bluetooth.BLE()
            print("BLE stage: BLE object constructed")
        except Exception as exc:
            raise RuntimeError("BLE object construction failed; " + _error_details(exc))
        self.enabled = False
        self.scanning = False
        self.scan_failed = False
        self.last_stage = "constructed"
        self.last_error = None

    def _record_error(self, stage, exc):
        self.last_stage = stage
        self.last_error = exc

    def active(self, value=None):
        try:
            if value is None:
                return self.interface.active()
            result = self.interface.active(value)
            if result is None:
                result = self.interface.active()
            self.enabled = bool(value) and bool(result)
            return result
        except Exception as exc:
            self.scan_failed = True
            self.enabled = False
            self._record_error(self.last_stage, exc)
            raise

    def irq(self, handler):
        self.last_stage = "IRQ registration"
        try:
            print("BLE stage: checking active state before IRQ")
            if not self.active():
                raise RuntimeError("Activate BLE before registering an IRQ handler")
            print("BLE stage: registering IRQ callback")
            result = self.interface.irq(handler)
            print("BLE stage: IRQ registration returned")
            return result
        except Exception as exc:
            self._record_error("IRQ registration", exc)
            # An IRQ registration error came from the native BLE API. Avoid
            # further controller calls because its state cannot be confirmed.
            self.scan_failed = True
            raise

    def activate(self):
        """Activate the radio and verify that the firmware reports it ready."""
        self.last_stage = "BLE activation"
        try:
            print("BLE stage: querying current active state")
            current = self.active()
            print("BLE stage: current active state=%s" % current)
            if not current:
                print("BLE stage: calling active(True)")
                self.active(True)
                print("BLE stage: active(True) returned")
            print("BLE stage: verifying active state")
            if not self.active():
                raise RuntimeError("BLE radio did not become active")
            self.enabled = True
            print("BLE stage: activation verified")
            return True
        except Exception as exc:
            self._record_error("BLE activation", exc)
            self.scan_failed = True
            raise

    def scan(self, duration_ms=8000, interval_us=None, window_us=None):
        if self.scan_failed:
            raise RuntimeError("BLE scan previously failed; restart before retrying")
        if self.scanning:
            raise RuntimeError("BLE scan is already running")
        if interval_us is not None and window_us is not None and \
                (interval_us <= 0 or window_us <= 0 or window_us > interval_us):
            raise ValueError("BLE scan window must be positive and no longer than interval")
        self.last_stage = "BLE scan preflight"
        # The UI explicitly activates before registering IRQ. Avoid running
        # the full activation sequence again, but verify that the adapter is
        # still active before GAP scan startup.
        if not self.enabled or not self.active():
            self.enabled = False
            self.activate()
        self.scanning = True
        self.last_stage = "gap_scan startup"
        try:
            # Use firmware defaults unless a validated user preference is set.
            if interval_us is None or window_us is None:
                print("BLE stage: gap_scan(%d) using MicroPython defaults" % duration_ms)
                self.interface.gap_scan(duration_ms)
            else:
                print("BLE stage: gap_scan(%d, %d, %d)" %
                      (duration_ms, interval_us, window_us))
                self.interface.gap_scan(duration_ms, interval_us, window_us)
            print("BLE stage: gap_scan returned")
        except Exception as exc:
            # The scan state is unknown after a native API error. Do not issue
            # another GAP operation as speculative cleanup.
            self.scanning = False
            self.scan_failed = True
            self.enabled = False
            self._record_error("gap_scan startup", exc)
            raise

    def stop_scan(self):
        if self.scanning:
            self.last_stage = "BLE scan stop"
            try:
                print("BLE stage: gap_scan(None) stop")
                self.interface.gap_scan(None)
                self.scanning = False
            except Exception as exc:
                self.scan_failed = True
                self.enabled = False
                self._record_error("BLE scan stop", exc)
                raise

    def scan_done(self):
        self.scanning = False

    def deactivate(self):
        """Stop a live scan and disable BLE only when this adapter enabled it."""
        if self.scan_failed:
            # Avoid further calls into a stack that already rejected gap_scan.
            # Raising keeps HardwareManager from treating this instance as
            # cleanly deinitialized and automatically retrying it.
            raise RuntimeError("BLE state uncertain after scan error; restart before retrying")
        error = None
        self.last_stage = "BLE scan stop"
        try:
            self.stop_scan()
        except Exception as exc:
            self._record_error("BLE scan stop", exc)
            # Do not call active(False) after a failed GAP stop request.
            raise
        if self.enabled:
            self.last_stage = "BLE deactivation"
            try:
                print("BLE stage: calling active(False)")
                self.active(False)
                print("BLE stage: active(False) returned")
            except Exception as exc:
                self.scan_failed = True
                self._record_error("BLE deactivation", exc)
                if error is None:
                    error = exc
        if error is not None:
            raise error

    def deinit(self):
        self.deactivate()
