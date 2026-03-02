import subprocess
import sys
import os
import socket
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _get_local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


if __name__ == "__main__":
    host = os.getenv("YUMI_UI_HOST", "0.0.0.0")
    port = os.getenv("YUMI_UI_PORT", "8501")
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app/ui/streamlit_app.py",
        "--server.address",
        host,
        "--server.port",
        str(port),
        "--browser.gatherUsageStats",
        "false",
    ]
    lan_ip = _get_local_ip()
    print(f"Yumi UI listening on http://{lan_ip}:{port} and http://127.0.0.1:{port}")
    subprocess.run(cmd, check=False)
