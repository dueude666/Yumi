import uvicorn
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


if __name__ == "__main__":
    host = os.getenv("YUMI_API_HOST", "127.0.0.1")
    port = int(os.getenv("YUMI_API_PORT", "8000"))
    reload_mode = os.getenv("YUMI_DEV_RELOAD", "0").lower() in {"1", "true", "yes"}
    uvicorn.run("app.api.main:app", host=host, port=port, reload=reload_mode)
