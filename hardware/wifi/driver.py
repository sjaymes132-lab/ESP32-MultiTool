"""Read-only STA interface adapter; does not enable or connect during construction."""
import gc


def _free_heap():
    try:
        return gc.mem_free()
    except Exception:
        return None


def heap_snapshot(collect=False):
    """Return best-effort GC heap readings without masking a radio failure."""
    errors = []
    if collect:
        try:
            gc.collect()
        except Exception as exc:
            errors.append("gc.collect: " + str(exc))
    free = None
    allocated = None
    try:
        free = gc.mem_free()
    except Exception as exc:
        errors.append("gc.mem_free: " + str(exc))
    try:
        allocated = gc.mem_alloc()
    except Exception as exc:
        errors.append("gc.mem_alloc: " + str(exc))
    return free, allocated, "; ".join(errors)


class WiFiAdapter:
    def __init__(self):
        import network
        wlan_type = network.WLAN
        # MicroPython v1.29 documents WLAN.IF_STA; retain STA_IF for older
        # ESP32 firmware builds that exposed the legacy module-level alias.
        interface_id = getattr(wlan_type, "IF_STA", None)
        if interface_id is None:
            interface_id = getattr(network, "STA_IF", None)
        if interface_id is None:
            raise RuntimeError("Wi-Fi station interface constant is unavailable")
        self.interface = wlan_type(interface_id)
        self.heap_free_before = None
        self.heap_free_after = None
        self.heap_allocated_before = None
        self.heap_allocated_after = None
        self.heap_diagnostic_error = ""
        self.raw_result_count = 0
        self.last_stage = "WLAN object ready"
        self.last_error = None

    def scan(self):
        self.heap_free_before = None
        self.heap_free_after = None
        self.heap_allocated_before = None
        self.heap_allocated_after = None
        self.heap_diagnostic_error = ""
        self.raw_result_count = 0
        self.last_error = None
        self.last_stage = "WLAN scan preflight"
        if not hasattr(self.interface, "scan"):
            raise RuntimeError("Wi-Fi scan API unavailable")
        was_active = self.interface.active()
        was_connected = self.interface.isconnected() if was_active else False
        operation_error = None
        try:
            if not was_active:
                self.last_stage = "Wi-Fi activation"
                self.interface.active(True)
                if not self.interface.active():
                    raise RuntimeError("Wi-Fi interface did not become active")
            self.last_stage = "Pre WLAN.scan heap snapshot"
            free, allocated, diagnostic_error = heap_snapshot(collect=True)
            self.heap_free_before = free
            self.heap_allocated_before = allocated
            if diagnostic_error:
                self.heap_diagnostic_error = diagnostic_error
            self.last_stage = "WLAN.scan()"
            results = self.interface.scan()
            try:
                self.raw_result_count = len(results)
            except TypeError:
                self.raw_result_count = 0
            self.last_stage = "Post WLAN.scan heap snapshot"
            free, allocated, diagnostic_error = heap_snapshot(collect=True)
            self.heap_free_after = free
            self.heap_allocated_after = allocated
            if diagnostic_error:
                self.heap_diagnostic_error = diagnostic_error
            return results
        except Exception as exc:
            operation_error = exc
            self.last_error = exc
            # Diagnostic work is strictly best-effort; it must never replace
            # the original exception raised by WLAN or the adapter.
            try:
                free, allocated, diagnostic_error = heap_snapshot(collect=True)
                self.heap_free_after = free
                self.heap_allocated_after = allocated
                if diagnostic_error:
                    self.heap_diagnostic_error = diagnostic_error
            except Exception as diagnostic_exc:
                self.heap_diagnostic_error = "heap snapshot: " + str(diagnostic_exc)
            raise
        finally:
            if not was_active and not was_connected:
                if operation_error is None:
                    self.last_stage = "Wi-Fi interface restore"
                try:
                    if self.interface.active():
                        self.interface.active(False)
                except Exception:
                    # Keep the scan exception as the primary failure. If the
                    # scan succeeded, a failed restore is still a real error.
                    if operation_error is None:
                        raise

    def deinit(self):
        """Disable the station interface when an owner explicitly releases it."""
        if self.interface.active():
            self.interface.active(False)

    def active(self):
        return self.interface.active()

    def isconnected(self):
        return self.interface.isconnected()

    def ifconfig(self):
        return self.interface.ifconfig()

    def mac(self):
        return self.interface.config("mac")

    def rssi(self):
        return self.interface.status("rssi")
