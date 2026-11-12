"""Host-side tests for bounded Wi-Fi and BLE metadata processing."""
import unittest
import sys
import types

from tools.wifi.analysis import (normalise_record, normalise_results, sort_results, statistics,
                                 bounded_scan_results)
from tools.wifi.network_scan import (_private_range, LocalNetworkScanScreen,
                                    _check_socket_timeout, _sockaddr)
from tools.wifi.survey import observation_count, MAX_OBSERVATIONS, WardriveScreen
from tools.wifi.screens import CSIActivityScreen, NetworkScanScreen, wifi_error_text
from hardware.bluetooth.advertising import AdvertisementQueue, parse_advertisement
from core.radio_manager import RadioManager
from hardware.wifi.driver import WiFiAdapter
from core.settings_manager import SettingsManager
from tools.wifi.menu import build_menu as build_wifi_menu
from tools.bluetooth.menu import build_menu as build_bluetooth_menu
from ui.screens import MenuScreen


class WiFiAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.raw = [
            (b"Office", b"\x00\x11\x22\x33\x44\x55", 6, -40, 3, 0),
            (b"", b"\x00\x11\x22\x33\x44\x66", 11, -83, 0, 1),
            (b"Office", b"\x00\x11\x22\x33\x44\x77", 1, -65, 4, 0),
        ]

    def test_hidden_network_and_documented_tuple_fields(self):
        row = normalise_record(self.raw[1])
        self.assertEqual(row["display_ssid"], "<hidden>")
        self.assertTrue(row["hidden"])
        self.assertEqual(row["channel"], 11)
        self.assertEqual(row["security_name"], "Open")

    def test_invalid_tuple_is_skipped_and_results_are_bounded(self):
        rows = normalise_results(self.raw + [(b"bad",)], 2)
        self.assertEqual(len(rows), 2)

    def test_bounded_scan_processes_every_row_retains_strongest_and_releases_raw_refs(self):
        raw = list(self.raw) + [(b"broken",)]
        rows, total = bounded_scan_results(raw, 2)
        self.assertEqual(total, 3)
        self.assertEqual(len(rows), 2)
        self.assertEqual(sorted(row["rssi"] for row in rows), [-65, -40])
        self.assertEqual(raw, [None] * len(raw))

    def test_wifi_error_reporting_distinguishes_heap_and_os_errors(self):
        self.assertIn("MemoryError", wifi_error_text(MemoryError()))
        message = wifi_error_text(OSError(5, "EIO"))
        self.assertIn("OSError errno 5", message)
        self.assertNotIn("out of memory", message.lower())

    def test_sorting_and_analysis(self):
        rows = normalise_results(self.raw)
        self.assertEqual(sort_results(rows, "rssi")[0]["rssi"], -40)
        self.assertEqual(sort_results(rows, "channel")[0]["channel"], 1)
        summary = statistics(rows)
        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["open_count"], 1)
        self.assertEqual(summary["channels"][6], 1)
        self.assertEqual(summary["duplicate_ssids"], ["office"])

    def test_private_subnet_only_and_bounded(self):
        hosts = _private_range("192.168.4.10", "255.255.255.0")
        self.assertLessEqual(len(hosts), 32)
        self.assertNotIn("192.168.4.10", hosts)
        with self.assertRaisesRegex(ValueError, "RFC1918"):
            _private_range("8.8.8.8", "255.255.255.0")
        with self.assertRaisesRegex(ValueError, "contiguous"):
            _private_range("192.168.4.10", "255.0.255.0")

    def test_survey_limit_counts_access_points_not_scan_batches(self):
        session = {"observations": [{"aps": [{"bssid": str(i)} for i in range(24)]}
                                     for _ in range(4)]}
        self.assertEqual(observation_count(session), MAX_OBSERVATIONS)


class BLEAdvertisementTests(unittest.TestCase):
    def test_fixed_queue_copies_callback_memoryviews_and_drops_when_full(self):
        queue = AdvertisementQueue(1, 8)
        address = bytearray(b"123456")
        adv = bytearray(b"abc")
        self.assertTrue(queue.push(0, memoryview(address), 0, -50, memoryview(adv)))
        address[0] = 0
        adv[0] = 0
        self.assertFalse(queue.push(0, address, 0, -20, adv))
        self.assertEqual(queue.dropped, 1)
        item = queue.pop()
        self.assertEqual(item[1], b"123456")
        self.assertEqual(item[4], b"abc")

    def test_fixed_queue_wraps_without_overwriting_unread_entries(self):
        queue = AdvertisementQueue(2, 8)
        self.assertTrue(queue.push(0, b"123456", 0, -40, b"one"))
        self.assertTrue(queue.push(0, b"abcdef", 0, -50, b"two"))
        self.assertFalse(queue.push(0, b"zzzzzz", 0, -60, b"three"))
        self.assertEqual(queue.pop()[4], b"one")
        self.assertTrue(queue.push(0, b"zzzzzz", 0, -60, b"three"))
        self.assertEqual([queue.pop()[4], queue.pop()[4]], [b"two", b"three"])

    def test_malformed_advertisement_does_not_raise(self):
        result = parse_advertisement(b"\x05\x09ab")
        self.assertTrue(result["malformed"])

    def test_iBeacon_fields_are_parsed(self):
        payload = (b"\x1a\xff\x4c\x00\x02\x15" + bytes(range(16)) +
                   b"\x00\x07\x00\x09\xc5")
        parsed = parse_advertisement(payload)
        self.assertEqual(parsed["manufacturer_id"], 0x004C)
        self.assertEqual(parsed["ibeacon"]["major"], 7)
        self.assertEqual(parsed["ibeacon"]["minor"], 9)
        self.assertEqual(parsed["ibeacon"]["tx_power"], -59)

    def test_service_uuid_is_parsed(self):
        parsed = parse_advertisement(b"\x03\x03\x0f\x18")
        self.assertEqual(parsed["service_uuids"], ["180F"])


class RadioManagerTests(unittest.TestCase):
    def test_radio_scan_leases_are_exclusive_and_releasable(self):
        radio = RadioManager()
        self.assertTrue(radio.acquire("wifi_scan"))
        self.assertFalse(radio.acquire("ble_scan"))
        self.assertTrue(radio.busy())
        self.assertFalse(radio.release("ble_scan"))
        self.assertTrue(radio.release("wifi_scan"))
        self.assertFalse(radio.busy())

    def test_uncertain_native_radio_state_blocks_future_leases(self):
        radio = RadioManager()
        self.assertTrue(radio.acquire("ble_scan"))
        radio.block("native scan state uncertain")
        self.assertTrue(radio.release("ble_scan"))
        self.assertFalse(radio.busy())
        self.assertTrue(radio.blocked())
        self.assertFalse(radio.acquire("wifi_scan"))

    def test_exiting_wifi_scan_requests_worker_cancellation(self):
        app = types.SimpleNamespace(settings=None)
        screen = NetworkScanScreen(app, live=True)
        screen.running = True
        screen.on_exit(app)
        self.assertTrue(screen.cancel_requested)
        self.assertFalse(screen.live)

    def test_survey_reports_gps_uart_poll_failure_without_fake_fix(self):
        class BrokenGPS:
            def poll(self):
                raise OSError("UART disconnected")

        screen = WardriveScreen(geotag=True)
        screen.gps = BrokenGPS()
        self.assertIsNone(screen._fix())
        self.assertIn("UART disconnected", screen.gps_error)

    def test_survey_rejects_stale_fix(self):
        import time
        class StaleGPS:
            parser = types.SimpleNamespace(data={"fix": True, "latitude": 51.0,
                                                  "longitude": -1.0, "altitude_m": 10})
            last_valid_fix_ms = int(time.time() * 1000) - 6000

            def poll(self):
                return False

        screen = WardriveScreen(geotag=True)
        screen.gps = StaleGPS()
        self.assertIsNone(screen._fix())

    def test_survey_waiting_for_fix_does_not_hold_radio_lease(self):
        class GPS:
            parser = types.SimpleNamespace(data={"fix": False})
            last_valid_fix_ms = None
            def poll(self):
                return False
        class Hardware:
            def initialise(self, name):
                return GPS() if name == "gps" else types.SimpleNamespace()
            def error(self, _name):
                return ""
        app = types.SimpleNamespace(radio=RadioManager(), hardware=Hardware())
        screen = WardriveScreen(geotag=True)
        screen._begin(app)
        self.assertTrue(screen.waiting_fix)
        self.assertFalse(app.radio.busy())
        screen.handle(app, "select")
        self.assertFalse(app.radio.busy())

    def test_survey_scan_error_does_not_poison_cached_wifi_driver(self):
        class WLAN:
            def scan(self):
                raise OSError(12, "Wifi out of memory")
        class Hardware:
            failed = False
            def fail(self, _name, _exc):
                self.failed = True
        class Settings:
            def get(self, _key):
                return 2000
        hardware = Hardware()
        radio = RadioManager()
        screen = WardriveScreen(geotag=False)
        screen.wlan = WLAN()
        screen.running = True
        screen.lease_held = True
        app = types.SimpleNamespace(hardware=hardware, radio=radio, settings=Settings())
        screen._worker(app)
        self.assertIn("Wifi out of memory", screen.status)
        self.assertFalse(hardware.failed)
        self.assertFalse(radio.busy())

    def test_local_discovery_exit_requests_cancellation(self):
        screen = LocalNetworkScanScreen()
        screen.running = True
        screen.on_exit(types.SimpleNamespace())
        self.assertTrue(screen.cancel_requested)

    def test_csi_requires_connected_wifi_and_releases_lease(self):
        class Interface:
            def isconnected(self):
                return False

        class WLAN:
            interface = Interface()

            def isconnected(self):
                return self.interface.isconnected()

        class Hardware:
            def initialise(self, _name):
                return WLAN()

        app = types.SimpleNamespace(radio=RadioManager(), hardware=Hardware(), settings=None)
        screen = CSIActivityScreen()
        screen._start(app)
        self.assertIn("Connect to Wi-Fi", screen.error)
        self.assertFalse(app.radio.busy())


class WiFiAdapterTests(unittest.TestCase):
    def _adapter(self, initial_active):
        class Interface:
            def __init__(self):
                self.is_active = initial_active
                self.calls = []

            def active(self, value=None):
                if value is not None:
                    self.calls.append(value)
                    self.is_active = value
                return self.is_active

            def isconnected(self):
                return False

            def scan(self):
                return []

        interface = Interface()
        network = types.ModuleType("network")
        network.STA_IF = 0
        network.WLAN = lambda _mode: interface
        previous = sys.modules.get("network")
        sys.modules["network"] = network
        try:
            return WiFiAdapter(), interface
        finally:
            if previous is None:
                del sys.modules["network"]
            else:
                sys.modules["network"] = previous

    def test_scan_restores_previously_inactive_interface(self):
        adapter, interface = self._adapter(False)
        self.assertEqual(adapter.scan(), [])
        self.assertEqual(interface.calls, [True, False])
        self.assertFalse(interface.is_active)

    def test_scan_leaves_preexisting_interface_active(self):
        adapter, interface = self._adapter(True)
        adapter.scan()
        self.assertEqual(interface.calls, [])
        self.assertTrue(interface.is_active)

    def test_scan_collects_garbage_before_native_scan_and_records_heap(self):
        import hardware.wifi.driver as driver
        events = []
        class FakeGC:
            def collect(self):
                events.append("collect")
            def mem_free(self):
                events.append("mem_free")
                return 4096 + len(events)
        class Interface:
            def active(self, value=None):
                return True
            def isconnected(self):
                return False
            def scan(self):
                events.append("scan")
                return [(b"ap", b"123456", 1, -40, 3, 0)]
        network = types.ModuleType("network")
        network.WLAN = lambda _mode: Interface()
        network.STA_IF = 0
        previous_network = sys.modules.get("network")
        previous_gc = driver.gc
        sys.modules["network"] = network
        driver.gc = FakeGC()
        try:
            adapter = WiFiAdapter()
            raw = adapter.scan()
        finally:
            driver.gc = previous_gc
            if previous_network is None:
                del sys.modules["network"]
            else:
                sys.modules["network"] = previous_network
        self.assertEqual(events[0], "collect")
        self.assertLess(events.index("collect"), events.index("scan"))
        self.assertEqual(adapter.raw_result_count, 1)
        self.assertIsNotNone(adapter.heap_free_before)
        self.assertIsNotNone(adapter.heap_free_after)
        self.assertEqual(len(raw), 1)

    def test_scan_exception_is_not_replaced_by_heap_diagnostic_failure(self):
        import hardware.wifi.driver as driver
        class BrokenGC:
            def collect(self):
                raise RuntimeError("mock gc diagnostic failure")
            def mem_free(self):
                raise RuntimeError("mock heap diagnostic failure")
            def mem_alloc(self):
                raise RuntimeError("mock heap diagnostic failure")
        class Interface:
            def active(self, value=None):
                return True
            def isconnected(self):
                return False
            def scan(self):
                raise RuntimeError("Wifi out of memory")
        network = types.ModuleType("network")
        network.WLAN = lambda _mode: Interface()
        network.STA_IF = 0
        previous_network = sys.modules.get("network")
        previous_gc = driver.gc
        sys.modules["network"] = network
        driver.gc = BrokenGC()
        try:
            adapter = WiFiAdapter()
            with self.assertRaisesRegex(RuntimeError, "Wifi out of memory"):
                adapter.scan()
            self.assertIn("gc.collect", adapter.heap_diagnostic_error)
        finally:
            driver.gc = previous_gc
            if previous_network is None:
                del sys.modules["network"]
            else:
                sys.modules["network"] = previous_network

    def test_scan_attempt_resets_previous_adapter_diagnostics(self):
        adapter, _interface = self._adapter(True)
        adapter.heap_free_before = 123
        adapter.heap_free_after = 456
        adapter.raw_result_count = 99
        adapter.scan()
        self.assertNotEqual(adapter.heap_free_before, 123)
        self.assertNotEqual(adapter.heap_free_after, 456)
        self.assertEqual(adapter.raw_result_count, 0)

    def test_adapter_construction_failure_keeps_worker_heap_and_exception_type(self):
        import tools.wifi.screens as wifi_screens
        class Hardware:
            def initialise(self, _name):
                return None
            def error_detail(self, _name):
                return "OSError: Wifi out of memory"
            def error(self, _name):
                return "Wifi out of memory"
        app = types.SimpleNamespace(hardware=Hardware(), settings=None,
                                    wifi_scan_results=[])
        screen = NetworkScanScreen(app)
        old_snapshot = wifi_screens.heap_snapshot
        snapshots = iter([(76000, 24000, "")])
        wifi_screens.heap_snapshot = lambda collect=False: next(snapshots)
        try:
            screen._worker()
        finally:
            wifi_screens.heap_snapshot = old_snapshot
        self.assertIn("Wi-Fi adapter initialization", screen.error)
        self.assertIn("OSError: Wifi out of memory", screen.error)
        self.assertEqual(screen.heap_free_worker_start, 76000)
        self.assertIsNone(screen.heap_free_before)

    def test_v129_wlan_if_sta_constant_is_preferred(self):
        class Interface:
            def active(self, value=None):
                return False
        class WLANType:
            IF_STA = 7
            def __new__(cls, interface_id):
                cls.last_id = interface_id
                return Interface()
        mock = types.ModuleType("network")
        mock.WLAN = WLANType
        previous = sys.modules.get("network")
        sys.modules["network"] = mock
        try:
            WiFiAdapter()
            self.assertEqual(WLANType.last_id, 7)
        finally:
            if previous is None:
                del sys.modules["network"]
            else:
                sys.modules["network"] = previous


class NetworkSocketCompatibilityTests(unittest.TestCase):
    def test_missing_timeout_api_closes_probe_and_fails_closed(self):
        class Probe:
            closed = False
            def close(self):
                self.closed = True
        probe = Probe()
        fake_socket = types.SimpleNamespace(socket=lambda: probe)
        with self.assertRaisesRegex(RuntimeError, "timeout API unavailable"):
            _check_socket_timeout(fake_socket)
        self.assertTrue(probe.closed)

    def test_numeric_local_host_uses_getaddrinfo(self):
        class FakeSocket:
            SOCK_STREAM = 1
            def getaddrinfo(self, host, port, family, socktype):
                self.args = (host, port, family, socktype)
                return [(2, 1, 6, "", (host, port))]
        fake = FakeSocket()
        self.assertEqual(_sockaddr(fake, "192.168.1.4", 80), ("192.168.1.4", 80))
        self.assertEqual(fake.args, ("192.168.1.4", 80, 0, fake.SOCK_STREAM))


class WirelessSettingsTests(unittest.TestCase):
    def test_ble_scan_settings_have_safe_bounds(self):
        settings = SettingsManager(path="__test_settings_missing__.json")
        self.assertFalse(settings._valid("ble_scan_interval_us", 50000))
        self.assertFalse(settings._valid("ble_scan_window_us", 150000))
        self.assertTrue(settings._valid("ble_scan_duration_ms", 8000))


class WirelessMenuTests(unittest.TestCase):
    def _check_menu(self, builder):
        class Navigation:
            def __init__(self):
                self.opened = []

            def open(self, screen):
                self.opened.append(screen)

            def back(self):
                return None

        app = types.SimpleNamespace(navigation=Navigation())
        root = builder(app)
        self.assertIsInstance(root, MenuScreen)
        self.assertTrue(root.entries)
        for entry in root.entries:
            self.assertTrue(callable(entry.action), entry.label)
            entry.action(app)
            if app.navigation.opened:
                child = app.navigation.opened[-1]
                if isinstance(child, MenuScreen):
                    for child_entry in child.entries:
                        self.assertTrue(callable(child_entry.action), child_entry.label)
        return root

    def test_wifi_and_bluetooth_menus_have_actions_for_each_entry(self):
        self._check_menu(build_wifi_menu)
        self._check_menu(build_bluetooth_menu)


if __name__ == "__main__":
    unittest.main()
