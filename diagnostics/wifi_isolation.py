"""Standalone STA scan diagnostic; does not import the application or UI."""
import gc


def heap(label):
    try:
        gc.collect()
    except Exception as exc:
        print("Wi-Fi diagnostic: GC before %s failed: %s" %
              (label, repr(exc)))
    try:
        free = gc.mem_free()
    except Exception as exc:
        free = "unavailable (%s: %s)" % (type(exc).__name__, repr(exc))
    try:
        allocated = gc.mem_alloc()
    except Exception as exc:
        allocated = "unavailable (%s: %s)" % (type(exc).__name__, repr(exc))
    print("Wi-Fi diagnostic: %s heap free=%s allocated=%s" %
          (label, free, allocated))


print("Wi-Fi diagnostic: importing network")
try:
    import network
except Exception as exc:
    print("Wi-Fi diagnostic: network import failed: %s: %s" %
          (type(exc).__name__, repr(exc)))
    raise

wlan = None
changed_active = False
scan_completed = False
failed_stage = None
try:
    heap("before WLAN object")
    stage = "WLAN object construction"
    print("Wi-Fi diagnostic: constructing WLAN.IF_STA")
    interface_id = network.WLAN.IF_STA
    wlan = network.WLAN(interface_id)
    print("Wi-Fi diagnostic: WLAN object constructed")

    was_active = wlan.active()
    print("Wi-Fi diagnostic: initial active state=%s" % repr(was_active))
    if not was_active:
        stage = "Wi-Fi activation"
        print("Wi-Fi diagnostic: calling active(True)")
        wlan.active(True)
        changed_active = True
        active_after = wlan.active()
        print("Wi-Fi diagnostic: active state after request=%s" % repr(active_after))
        if not active_after:
            raise RuntimeError("WLAN did not become active")

    heap("immediately before WLAN.scan")
    stage = "WLAN.scan()"
    print("Wi-Fi diagnostic: calling WLAN.scan()")
    results = wlan.scan()
    scan_completed = True
    print("Wi-Fi diagnostic: scan returned %d rows" % len(results))
    for index in range(min(3, len(results))):
        print("Wi-Fi diagnostic: sample[%d]=%s" % (index, repr(results[index])))
    del results
    heap("after releasing scan result list")
except Exception as exc:
    failed_stage = stage
    print("Wi-Fi diagnostic: %s failed: %s: %s" %
          (stage, type(exc).__name__, repr(exc)))
    heap("after failed operation")
finally:
    # Do not issue more driver operations after a scan or activation error.
    # Deactivate only after a normal scan return and only if this script enabled it.
    if wlan is not None and changed_active and scan_completed and not failed_stage:
        try:
            print("Wi-Fi diagnostic: deactivating after successful scan")
            wlan.active(False)
            print("Wi-Fi diagnostic: deactivation returned")
        except Exception as exc:
            print("Wi-Fi diagnostic: deactivation failed: %s: %s" %
                  (type(exc).__name__, repr(exc)))
print("Wi-Fi diagnostic: finished")
