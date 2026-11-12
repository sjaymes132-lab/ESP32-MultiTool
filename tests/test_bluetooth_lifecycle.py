"""Host-side BLE adapter tests using a fake MicroPython bluetooth module."""
import sys
import types
import unittest

from hardware.bluetooth.driver import BLEAdapter
from tools.bluetooth.screens import BLEScanScreen


class FakeBLE:
    def __init__(self, activate_result=True, scan_error=None, irq_error=None,
                 activation_error=None):
        self.is_active = False
        self.activate_result = activate_result
        self.scan_error = scan_error
        self.irq_error = irq_error
        self.activation_error = activation_error
        self.scan_calls = []
        self.active_calls = []
        self.call_order = []
        self.handler = None

    def active(self, value=None):
        if value is None:
            return self.is_active
        self.active_calls.append(value)
        if value:
            self.call_order.append("active(True)")
            if self.activation_error:
                raise self.activation_error
        if value:
            self.is_active = self.activate_result
        else:
            self.is_active = False
        return self.is_active

    def irq(self, handler):
        self.call_order.append("irq")
        if self.irq_error:
            raise self.irq_error
        self.handler = handler

    def gap_scan(self, *args):
        self.call_order.append("gap_scan")
        self.scan_calls.append(args)
        if self.scan_error:
            raise self.scan_error


class BLEAdapterTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeBLE()
        bluetooth = types.ModuleType("bluetooth")
        bluetooth.BLE = lambda: self.fake
        self.previous = sys.modules.get("bluetooth")
        sys.modules["bluetooth"] = bluetooth

    def tearDown(self):
        if self.previous is None:
            del sys.modules["bluetooth"]
        else:
            sys.modules["bluetooth"] = self.previous

    def test_scan_activates_and_uses_documented_default_parameters(self):
        adapter = BLEAdapter()
        adapter.scan(4000)
        self.assertTrue(adapter.enabled)
        self.assertTrue(adapter.scanning)
        self.assertEqual(self.fake.active_calls, [True])
        self.assertEqual(self.fake.scan_calls, [(4000,)])

    def test_scan_passes_valid_configured_interval_and_window(self):
        adapter = BLEAdapter()
        adapter.scan(4000, 1280000, 11250)
        self.assertEqual(self.fake.scan_calls, [(4000, 1280000, 11250)])
        self.assertEqual(self.fake.active_calls, [True])

    def test_irq_registration_requires_active_radio(self):
        adapter = BLEAdapter()
        with self.assertRaisesRegex(RuntimeError, "Activate BLE"):
            adapter.irq(lambda event, data: None)
        self.assertIsNone(self.fake.handler)

    def test_second_scan_is_rejected_while_one_is_active(self):
        adapter = BLEAdapter()
        adapter.scan(4000)
        with self.assertRaisesRegex(RuntimeError, "already running"):
            adapter.scan(4000)
        self.assertEqual(self.fake.scan_calls, [(4000,)])

    def test_screen_ignores_select_while_scan_is_active(self):
        screen = BLEScanScreen()
        screen.scanning = True
        screen.ble = types.SimpleNamespace(scanning=True)
        screen._start()
        self.assertEqual(screen.status, "Scan already active")

    def test_select_stops_ble_scan_and_releases_radio_lease(self):
        class Adapter:
            def __init__(self):
                self.stopped = False
            def deactivate(self):
                self.stopped = True

        class Hardware:
            def __init__(self):
                self.failed = None
            def fail(self, name, error):
                self.failed = (name, error)

        from core.radio_manager import RadioManager
        adapter = Adapter()
        radio = RadioManager()
        self.assertTrue(radio.acquire("ble_scan"))
        screen = BLEScanScreen()
        screen.scanning = True
        screen.ble = adapter
        app = types.SimpleNamespace(radio=radio, hardware=Hardware())
        self.assertTrue(screen.handle(app, "select"))
        self.assertTrue(adapter.stopped)
        self.assertFalse(screen.scanning)
        self.assertFalse(radio.busy())

    def test_screen_activates_before_irq_registration_and_scan(self):
        adapter = BLEAdapter()

        class Hardware:
            def initialise(self, name):
                self.name = name
                return adapter

            def fail(self, name, error):
                raise AssertionError("unexpected BLE failure")

            def error(self, name):
                return ""

        app = types.SimpleNamespace(hardware=Hardware(), ble_devices=[])
        screen = BLEScanScreen(app)
        screen._start()
        self.assertEqual(self.fake.call_order, ["active(True)", "irq", "gap_scan"])
        self.assertEqual(self.fake.active_calls, [True])
        self.assertEqual(screen.status, "Scanning... SELECT stops")

    def test_failed_activation_never_starts_scan(self):
        self.fake.activate_result = False
        adapter = BLEAdapter()
        with self.assertRaisesRegex(RuntimeError, "did not become active"):
            adapter.scan(4000)
        self.assertEqual(self.fake.scan_calls, [])

    def test_scan_error_prevents_further_native_cleanup_calls(self):
        self.fake.scan_error = OSError("scan rejected")
        adapter = BLEAdapter()
        with self.assertRaisesRegex(OSError, "scan rejected"):
            adapter.scan(4000)
        with self.assertRaisesRegex(RuntimeError, "state uncertain"):
            adapter.deactivate()
        self.assertTrue(adapter.scan_failed)
        self.assertEqual(self.fake.active_calls, [True])
        self.assertEqual(self.fake.scan_calls, [(4000,)])

    def test_uncertain_scan_failure_releases_lease_but_blocks_other_radio_work(self):
        from core.radio_manager import RadioManager
        self.fake.scan_error = OSError(5, "EIO")
        adapter = BLEAdapter()
        class Hardware:
            def initialise(self, _name):
                return adapter
            def error(self, _name):
                return ""
            def fail(self, _name, _error):
                return None
        radio = RadioManager()
        app = types.SimpleNamespace(hardware=Hardware(), radio=radio, ble_devices=[])
        screen = BLEScanScreen(app)
        screen._start()
        self.assertFalse(radio.owner)
        self.assertFalse(radio.busy())
        self.assertTrue(radio.blocked())
        self.assertIn("gap_scan startup failed", screen.status)
        self.assertIn("errno 5", screen.status)
        self.assertNotIn("cleanup:", screen.status)
        self.assertFalse(radio.acquire("wifi_scan"))

    def test_activation_oserror_is_reported_at_activation_stage(self):
        self.fake.activation_error = OSError(5, "EIO")
        adapter = BLEAdapter()
        with self.assertRaises(OSError):
            adapter.scan(4000)
        self.assertEqual(adapter.last_stage, "BLE activation")
        self.assertEqual(self.fake.call_order, ["active(True)"])
        self.assertEqual(self.fake.scan_calls, [])

    def test_screen_reports_activation_stage_and_releases_radio_lease(self):
        self.fake.activation_error = OSError(5, "EIO")
        adapter = BLEAdapter()
        from core.radio_manager import RadioManager
        class Hardware:
            def initialise(self, _name):
                return adapter
            def fail(self, _name, _error):
                return True
            def error(self, _name):
                return ""
        radio = RadioManager()
        app = types.SimpleNamespace(hardware=Hardware(), radio=radio, ble_devices=[])
        screen = BLEScanScreen(app)
        screen._start()
        self.assertIn("BLE activation failed", screen.status)
        self.assertIn("errno 5", screen.status)
        self.assertFalse(radio.busy())
        self.assertTrue(radio.blocked())
        self.assertEqual(self.fake.scan_calls, [])

    def test_irq_oserror_is_reported_and_scan_never_starts(self):
        self.fake.irq_error = OSError(5, "EIO")
        adapter = BLEAdapter()
        adapter.activate()
        with self.assertRaises(OSError):
            adapter.irq(lambda *_args: None)
        self.assertEqual(adapter.last_stage, "IRQ registration")
        self.assertEqual(self.fake.call_order, ["active(True)", "irq"])
        self.assertEqual(self.fake.scan_calls, [])
        self.assertTrue(adapter.scan_failed)
        with self.assertRaisesRegex(RuntimeError, "state uncertain"):
            adapter.deactivate()
        self.assertEqual(self.fake.active_calls, [True])

    def test_scan_stop_error_does_not_attempt_ble_deactivation(self):
        class StopFailBLE(FakeBLE):
            def gap_scan(self, *args):
                self.call_order.append("gap_scan")
                self.scan_calls.append(args)
                if args == (None,):
                    raise OSError(5, "EIO stop")
        fake = StopFailBLE()
        bluetooth = sys.modules["bluetooth"]
        bluetooth.BLE = lambda: fake
        adapter = BLEAdapter()
        adapter.activate()
        adapter.irq(lambda *_args: None)
        adapter.scan(4000)
        with self.assertRaisesRegex(OSError, "EIO stop"):
            adapter.deactivate()
        self.assertTrue(adapter.scan_failed)
        self.assertEqual(fake.active_calls, [True])

    def test_ble_constructor_error_preserves_stage_and_os_error(self):
        bluetooth = sys.modules["bluetooth"]
        bluetooth.BLE = lambda: (_ for _ in ()).throw(OSError(5, "EIO"))
        with self.assertRaisesRegex(RuntimeError, "BLE object construction failed.*errno 5"):
            BLEAdapter()


if __name__ == "__main__":
    unittest.main()
