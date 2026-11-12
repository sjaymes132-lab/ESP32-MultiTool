"""Hardware and UI defaults for ESP32-S3 N16R8."""
OLED_WIDTH = 128
OLED_HEIGHT = 128
OLED_SDA = 8
OLED_SCL = 9
OLED_ADDRESS = 0x3C
# The supplied working demo uses rotate=90; the bundled driver explicitly supports it.
OLED_ROTATION = 90
JOYSTICK_PINS = {"up": 4, "down": 5, "left": 6, "right": 7, "select": 15}
BUZZER_PIN = 12
INPUT_DEBOUNCE_MS = 35
INPUT_REPEAT_DELAY_MS = 450
INPUT_REPEAT_INTERVAL_MS = 140
SOUND_ENABLED = True
UI_SOUNDS_ENABLED = True
DISPLAY_BRIGHTNESS = 128  # SH1107.contrast() accepts 0..255.
MENU_ROWS = 6
MENU_ROW_HEIGHT = 16
HEADER_HEIGHT = 16
TEXT_MARQUEE_ENABLED = True
TEXT_MARQUEE_START_DELAY_MS = 700
TEXT_MARQUEE_END_PAUSE_MS = 850
TEXT_MARQUEE_STEP_MS = 32

# External hardware is intentionally unassigned until the user's wiring is known.
NRF24_MODULES = (
    {"name": "Module 1", "spi_id": None, "sck": None, "mosi": None, "miso": None, "csn": None, "ce": None},
    {"name": "Module 2", "spi_id": None, "sck": None, "mosi": None, "miso": None, "csn": None, "ce": None},
)
CC1101_MODULES = (
    {"name": "Module 1", "spi_id": None, "sck": None, "mosi": None, "miso": None, "csn": None, "gdo0": None, "gdo2": None},
    {"name": "Module 2", "spi_id": None, "sck": None, "mosi": None, "miso": None, "csn": None, "gdo0": None, "gdo2": None},
)
GPS_UART_ID = 1
GPS_TX_PIN = 17
GPS_RX_PIN = 16
GPS_BAUDRATE = 9600
