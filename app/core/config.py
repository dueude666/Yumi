from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    project_name: str = "Yumi"
    db_path: Path = Path("data/db/yumi.db")
    raw_data_dir: Path = Path("data/raw")
    index_dir: Path = Path("data/index")


settings = Settings()


def ensure_directories() -> None:
    for path in (settings.db_path.parent, settings.raw_data_dir, settings.index_dir):
        path.mkdir(parents=True, exist_ok=True)

