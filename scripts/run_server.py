#!/usr/bin/env python3
"""
Server runner for EventFrame.
Launches FastAPI with Uvicorn, detects local venue Wi-Fi IP address,
and displays instructions for physical camera tethering and Cloudflare Tunneling.
"""
import os
import socket
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from backend.config import settings
from backend.models.database import init_db

def get_local_ip() -> str:
    """Detect local venue Wi-Fi or hotspot IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Dummy connect to determine routing interface (no packets sent)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def main():
    init_db()
    local_ip = get_local_ip()
    port = settings.PORT

    print("\n" + "=" * 68)
    print("  🚀 EventFrame — Local-First Event Photo Delivery Platform")
    print("=" * 68)
    print(f"  • Local Dashboard:     http://localhost:{port}/")
    print(f"  • Venue Wi-Fi Access:  http://{local_ip}:{port}/")
    print(f"  • Storage Directory:   {settings.STORAGE_DIR}")
    print(f"  • Active Face Matcher: {settings.FACE_MATCHER_BACKEND}")
    print("-" * 68)
    print("  🌐 Cloudflare Tunnel Quick-Start (Optional Public HTTPS):")
    print(f"     cloudflared tunnel --url http://localhost:{port}")
    print("=" * 68 + "\n")

    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=port,
        reload=False,
        log_level="info",
    )

if __name__ == "__main__":
    main()
