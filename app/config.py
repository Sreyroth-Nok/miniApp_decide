"""Settings, read from environment variables or a local .env file."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal .env reader. Real environment variables always win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


@dataclass
class Config:
    bot_token: str = ""
    bot_username: str = ""
    app_short_name: str = ""
    public_url: str = ""
    webhook_secret: str = ""
    db_path: str = str(ROOT / "data.sqlite3")
    dev_mode: bool = False
    init_data_max_age: int = 24 * 60 * 60  # seconds a Telegram login stays valid

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        return cls(
            bot_token=os.environ.get("BOT_TOKEN", ""),
            bot_username=os.environ.get("BOT_USERNAME", "").lstrip("@"),
            app_short_name=os.environ.get("APP_SHORT_NAME", ""),
            public_url=os.environ.get("PUBLIC_URL", "").rstrip("/"),
            webhook_secret=os.environ.get("WEBHOOK_SECRET", ""),
            db_path=os.environ.get("DB_PATH", cls.db_path),
            dev_mode=os.environ.get("DEV_MODE", "0") == "1",
        )
