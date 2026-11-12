# ESP MULTI TOOL
THIS IS NOT YET FINISHED AND EXTREMELY EXPERIMENTAL. DO NOT USE IF YOUR EXPECTING A WORKING FINISHED FW



Modular MicroPython firmware for the ESP32-S3 N16R8, built around the existing 128x128 SH1107 OLED driver. The UI starts with built-in hardware only: GPS uses the supplied UART1 wiring, while external radio module pins remain unset until verified.

## Project structure



Package `__init__.py` files are present in the directories that need Python package imports. The earlier one-file wrappers are retained with `legacy_` filenames to avoid import-name collisions with the per-tool folders; the main app registers package menus through `tools/registry.py`.

## Hardware pins

| Function | Pin / setting |
|---|---|
| OLED SDA / SCL | GPIO8 / GPIO9 |
| OLED I²C address | `0x3C` |
| OLED rotation | 90 degrees |
| Joystick UP / DOWN / LEFT / RIGHT / SELECT | GPIO4 / 5 / 6 / 7 / 15 |
| Buzzer | GPIO12, PWM |
| GPS UART1 RX / TX / baud | GPIO16 / GPIO17 / 9600 (as supplied for this board) |
| NRF24, CC1101 | External pins remain unset until verified against actual wiring |

Do not copy sample pin values from unrelated hardware examples. Fill the external module fields in `config.py` only after checking your actual wiring. The external radio slots have separate dictionaries for Module 1 and Module 2.

## Boot and application services

On MicroPython, `main.py` is the application entry point. It creates the display, joystick input manager, optional sound manager, settings store and hardware registry. It then registers the tool menu builders, creates the root menu, and polls `App.update()` every 10 ms.

`DisplayManager.from_hardware()` creates I²C bus 0 at 100 kHz, scans for `0x3C`, and creates the existing `SH1107_I2C` driver using 128x128 and rotation 90. This required OLED must answer at startup; missing optional NRF24, CC1101, GPS, Wi-Fi or BLE hardware does not prevent menu startup. Buzzer PWM failure is reported as unavailable and does not stop the UI.

`InputManager` owns all joystick reads. Pins use pull-ups and active-low logic. It debounces button transitions, emits individual press/release events, repeats UP/DOWN after the configured delay, and ignores multi-button chords until all buttons are released. Tools receive input through the active shared screen; they must not start a second input loop.

`Navigation` keeps a bounded stack of screens. Opening a child pushes it; LEFT or Back pops it. The parent menu object remains on the stack, including its selected item.

The renderer uses the SH1107 driver’s 8x8 framebuffer text, fill, line, rectangle, pixel, contrast, inversion and `show()` methods. Menu rows, labels, titles and footers are clipped to the 128-pixel width. Six 16-pixel rows fit below the header. Content screens scroll when needed.

## Main menu and tool registration

The root order is in `tools/registry.py` (`TOOL_ORDER`). That file maps each name to a package `build_menu(app)` function. `ui/menu_builder.py` turns that order into the root screen; `App.open_tool()` opens the registered menu. Each tool folder owns its menu and screens.

To add a tool:

1. Create `tools/example/__init__.py`, `menu.py`, and any screens or helper modules it needs.
2. Add a `build_menu(app)` function returning a shared `ui.screens.MenuScreen`.
3. Add the name to `TOOL_ORDER` and add the builder to `register_tools()` in `tools/registry.py`.
4. Use `app.display`, `app.input`, `app.sound`, `app.hardware`, `app.settings`, and `app.navigation`. Do not create another OLED, joystick reader, or buzzer.

Example:

```python
from tools.common import submenu, show_message

def build_menu(app):
    return submenu("Example", ["Status"], {
        "Status": show_message("Example", "Ready for implementation")
    })
```

For a custom screen, subclass `core.screen_manager.Screen`, implement `render(app)` and `handle(app, button)`, and optionally implement `update(app)` for a cooperative, non-blocking poll. Return `True` from `update` only when the screen needs a redraw. Use `on_exit(app)` to stop a scan or release a tool-owned resource.

## Hardware integration

`HardwareManager` stores a module’s status, instance and initialization error. Lifecycle states are `UNINITIALISED`, `INITIALISING`, `READY`, `FAILED`, and `STOPPING`; `NOT_CONFIGURED` and `DISABLED` describe modules that cannot be started. Initialization is lazy and serialized: a concurrent request during initialization returns without starting a second factory, and failures are cached until the instance is explicitly deinitialized. Cleanup is only called for a constructed instance.

Wi-Fi and BLE adapters initialise only when a selected tool needs them. `core/radio_manager.py` gives discovery operations an exclusive lease, so Wi-Fi and BLE scans do not overlap. Wi-Fi scan results and BLE callback observations are bounded in RAM. The BLE IRQ writes fixed-size copies to a queue; parsing and drawing happen later in the normal screen update. BLE activation is verified before IRQ registration and scan start. A native BLE operation failure is reported and not retried automatically.

If a BLE native scan/stop failure leaves radio state uncertain, wireless leases are released but the shared radio manager blocks further wireless operations until restart. This avoids starting Wi-Fi while the BLE stack may still be active. `_thread` is optional and experimental in MicroPython; discovery screens fail closed when thread support or bounded socket timeouts are unavailable.

GPS configuration is `GPS_UART_ID`, `GPS_TX_PIN`, `GPS_RX_PIN`, and `GPS_BAUDRATE` in `config.py` (UART1, RX GPIO16, TX GPIO17, 9600 baud from the board details supplied). `hardware/gps/driver.py` collects UART bytes without waiting, validates NMEA checksums, and parses standard GGA and RMC fields. GPS screens show `NOT_CONFIGURED` or `NO FIX` until actual valid data is available, and change a fix to `STALE` if valid data stops arriving for five seconds. They do not synthesize coordinates.

NRF24 and CC1101 configuration uses two independent entries in `config.py`. The driver classes validate that required pins are provided, then clearly report that a compatible device driver still needs to be installed/integrated. No radio register access, receive operation or transmission is implemented here. No GPIO assignments are assumed.

To integrate another hardware driver, add a factory to `HardwareManager` during startup and register it with a `configured` check based on the required user-provided settings. Screens call `app.hardware.initialise(name)` only after selection, then display the manager’s status/error. Leave the module `NOT_CONFIGURED` if any required pin or setting is missing.

## Wireless suites

Wi-Fi and BLE adapters initialise only when a selected tool needs them. `core/radio_manager.py` gives discovery operations an exclusive lease, so Wi-Fi and BLE scans do not overlap. Wi-Fi scan results and BLE callback observations are bounded in RAM. The BLE IRQ writes fixed-size copies to a queue; parsing and drawing happen later in the normal screen update. BLE activation is verified before IRQ registration and scan start. A native BLE operation failure is reported and not retried automatically.

Wi-Fi AP scans use `network.WLAN.scan()` and show actual SSID (including hidden-network labels), BSSID, RSSI, channel and security metadata. Sorting, filtering, bounded analysis, saved AP-only snapshots and CSV export are available. The app never connects or saves credentials. Without `_thread`, scan screens report that they cannot run without freezing the joystick loop. MicroPython v1.29.0 documents scan fields as `(ssid, bssid, channel, RSSI, security, hidden)`; unknown security values show as Unknown. [WLAN documentation](https://docs.micropython.org/en/v1.29.0/library/network.WLAN.html)

Network diagnostics display the current connection's IP, mask, gateway and DNS. DNS resolution is an explicit threaded request to `micropython.org`; ICMP ping is unavailable. Local service discovery requires explicit confirmation and a connected RFC1918 subnet, limits targets to 32 addresses, tests four common TCP ports with short timeouts, and is cancellable between connection attempts. It does not scan public ranges or exploit services.

The Wi-Fi “sniffer” entries are aggregate only. CSI is opt-in, requires an already-connected station and incoming traffic, and is runtime feature-detected. Raw CSI and MAC fields are discarded; only counters and aggregate RSSI/channel data are displayed. CSI signatures vary by firmware. [WLAN CSI documentation](https://docs.micropython.org/en/v1.29.0/library/network.WLAN.html)

The wardrive screen is an AP survey, not client tracking. Geotagged mode requires a recent valid GPS fix; without one no location sample is recorded. A separate explicit non-geotagged mode is available. Survey data is bounded, buffered and limited to AP metadata, and can be exported/deleted. It uses the shared GPS driver with UART1 RX GPIO16, TX GPIO17, 9600 baud.

### Wireless capability matrix

| Feature | Implemented | Hardware/firmware support | Tested |
|---|---|---|---|
| AP scan and metadata | Yes | Standard WLAN scan; runtime Wi-Fi availability | Host mocked tests; physical scan pending |
| AP sorting/filter/analysis | Yes | Uses actual scan results | Host tests; OLED review pending |
| Connected status/IP/gateway/DNS | Yes | Requires existing Wi-Fi connection | Static only; network test pending |
| DNS resolution | Yes | Connected WLAN, socket API and `_thread` | Not run on device |
| Local TCP service checks | Yes, bounded | Authorised private subnet and `_thread` | Range tests; physical network test pending |
| Wi-Fi CSI aggregate display | Feature-detected | CSI methods, associated station, incoming traffic | Not hardware-tested |
| Raw Wi-Fi packet/management sniffing | No | Requires native firmware extension | Unavailable in this build |
| Remote ID decoding | No | Requires validated decoder and reception path | Unavailable in this build |
| BLE passive advertisements | Yes | Working MicroPython BLE/NimBLE stack | Mock tests; physical scan pending |
| BLE names, RSSI, service UUIDs | Yes | Advertisement fields may be omitted | Host parser tests; physical scan pending |
| iBeacon fields | Yes | Standard manufacturer advertisement format | Host parser tests; physical scan pending |
| Flipper name hint | Limited, low confidence | Advertised local name only; no identity proof | Static only |
| AirTag, card-skimmer, Flock, Meta signatures | No | No validated signature parser included | Unavailable; UI says so |
| BLE connection/GATT inspection | No | Outside this passive observer | Unavailable |
| BLE export/permanent identifier history | No | Intentionally avoided for privacy | Unavailable |
| Fox Hunt selection/history | No | Own-beacon monitor/history not implemented | Unavailable |

Use discovery only on networks and devices you own or have permission to assess. BLE observations remain temporary and bounded in RAM. RSSI proximity estimates are approximate and cannot establish identity or distance.
## System diagnostics

The System menu is defined in `tools/system/menu.py`; its special screens live in `tools/system/screens.py`.

- **Device information:** feature-detects `os.uname()`, `sys.version`, `sys.implementation._build`, `machine.freq()` and `machine.unique_id()`. Unsupported calls show “Unavailable.”
- **Memory:** calls `gc.collect()` and, when available, reports `gc.mem_free()`, `gc.mem_alloc()`, their GC heap sum, and `gc.threshold()`.
- **Storage:** calls `os.statvfs('/')` and reports total, used and free bytes; unsupported firmware shows “Filesystem: Unavailable.”
- **Hardware status:** reports that the OLED initialized, joystick pins were configured, buzzer PWM availability, the actual startup I²C addresses, SPI/UART API presence, and optional module manager states. API presence is not the same as an instantiated bus or a healthy peripheral.
- **I²C Bus Scan:** displays the startup results and lets the user request another scan. A response proves only that an address acknowledged the scan; it does not prove full device health.
- **System Monitor:** refreshes about once a second with application uptime, CPU frequency, free heap and current screen.
- **Input Test:** displays live debounced joystick state.
- **Display Test:** offers pixel grid, border, text, inversion, refresh and temporary contrast changes. LEFT restores configured contrast and the prior inversion state.
- **Buzzer Test:** adjusts frequency (200–5000 Hz) and duration (80 or 200 ms), then plays only when selected. The tone stops from the regular application loop.
- **Utilities:** garbage collection is an explicit menu action. Restart is guarded by a confirmation screen whose default selection is No.

These features are implemented in software but still need physical board testing. None of the menu text is a claim that a speaker, OLED pixel, or GPIO has been electrically measured.

## Settings and persistence

`SettingsManager` stores validated preferences in `settings.json` in the device working directory. It writes only when a setting changes. Missing or invalid files fall back to safe defaults. The Reset Settings confirmation restores preferences only; it does not overwrite `config.py` or external hardware pins.

The settings UI includes contrast, sound enable, UI sound effects, debounce, repeat delay/speed, music tempo/volume and a fixed monochrome theme note. Contrast uses the driver’s supported 0–255 `contrast()` API. The monochrome theme is fixed by the SH1107 display.

## Text layout and long labels

`ui/text_renderer.py` is the shared fixed-font text helper. It measures the SH1107 driver's 8x8 font, wraps descriptions at word boundaries, and adds an ellipsis when a fixed one-line label must be shortened. Long selected menu/list entries use a single non-blocking pixel marquee; only the focused row animates. Short entries remain still. `core/display_manager.py` owns drawing and routes long information through `render_document()`, which keeps the title and footer visible while UP/DOWN scroll the wrapped body.

For a new screen, use `app.display.render_document(title, lines, offset, footer)` for descriptions or diagnostics. Keep an `offset` integer and adjust it on UP/DOWN, clamped to `0..max(0, len(wrapped_lines) - 12)`. For menu screens, pass a stable `marquee_key` to `render_lines()` and call `update_marquee()` from the screen's non-blocking `update()` method. Do not add sleeps to animate text.

Marquee defaults are in `config.py`: `TEXT_MARQUEE_ENABLED`, `TEXT_MARQUEE_START_DELAY_MS`, `TEXT_MARQUEE_END_PAUSE_MS`, and `TEXT_MARQUEE_STEP_MS`. The renderer uses the existing built-in font and the SH1107 driver's dirty-page updates; it adds no font or graphics dependency.

## Buzzer music player

The player engine is `core/music_player.py`; original short tune definitions are in `assets/tunes/library.py`. A tune is a sequence of `(frequency_hz, beat_units)` pairs; zero frequency is a rest. Add another dictionary to `TUNES` without changing the engine.

The player uses the same shared PWM buzzer service as UI sounds. Notes advance from `App.update()` without sleeping. SELECT plays/pauses, RIGHT advances, UP/DOWN select tunes while stopped or adjust tempo during playback, and LEFT stops and exits. UI sound feedback is suppressed while music is playing. Hardware volume, timing and speaker output still need physical verification.

## Copying and starting

Copy `main.py`, `config.py`, `sh1107.py`, `umenu.py`, and the `core/`, `ui/`, `hardware/`, `tools/`, and `assets/` directories to the ESP32-S3 filesystem, keeping package `__init__.py` files. `settings.json` is created after the first preference change. Reset the board to run `main.py`, or start from the REPL with `import main; main.main()`.

## Validation performed

Software-side checks run on the development host:

- Python syntax compilation and imports across the app, hardware adapters and tool packages.
- Mock startup through the first app-loop tick with no optional external modules present.
- Main menu/tool registry construction and settings validation/persistence.
- NMEA checksum rejection and coordinate conversion.
- Music play/pause/resume/stop state transitions with a fake clock and buzzer.
- Hardware manager unavailable/error behavior and cached initialization failure.
- Wi-Fi scan rendering with mocked firmware results.
- Shared text wrapping, ellipsis, long-label marquee timing/focus reset, and partial-row drawing with a fake 128x128 display.
- Text and list layout boundary checks plus nested navigation/selection preservation after renderer integration.

No physical ESP32-S3 or attached OLED, joystick, buzzer, radio or GPS module was available for this work. Run the board checklist below before relying on hardware behavior.

## Hardware test checklist

1. Boot with the OLED connected at `0x3C`; verify orientation, six-row menu layout, contrast and I²C startup.
2. Press each joystick direction separately; verify debounce, one press event, UP/DOWN hold repeat and live Input Test states.
3. Press two buttons together; verify the chord is ignored until all buttons are released.
4. Open nested menus, return with LEFT and Back, and verify parent selection is retained.
5. Check Device, Memory and Storage screens against available firmware/REPL information; confirm unsupported APIs say Unavailable.
6. Run the I²C rescan and compare displayed addresses with connected devices.
7. Test Display Test modes, then confirm configured contrast and normal inversion are restored on exit.
8. Run the short buzzer test, adjust its frequency/duration, disable sound, and confirm no tone plays while disabled.
9. Play, pause, resume, skip and stop each tune; verify joystick input remains responsive.
10. Only after entering actual external pin/baud configuration, initialize each module independently and verify status before using any future hardware-specific operation.
