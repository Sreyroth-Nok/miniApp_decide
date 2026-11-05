"""Checks that a request really comes from a Telegram user.

The Mini App sends Telegram.WebApp.initData with every API call. Telegram signs
that string with a key derived from the bot token, so only Telegram and this
server can produce a valid hash. initDataUnsafe must never be trusted.
"""
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from functools import wraps
from urllib.parse import parse_qsl

from flask import current_app, g, jsonify, request


class InvalidInitData(Exception):
    pass


@dataclass
class User:
    id: int
    name: str
    chat_instance: str | None = None
    chat_type: str | None = None


def validate_init_data(raw: str, bot_token: str, max_age: int, now: float | None = None) -> User:
    if not raw or not bot_token:
        raise InvalidInitData("missing init data")

    pairs = parse_qsl(raw, keep_blank_values=True)
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise InvalidInitData("duplicate fields")

    received_hash = fields.pop("hash", None)
    if not received_hash:
        raise InvalidInitData("missing hash")

    # Only `hash` is left out. `signature` stays in: it is excluded only by the
    # separate Ed25519 check that third parties use.
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise InvalidInitData("bad hash")

    try:
        auth_date = int(fields["auth_date"])
        user = json.loads(fields["user"])
        user_id = int(user["id"])
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidInitData("malformed fields") from exc

    if (now if now is not None else time.time()) - auth_date > max_age:
        raise InvalidInitData("expired")

    name = " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p)
    return User(
        id=user_id,
        name=name or user.get("username") or "Someone",
        chat_instance=fields.get("chat_instance"),
        chat_type=fields.get("chat_type"),
    )


def _dev_user(name: str) -> User:
    """A stable fake user for browser testing. Only reachable when DEV_MODE=1."""
    name = name.strip()[:32] or "Tester"
    fake_id = int(hashlib.sha256(name.encode()).hexdigest()[:12], 16)
    return User(
        id=fake_id,
        name=name,
        chat_instance=request.headers.get("X-Dev-Chat") or None,
        chat_type="group" if request.headers.get("X-Dev-Chat") else None,
    )


def require_user(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        cfg = current_app.config["APP"]
        header = request.headers.get("Authorization", "")
        if header.startswith("tma "):
            try:
                g.user = validate_init_data(header[4:], cfg.bot_token, cfg.init_data_max_age)
            except InvalidInitData:
                return jsonify(error="Your session has expired. Close and reopen the app."), 401
        elif cfg.dev_mode and request.headers.get("X-Dev-User"):
            g.user = _dev_user(request.headers["X-Dev-User"])
        else:
            return jsonify(error="Open this app from Telegram."), 401
        return view(*args, **kwargs)

    return wrapped
