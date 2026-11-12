"""Safe NRF24 construction guard; no third-party radio driver is bundled."""
class NRF24Driver:
    def __init__(self, module_config):
        required = ("spi_id", "sck", "mosi", "miso", "csn", "ce")
        missing = [name for name in required if module_config.get(name) is None]
        if missing:
            raise ValueError("NRF24 pin configuration required: " + ", ".join(missing))
        raise NotImplementedError("Install and connect a supported NRF24 SPI driver")
