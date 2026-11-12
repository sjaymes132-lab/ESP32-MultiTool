"""Standalone BLE stack check; run on the ESP32 from the REPL.

This deliberately avoids importing the ESP MULTI TOOL application or touching
its display, joystick, Wi-Fi, GPS, or external radio modules.
"""
import time

print("BLE diagnostic: importing bluetooth")
try:
    import bluetooth
except Exception as exc:
    print("BLE diagnostic: import failed:", repr(exc))
    raise

ble = None
radio_active = False
scan_started = False
scan_done = False
failed_stage = None
DURATION_MS = 8000
INTERVAL_US = 1280000
WINDOW_US = 11250
USE_EXPLICIT_SCAN_PARAMS = True


def ble_irq(event, data):
    # Keep the callback allocation-free and only record scan completion.
    global scan_done
    if event == 6:  # MicroPython _IRQ_SCAN_DONE
        scan_done = True


stage = "bluetooth import"
try:
    print("BLE diagnostic: constructing bluetooth.BLE()")
    stage = "BLE object construction"
    ble = bluetooth.BLE()
    print("BLE diagnostic: BLE object constructed")

    print("BLE diagnostic: activating BLE")
    stage = "BLE activation"
    active_result = ble.active(True)
    print("BLE diagnostic: active(True) returned", repr(active_result))
    radio_active = bool(ble.active())
    print("BLE diagnostic: active state is", radio_active)
    if not radio_active:
        raise RuntimeError("BLE did not report active after active(True)")

    print("BLE diagnostic: installing scan completion callback")
    stage = "IRQ registration"
    ble.irq(ble_irq)

    print("BLE diagnostic: starting scan (duration=%d ms, interval=%d us, window=%d us)" %
          (DURATION_MS, INTERVAL_US, WINDOW_US))
    stage = "gap_scan startup"
    if USE_EXPLICIT_SCAN_PARAMS:
        ble.gap_scan(DURATION_MS, INTERVAL_US, WINDOW_US)
    else:
        ble.gap_scan(DURATION_MS)
    scan_started = True
    deadline = time.ticks_add(time.ticks_ms(), DURATION_MS + 2000)
    while not scan_done and time.ticks_diff(deadline, time.ticks_ms()) > 0:
        time.sleep_ms(50)
    if scan_done:
        print("BLE diagnostic: scan completion callback received")
    else:
        print("BLE diagnostic: no completion callback before timeout; radio state uncertain")
except Exception as exc:
    failed_stage = stage
    print("BLE diagnostic: %s failed: %s: %s" %
          (stage, type(exc).__name__, repr(exc)))
finally:
    # Do not make another native call after any operation error or uncertain
    # scan completion. A firmware assert cannot be recovered by Python cleanup.
    if ble is not None and radio_active and scan_started and scan_done and not failed_stage:
        stage = "BLE deactivation after successful scan"
        try:
            print("BLE diagnostic: deactivating after normal scan completion")
            ble.active(False)
            print("BLE diagnostic: deactivation returned")
        except Exception as exc:
            print("BLE diagnostic: %s failed: %s: %s" %
                  (stage, type(exc).__name__, repr(exc)))
print("BLE diagnostic: finished")
