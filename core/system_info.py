"""Feature-detected ESP32/MicroPython information helpers."""
import gc
import sys


def _text(value):
    try:
        return str(value)
    except Exception:
        return "Unavailable"


def device_lines():
    lines = []
    try:
        import os
        uname = os.uname()
        lines.append("Board: " + _text(getattr(uname, "machine", "Unavailable")))
        lines.append("Release: " + _text(getattr(uname, "release", "Unavailable")))
    except Exception:
        lines.append("Board: Unavailable")
    lines.append("MicroPython: " + _text(getattr(sys, "version", "Unavailable")))
    implementation = getattr(sys, "implementation", None)
    lines.append("Build: " + _text(getattr(implementation, "_build", "Unavailable")))
    try:
        import machine
        lines.append("CPU: %d MHz" % (machine.freq() // 1000000))
    except Exception:
        lines.append("CPU: Unavailable")
    try:
        import machine
        uid = machine.unique_id()
        lines.append("ID: " + "".join("%02x" % byte for byte in uid))
    except Exception:
        lines.append("ID: Unavailable")
    return lines


def memory_lines():
    lines = []
    try:
        gc.collect()
        free = gc.mem_free()
        used = gc.mem_alloc()
        lines.extend(["Heap free: %d B" % free, "Heap used: %d B" % used,
                      "Heap total: %d B" % (free + used)])
    except Exception:
        lines.extend(["Heap free: Unavailable", "Heap used: Unavailable",
                      "Heap total: Unavailable"])
    try:
        lines.append("GC threshold: " + str(gc.threshold()))
    except Exception:
        lines.append("GC threshold: Unavailable")
    return lines


def storage_lines(path="/"):
    try:
        import os
        stats = os.statvfs(path)
        block_size = stats[0]
        total = stats[2] * block_size
        free = stats[3] * block_size
        return ["Path: " + path, "Total: %d B" % total,
                "Used: %d B" % (total - free), "Free: %d B" % free]
    except Exception:
        return ["Filesystem: Unavailable"]


def uptime_seconds(start_ticks, now_ticks, ticks_diff):
    return ticks_diff(now_ticks, start_ticks) // 1000

