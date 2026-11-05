import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402

BOT_TOKEN = "123456:TEST-token"


def sign_init_data(fields: dict, token: str = BOT_TOKEN) -> str:
    """Builds initData the same way Telegram does."""
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    signed = dict(fields, hash=hmac.new(secret, check.encode(), hashlib.sha256).hexdigest())
    return urlencode(signed)


def init_data_for(user_id=1, first_name="Dara", age=0, **extra) -> str:
    fields = {
        "auth_date": str(int(time.time()) - age),
        "user": json.dumps({"id": user_id, "first_name": first_name}),
        "query_id": "AAH",
        **extra,
    }
    return sign_init_data(fields)


@pytest.fixture
def app(tmp_path):
    return create_app(
        Config(
            bot_token=BOT_TOKEN,
            bot_username="decide_bot",
            app_short_name="decide",
            webhook_secret="hook-secret",
            db_path=str(tmp_path / "test.sqlite3"),
        )
    )


class Person:
    """A signed-in Telegram user talking to the API."""

    def __init__(self, app, user_id, name, **extra):
        self.client = app.test_client()
        self.headers = {"Authorization": "tma " + init_data_for(user_id, name, **extra)}

    def get(self, url):
        return self.client.get(url, headers=self.headers)

    def post(self, url, payload=None):
        return self.client.post(url, json=payload if payload is not None else {}, headers=self.headers)


@pytest.fixture
def dara(app):
    return Person(app, 1, "Dara")


@pytest.fixture
def sok(app):
    return Person(app, 2, "Sok")


@pytest.fixture
def lina(app):
    return Person(app, 3, "Lina")


def make_poll(person, mode="single", options=("Pizza", "Noodles", "Rice"), **extra):
    response = person.post(
        "/api/polls", {"question": "Where should we eat lunch?", "mode": mode, "options": list(options), **extra}
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()
