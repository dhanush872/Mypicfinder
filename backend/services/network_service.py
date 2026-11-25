import socket
from typing import Dict
from backend.config import settings

def get_local_ip() -> str:
    """
    Detect local venue Wi-Fi or hotspot IPv4 address.
    Returns 127.0.0.1 if offline or no network interface found.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Dummy connect to determine the active routing interface
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def get_network_info() -> Dict[str, str]:
    local_ip = get_local_ip()
    port = settings.PORT
    lan_url = f"http://{local_ip}:{port}"
    public_url = settings.PUBLIC_URL or ""
    return {
        "local_ip": local_ip,
        "port": str(port),
        "lan_url": lan_url,
        "public_url": public_url,
    }
