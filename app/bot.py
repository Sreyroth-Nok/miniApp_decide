"""Webhook for the bot side: /start, /new and inline mode."""
import hmac
import logging

from flask import Blueprint, current_app, jsonify, request

from . import telegram
from .db import get_db

bp = Blueprint("bot", __name__)
log = logging.getLogger(__name__)


def _handle_message(message: dict) -> None:
    text = (message.get("text") or "").strip()
    if not text.startswith("/"):
        return
    head, _, param = text.partition(" ")
    command = head.split("@", 1)[0]
    chat_id = message["chat"]["id"]

    if command == "/start" and param:
        telegram.call(
            "sendMessage",
            chat_id=chat_id,
            text="Here's the decision you were sent.",
            reply_markup=telegram.open_button("Open it", param.strip()),
        )
    elif command in ("/start", "/new", "/decide"):
        telegram.call(
            "sendMessage",
            chat_id=chat_id,
            text="Start a poll or a spin wheel, then send it to this chat.",
            reply_markup=telegram.open_button("Open Decision Maker"),
        )
    elif command == "/help":
        bot = current_app.config["APP"].bot_username
        telegram.call(
            "sendMessage",
            chat_id=chat_id,
            text=(
                "I help groups decide things together.\n\n"
                "/start - open Decision Maker\n"
                "/new - start a poll or spin wheel\n"
                "/decide - make a quick group decision\n"
                "/help - show this message\n\n"
                f"Tip: type @{bot} in any chat to share one of your polls."
            ),
            reply_markup=telegram.open_button("Open Decision Maker"),
        )


def _handle_inline_query(query: dict) -> None:
    """Typing @yourbot in any chat lists your recent polls to post there."""
    rows = get_db().execute(
        """SELECT id, question, mode FROM polls
           WHERE owner_id = ? AND question LIKE ? ESCAPE '\\'
           ORDER BY created_at DESC LIMIT 20""",
        (query["from"]["id"], "%" + _escape_like(query.get("query", "")) + "%"),
    ).fetchall()
    telegram.call(
        "answerInlineQuery",
        inline_query_id=query["id"],
        results=[telegram.inline_result(dict(row)) for row in rows],
        cache_time=5,
        is_personal=True,
    )


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@bp.post("/tg/webhook")
def webhook():
    cfg = current_app.config["APP"]
    supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not cfg.webhook_secret or not hmac.compare_digest(supplied, cfg.webhook_secret):
        return jsonify(error="forbidden"), 403

    update = request.get_json(silent=True) or {}
    try:
        if "message" in update:
            _handle_message(update["message"])
        elif "inline_query" in update:
            _handle_inline_query(update["inline_query"])
    except telegram.TelegramError as exc:
        # Answer 200 anyway, or Telegram keeps redelivering the same update.
        log.warning("bot reply failed: %s", exc)
    return jsonify(ok=True)
