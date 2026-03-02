import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


if __name__ == "__main__":
    cmd = [sys.executable, "-m", "streamlit", "run", "app/ui/streamlit_app.py"]
    subprocess.run(cmd, check=False)
