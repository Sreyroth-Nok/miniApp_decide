"""Run once after deploying: python scripts/set_webhook.py

Points the bot at this server and sets the command list.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app, telegram  # noqa: E402


def main() -> None:
    app = create_app()
    cfg = app.config["APP"]
    missing = [
        name
        for name, value in {
            "BOT_TOKEN": cfg.bot_token,
            "PUBLIC_URL": cfg.public_url,
            "WEBHOOK_SECRET": cfg.webhook_secret,
        }.items()
        if not value
    ]
    if missing:
        sys.exit(f"Set these in .env first: {', '.join(missing)}")
    if not cfg.public_url.startswith("https://"):
        sys.exit("PUBLIC_URL must start with https://")

    with app.app_context():
        telegram.call(
            "setWebhook",
            url=f"{cfg.public_url}/tg/webhook",
            secret_token=cfg.webhook_secret,
            allowed_updates=["message", "inline_query"],
        )
        telegram.call(
            "setMyCommands",
            commands=[
                {"command": "start", "description": "Open Decision Maker"},
                {"command": "new", "description": "Start a poll or spin wheel"},
                {"command": "decide", "description": "Make a quick group decision"},
                {"command": "help", "description": "What this bot can do"},
            ],
        )
    print(f"Webhook set to {cfg.public_url}/tg/webhook")


if __name__ == "__main__":
    main()
