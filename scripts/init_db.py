import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.db import init_db


if __name__ == "__main__":
    init_db()
    print("Database initialized: data/db/yumi.db")
