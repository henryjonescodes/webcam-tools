import socket
from typing import Optional

from zeroconf import Zeroconf, ServiceInfo

HOSTNAME = "webcam-tools"


def _local_ip() -> str:
    """Best-effort LAN IP: opens a UDP socket toward a public address (no
    packet actually sent) so the OS picks the real outbound interface,
    instead of the loopback address gethostname() often returns."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def start(port: int) -> Optional[Zeroconf]:
    """Advertises http://webcam-tools.local:<port> over mDNS so phones/other
    devices on the LAN can reach it without typing an IP. Requires the
    client device to support mDNS (iOS/Android/macOS do out of the box;
    other Windows PCs need Bonjour or similar installed). Best-effort: if
    registration fails for any reason (no network, port in use, etc.) the
    app still runs fine on its IP, just without the friendly name.
    """
    try:
        zc = Zeroconf()
        ip = _local_ip()
        info = ServiceInfo(
            "_http._tcp.local.",
            f"{HOSTNAME}._http._tcp.local.",
            addresses=[socket.inet_aton(ip)],
            port=port,
            server=f"{HOSTNAME}.local.",
        )
        zc.register_service(info)
        return zc
    except Exception:
        return None


def stop(zc: Optional[Zeroconf]):
    if zc is None:
        return
    try:
        zc.unregister_all_services()
        zc.close()
    except Exception:
        pass
