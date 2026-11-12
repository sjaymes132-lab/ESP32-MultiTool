"""Safe CC1101 construction guard; no third-party radio driver is bundled."""
class CC1101Driver:
    def __init__(self, module_config):
        required = ("spi_id", "sck", "mosi", "miso", "csn")
        missing = [name for name in required if module_config.get(name) is None]
        if missing:
            raise ValueError("CC1101 pin configuration required: " + ", ".join(missing))
        raise NotImplementedError("Install and connect a supported CC1101 SPI driver")
