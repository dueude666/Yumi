import subprocess
import sys


if __name__ == "__main__":
    cmd = [sys.executable, "-m", "streamlit", "run", "app/ui/streamlit_app.py"]
    subprocess.run(cmd, check=False)

