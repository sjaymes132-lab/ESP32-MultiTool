"""Rate-limited TCP service discovery restricted to the connected RFC1918 subnet."""
from core.screen_manager import Screen, InformationScreen, ConfirmationScreen
from tools.wifi.screens import _wlan, _lease, _release
try:
    from time import ticks_ms, ticks_diff, sleep_ms
except ImportError:
    import time
    ticks_ms = lambda: int(time.time() * 1000)
    ticks_diff = lambda newer, older: newer - older
    sleep_ms = lambda duration: time.sleep(duration / 1000.0)

PORTS = ((22, "SSH"), (80, "HTTP"), (443, "HTTPS"), (445, "SMB"))
MAX_HOSTS = 32
TIMEOUT_SECONDS = 0.15


def _ipv4_number(value):
    parts = str(value).split(".")
    if len(parts) != 4:
        raise ValueError("Invalid IPv4 address")
    result = 0
    for part in parts:
        octet = int(part)
        if octet < 0 or octet > 255:
            raise ValueError("Invalid IPv4 address")
        result = (result << 8) | octet
    return result


def _private_range(ip, mask):
    address = _ipv4_number(ip)
    if not (address >> 24 == 10 or address >> 20 == 0xAC1 or address >> 16 == 0xC0A8):
        raise ValueError("Only RFC1918 private subnets can be scanned")
    mask_value = _ipv4_number(mask)
    inverse_mask = 0xFFFFFFFF ^ mask_value
    if inverse_mask & (inverse_mask + 1):
        raise ValueError("Subnet mask must be contiguous")
    network = address & mask_value
    broadcast = network | inverse_mask
    count = min(MAX_HOSTS, max(0, broadcast - network - 1))
    own = address
    hosts = []
    candidate = network + 1
    while candidate < broadcast and len(hosts) < count:
        if candidate != own:
            hosts.append("%d.%d.%d.%d" % ((candidate >> 24) & 255,
                (candidate >> 16) & 255, (candidate >> 8) & 255, candidate & 255))
        candidate += 1
    return hosts


def _check_socket_timeout(socket_module):
    """Fail before scanning if the port cannot bound each blocking connect."""
    probe = socket_module.socket()
    try:
        settimeout = getattr(probe, "settimeout", None)
        if settimeout is None:
            raise RuntimeError("Socket timeout API unavailable; discovery disabled")
        settimeout(TIMEOUT_SECONDS)
    finally:
        probe.close()


def _sockaddr(socket_module, host, port):
    """Resolve even numeric hosts through the portable MicroPython API."""
    matches = socket_module.getaddrinfo(host, port, 0, socket_module.SOCK_STREAM)
    if not matches:
        raise OSError("No address returned for local host")
    return matches[0][-1]


class LocalNetworkScanScreen(Screen):
    """User-confirmed, bounded local TCP connect checks; no public-range option."""
    def __init__(self):
        self.started = False
        self.running = False
        self.cancel_requested = False
        self.status = "Only scan networks you own or may assess."
        self.results = []
        self.progress = 0
        self.total = 0
        self.error = ""
        self.version = 0
        self.rendered_version = 0
        self.last_render_ms = 0

    def _start(self, app):
        if not _lease(app, "wifi_discovery"):
            reason = getattr(getattr(app, "radio", None), "failure_reason", None)
            self.status = "Radio unavailable: " + reason if reason else "Radio busy with another scan"
            return
        try:
            wlan = _wlan(app)
            if not wlan.isconnected():
                raise RuntimeError("Connect to a private Wi-Fi network first")
            values = wlan.ifconfig()
            hosts = _private_range(values[0], values[1])
            if not hosts:
                raise RuntimeError("No scannable hosts in this subnet")
        except Exception as exc:
            self.status = str(exc)
            _release(app, "wifi_discovery")
            return False
        self.started = True
        self.running = True
        self.cancel_requested = False
        self.results = []
        self.progress = 0
        self.total = len(hosts)
        self.status = "Scanning confirmed private subnet"
        try:
            import _thread
            _thread.start_new_thread(self._worker, (app, hosts))
        except Exception as exc:
            self.running = False
            self.error = "Thread support unavailable: " + str(exc)
            self.status = self.error
            _release(app, "wifi_discovery")
            return False
        return True

    def _worker(self, app, hosts):
        import socket
        try:
            _check_socket_timeout(socket)
            for host in hosts:
                if self.cancel_requested:
                    break
                open_services = []
                for port, name in PORTS:
                    if self.cancel_requested:
                        break
                    sock = None
                    try:
                        sock = socket.socket()
                        sock.settimeout(TIMEOUT_SECONDS)
                        sock.connect(_sockaddr(socket, host, port))
                        open_services.append(name)
                    except Exception:
                        pass
                    finally:
                        if sock is not None:
                            try:
                                sock.close()
                            except Exception:
                                pass
                if open_services:
                    self.results.append({"ip": host, "services": open_services})
                self.progress += 1
                self.version += 1
                # Rate-limit per host and keep the UI thread independent.
                sleep_ms(50)
            self.status = "Stopped" if self.cancel_requested else "Scan complete"
        except Exception as exc:
            self.error = str(exc)
            self.status = "Scan error: " + str(exc)
        finally:
            self.running = False
            self.version += 1
            app.local_service_results = self.results
            _release(app, "wifi_discovery")

    def update(self, app):
        now = ticks_ms()
        if self.version != self.rendered_version and (not self.running or
                ticks_diff(now, self.last_render_ms) >= 250):
            self.rendered_version = self.version
            self.last_render_ms = now
            return True
        return False

    def render(self, app):
        self.rendered_version = self.version
        self.last_render_ms = ticks_ms()
        lines = [self.status]
        if self.running:
            lines.append("Hosts: %d/%d" % (self.progress, self.total))
            lines.append("Found: %d" % len(self.results))
        else:
            lines.extend(["Found: %d" % len(self.results), "TCP only; 4 ports/host"])
            lines.extend([row["ip"] + " " + "/".join(row["services"])
                          for row in self.results[:6]])
        app.display.render_document("Local Discovery", lines, 0,
                                    "SEL Cancel" if self.running else "SEL Start L Back")

    def handle(self, app, button):
        if button == "left":
            app.navigation.back()
            return True
        if button == "select":
            if self.running:
                self.cancel_requested = True
                self.status = "Cancelling..."
            elif not self.started:
                app.navigation.open(ConfirmationScreen("Authorised Scan",
                    "Scan up to 32 hosts on the connected private subnet for four common TCP services?",
                    lambda: "Discovery started" if self._start(app) else None))
                return True
            else:
                self._start(app)
            return True
        return False

    def on_exit(self, app):
        if self.running:
            self.cancel_requested = True


def export_results(rows, path="local_services.csv"):
    try:
        with open(path, "w") as stream:
            stream.write("ip,services\n")
            for row in rows[:MAX_HOSTS]:
                stream.write('"%s","%s"\n' %
                    (row["ip"], ";".join(row["services"])))
        return True
    except Exception:
        return False
