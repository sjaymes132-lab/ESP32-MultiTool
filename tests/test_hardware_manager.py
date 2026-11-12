"""Host-side tests for lazy hardware lifecycle transitions."""
import threading
import unittest

from core.hardware_manager import (
    FAILED,
    INITIALISING,
    NOT_CONFIGURED,
    READY,
    STOPPING,
    UNINITIALISED,
    HardwareManager,
)


class HardwareManagerTests(unittest.TestCase):
    def test_initialise_is_cached_while_ready(self):
        calls = []
        manager = HardwareManager()
        manager.register("test", lambda: calls.append(1) or object())

        first = manager.initialise("test")
        self.assertIs(manager.initialise("test"), first)
        self.assertEqual(len(calls), 1)
        self.assertEqual(manager.status("test"), READY)

    def test_concurrent_initialise_does_not_start_second_factory(self):
        started = threading.Event()
        finish = threading.Event()
        calls = []

        def factory():
            calls.append(1)
            started.set()
            finish.wait(2)
            return object()

        manager = HardwareManager()
        manager.register("test", factory)
        worker = threading.Thread(target=manager.initialise, args=("test",))
        worker.start()
        self.assertTrue(started.wait(2))
        self.assertEqual(manager.status("test"), INITIALISING)
        self.assertIsNone(manager.initialise("test"))
        self.assertEqual(len(calls), 1)
        finish.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(manager.status("test"), READY)

    def test_failed_initialise_is_cached_until_explicit_cleanup(self):
        calls = []

        def factory():
            calls.append(1)
            raise OSError("native init failed")

        manager = HardwareManager()
        manager.register("test", factory)
        self.assertIsNone(manager.initialise("test"))
        self.assertIsNone(manager.initialise("test"))
        self.assertEqual(calls, [1])
        self.assertEqual(manager.status("test"), FAILED)
        self.assertEqual(manager.error("test"), "native init failed")
        self.assertEqual(manager.error_detail("test"), "OSError: native init failed")

    def test_cleanup_is_called_once_then_instance_can_be_recreated(self):
        class Device:
            def __init__(self):
                self.closed = 0

            def deinit(self):
                self.closed += 1

        devices = []

        def factory():
            device = Device()
            devices.append(device)
            return device

        manager = HardwareManager()
        manager.register("test", factory)
        first = manager.initialise("test")
        self.assertTrue(manager.deinitialise("test"))
        self.assertEqual(manager.status("test"), UNINITIALISED)
        self.assertFalse(manager.deinitialise("test"))
        self.assertEqual(first.closed, 1)
        self.assertIsNot(manager.initialise("test"), first)
        self.assertEqual(len(devices), 2)

    def test_failed_cleanup_keeps_instance_for_inspection(self):
        class Device:
            def deinit(self):
                raise OSError("cleanup failed")

        manager = HardwareManager()
        manager.register("test", Device)
        device = manager.initialise("test")
        self.assertFalse(manager.deinitialise("test"))
        self.assertEqual(manager.status("test"), FAILED)
        self.assertIs(manager.records["test"].instance, device)
        self.assertEqual(manager.error("test"), "cleanup failed")
        self.assertNotEqual(manager.status("test"), STOPPING)

    def test_unconfigured_module_does_not_call_factory(self):
        calls = []
        manager = HardwareManager()
        manager.register("test", lambda: calls.append(1), configured=False)
        self.assertIsNone(manager.initialise("test"))
        self.assertEqual(manager.status("test"), NOT_CONFIGURED)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
