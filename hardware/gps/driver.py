"""Non-blocking UART line collection and conservative NMEA sentence parsing."""
import config
try:
    from time import ticks_ms
except ImportError:
    import time
    ticks_ms = lambda: int(time.time() * 1000)


class NMEAParser:
    def __init__(self):
        self.data = {"fix": False, "latitude": None, "longitude": None,
                     "altitude_m": None, "speed_kmh": None,
                     "satellites": None, "utc": None, "date": None}

    def feed(self, sentence):
        if isinstance(sentence, bytes):
            try:
                sentence = sentence.decode()
            except Exception:
                return False
        sentence = sentence.strip()
        if not sentence.startswith("$") or "*" not in sentence:
            return False
        body, checksum = sentence[1:].rsplit("*", 1)
        value = 0
        for char in body:
            value ^= ord(char)
        try:
            if value != int(checksum[:2], 16):
                return False
            fields = body.split(",")
            kind = fields[0][-3:]
            if kind == "GGA":
                self._gga(fields)
            elif kind == "RMC":
                self._rmc(fields)
            else:
                return False
            return True
        except (IndexError, ValueError, OverflowError):
            return False

    def _coordinate(self, value, hemisphere):
        if not value or hemisphere not in ("N", "S", "E", "W"):
            return None
        number = float(value)
        degrees = int(number // 100)
        minutes = number - degrees * 100
        result = degrees + minutes / 60.0
        maximum = 90 if hemisphere in ("N", "S") else 180
        if (result != result or minutes < 0 or minutes >= 60 or
                degrees > maximum or (degrees == maximum and minutes != 0)):
            return None
        if hemisphere in ("S", "W"):
            result = -result
        return result

    def _gga(self, fields):
        quality = int(fields[6] or "0")
        latitude = self._coordinate(fields[2], fields[3])
        longitude = self._coordinate(fields[4], fields[5])
        self.data["fix"] = quality > 0 and latitude is not None and longitude is not None
        if self.data["fix"]:
            self.data["utc"] = fields[1] or self.data["utc"]
            self.data["latitude"] = latitude
            self.data["longitude"] = longitude
            self.data["satellites"] = int(fields[7]) if fields[7] else None
            self.data["altitude_m"] = float(fields[9]) if fields[9] else None
        else:
            self.data["satellites"] = int(fields[7]) if fields[7] else 0

    def _rmc(self, fields):
        latitude = self._coordinate(fields[3], fields[4])
        longitude = self._coordinate(fields[5], fields[6])
        valid = fields[2] == "A" and latitude is not None and longitude is not None
        self.data["fix"] = valid
        self.data["utc"] = fields[1] or None
        self.data["date"] = fields[9] or None
        if valid:
            self.data["latitude"] = latitude
            self.data["longitude"] = longitude
            self.data["speed_kmh"] = float(fields[7]) * 1.852 if fields[7] else None
        else:
            self.data["speed_kmh"] = None


class GPSDriver:
    def __init__(self, uart_id=None, tx_pin=None, rx_pin=None, baudrate=None):
        uart_id = config.GPS_UART_ID if uart_id is None else uart_id
        tx_pin = config.GPS_TX_PIN if tx_pin is None else tx_pin
        rx_pin = config.GPS_RX_PIN if rx_pin is None else rx_pin
        baudrate = config.GPS_BAUDRATE if baudrate is None else baudrate
        if uart_id is None or tx_pin is None or rx_pin is None or baudrate is None:
            raise ValueError("Configure GPS UART ID, TX, RX and baud rate first")
        from machine import UART, Pin
        self.uart = UART(uart_id, baudrate=baudrate, tx=Pin(tx_pin), rx=Pin(rx_pin))
        self.parser = NMEAParser()
        self.buffer = ""
        self.last_sentence = ""
        self.last_valid_fix_ms = None

    def poll(self):
        available = self.uart.any()
        if not available:
            return False
        chunk = self.uart.read(min(available, 128))
        if not chunk:
            return False
        try:
            self.buffer += chunk.decode()
        except Exception:
            self.buffer += str(chunk)
        updated = False
        received = False
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self.last_sentence = line.strip()
            received = True
            parsed = self.parser.feed(line)
            if parsed and self.parser.data["fix"]:
                self.last_valid_fix_ms = ticks_ms()
            updated = parsed or updated
        if len(self.buffer) > 240:
            self.buffer = self.buffer[-120:]
        return updated or received

    def close(self):
        deinit = getattr(self.uart, "deinit", None)
        if deinit:
            deinit()
