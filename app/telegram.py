"""Thin wrapper around the Telegram Bot API, plus deep-link building."""
import requests
from flask import current_app


class TelegramError(Exception):
    pass


def call(method: str, **payload) -> dict:
    cfg = current_app.config["APP"]
    if not cfg.bot_token:
        raise TelegramError("BOT_TOKEN is not set")
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{cfg.bot_token}/{method}", json=payload, timeout=10
        )
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        # Never include the exception text: it can contain the URL with the token.
        raise TelegramError(f"{method} request failed") from exc
    if not data.get("ok"):
        raise TelegramError(f"{method}: {data.get('description', 'unknown error')}")
    return data["result"]


def app_link(start_param: str | None = None) -> str:
    """Direct link that opens the Mini App, optionally carrying a startapp value."""
    cfg = current_app.config["APP"]
    if not (cfg.bot_username and cfg.app_short_name):
        return ""
    link = f"https://t.me/{cfg.bot_username}/{cfg.app_short_name}"
    return f"{link}?startapp={start_param}" if start_param else link


def open_button(text: str, start_param: str | None = None) -> dict:
    """URL button. web_app buttons are not offered in groups, so a t.me link is used."""
    return {"inline_keyboard": [[{"text": text, "url": app_link(start_param)}]]}


def inline_result(poll: dict) -> dict:
    """The message posted into a chat, for inline mode and shareMessage."""
    action = "Spin the wheel" if poll["mode"] == "spin" else "Vote now"
    prefix = "s_" if poll["mode"] == "spin" else "v_"
    return {
        "type": "article",
        "id": poll["id"],
        "title": poll["question"],
        "description": "Send to this chat",
        "input_message_content": {"message_text": f"🗳 {poll['question']}"},
        "reply_markup": open_button(action, prefix + poll["id"]),
    }
