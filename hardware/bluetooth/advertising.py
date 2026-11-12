"""Bounded BLE event queue and defensive parser for advertisement metadata."""


class _QueueSlot:
    def __init__(self, address_size=6, adv_size=62):
        self.address = bytearray(address_size)
        self.advertisement = bytearray(adv_size)
        self.address_type = 0
        self.address_length = 0
        self.adv_type = 0
        self.rssi = 0
        self.adv_length = 0


class AdvertisementQueue:
    """Fixed-size ring buffer suitable for the BLE IRQ callback."""
    def __init__(self, capacity=16, adv_size=62):
        if capacity < 1:
            raise ValueError("Queue capacity must be positive")
        # One sentinel slot distinguishes full from empty without a shared
        # count that both the BLE IRQ producer and UI consumer would mutate.
        self.slots = [_QueueSlot(6, adv_size) for _ in range(capacity + 1)]
        self.capacity = capacity
        self.head = 0
        self.tail = 0
        self.dropped = 0

    def clear(self):
        # Call only before scanning starts or after the scanner has stopped.
        self.head = 0
        self.tail = 0
        self.dropped = 0

    def push(self, address_type, address, adv_type, rssi, advertisement):
        next_tail = (self.tail + 1) % len(self.slots)
        if next_tail == self.head:
            if self.dropped < 0x7FFFFFFF:
                self.dropped += 1
            return False
        slot = self.slots[self.tail]
        addr_len = min(len(address), len(slot.address))
        adv_len = min(len(advertisement), len(slot.advertisement))
        for index in range(addr_len):
            slot.address[index] = address[index]
        for index in range(adv_len):
            slot.advertisement[index] = advertisement[index]
        slot.address_type = address_type
        slot.address_length = addr_len
        slot.adv_type = adv_type
        slot.rssi = rssi
        slot.adv_length = adv_len
        # Publish the fully copied slot last; head/tail are single-writer.
        self.tail = next_tail
        return True

    def pop(self):
        if self.head == self.tail:
            return None
        slot = self.slots[self.head]
        item = (slot.address_type,
                bytes(slot.address[:slot.address_length]),
                slot.adv_type, slot.rssi,
                bytes(slot.advertisement[:slot.adv_length]))
        self.head = (self.head + 1) % len(self.slots)
        return item


def _text(value):
    try:
        return value.decode("utf-8")
    except Exception:
        return ""


def parse_advertisement(data):
    """Extract bounded public metadata; never retain arbitrary manufacturer bytes."""
    result = {"name": "", "manufacturer_id": None, "manufacturer": "",
              "service_uuids": [], "ibeacon": None, "malformed": False}
    offset = 0
    try:
        while offset < len(data):
            length = data[offset]
            offset += 1
            if length == 0:
                break
            if offset + length > len(data):
                result["malformed"] = True
                break
            kind = data[offset]
            start = offset + 1
            end = offset + length
            size = end - start
            if kind in (0x08, 0x09) and size and not result["name"]:
                result["name"] = _text(data[start:end])[:24]
            elif kind in (0x02, 0x03):
                pos = start
                while pos + 1 < end and len(result["service_uuids"]) < 8:
                    value = data[pos] | (data[pos + 1] << 8)
                    result["service_uuids"].append("%04X" % value)
                    pos += 2
            elif kind in (0x04, 0x05):
                pos = start
                while pos + 3 < end and len(result["service_uuids"]) < 8:
                    value = (data[pos] | (data[pos + 1] << 8) |
                             (data[pos + 2] << 16) | (data[pos + 3] << 24))
                    result["service_uuids"].append("%08X" % value)
                    pos += 4
            elif kind in (0x06, 0x07):
                pos = start
                while pos + 15 < end and len(result["service_uuids"]) < 8:
                    uuid_hex = "".join("%02X" % data[index]
                                       for index in range(pos + 15, pos - 1, -1))
                    result["service_uuids"].append(
                        uuid_hex[0:8] + "-" + uuid_hex[8:12] + "-" +
                        uuid_hex[12:16] + "-" + uuid_hex[16:20] + "-" + uuid_hex[20:32])
                    pos += 16
            elif kind == 0xFF and size >= 2:
                company = data[start] | (data[start + 1] << 8)
                result["manufacturer_id"] = company
                result["manufacturer"] = "Company 0x%04X (%d B)" % (company, size - 2)
                payload = start + 2
                # Standard Apple iBeacon manufacturer payload.
                if company == 0x004C and end - payload >= 23 and \
                        data[payload] == 0x02 and data[payload + 1] == 0x15:
                    uuid_bytes = data[payload + 2:payload + 18]
                    uuid_hex = "".join("%02X" % byte for byte in uuid_bytes)
                    result["ibeacon"] = {
                        "uuid": (uuid_hex[0:8] + "-" + uuid_hex[8:12] + "-" +
                                 uuid_hex[12:16] + "-" + uuid_hex[16:20] + "-" + uuid_hex[20:32]),
                        "major": (data[payload + 18] << 8) | data[payload + 19],
                        "minor": (data[payload + 20] << 8) | data[payload + 21],
                        "tx_power": data[payload + 22] - 256 if data[payload + 22] > 127
                                    else data[payload + 22],
                    }
            offset += length
    except (IndexError, TypeError, ValueError):
        result["malformed"] = True
    return result
