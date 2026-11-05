import pytest

from app import telegram

from .conftest import make_poll

HEADERS = {"X-Telegram-Bot-Api-Secret-Token": "hook-secret"}


@pytest.fixture
def sent(monkeypatch):
    calls = []

    def fake_call(method, **payload):
        calls.append((method, payload))
        return {}

    monkeypatch.setattr(telegram, "call", fake_call)
    return calls


def post(app, update, headers=HEADERS):
    return app.test_client().post("/tg/webhook", json=update, headers=headers)


def test_webhook_rejects_a_wrong_secret(app, sent):
    assert post(app, {}, headers={"X-Telegram-Bot-Api-Secret-Token": "bad"}).status_code == 403
    assert sent == []


def test_webhook_is_closed_when_no_secret_is_set(app, sent):
    app.config["APP"].webhook_secret = ""
    assert post(app, {}, headers={"X-Telegram-Bot-Api-Secret-Token": ""}).status_code == 403


def test_start_with_deep_link_opens_that_poll(app, sent):
    post(app, {"message": {"text": "/start v_abc123", "chat": {"id": 5}}})
    button = sent[0][1]["reply_markup"]["inline_keyboard"][0][0]
    assert button["url"] == "https://t.me/decide_bot/decide?startapp=v_abc123"


def test_group_command_with_bot_suffix_gets_a_url_button(app, sent):
    post(app, {"message": {"text": "/new@decide_bot", "chat": {"id": -100}}})
    assert sent[0][1]["reply_markup"]["inline_keyboard"][0][0]["url"] == "https://t.me/decide_bot/decide"


def test_plain_chat_messages_are_ignored(app, sent):
    post(app, {"message": {"text": "hello", "chat": {"id": -100}}})
    assert sent == []


def test_inline_query_lists_only_your_polls(app, dara, sok, sent):
    mine = make_poll(dara)
    make_poll(sok)
    post(app, {"inline_query": {"id": "q", "from": {"id": 1}, "query": "lunch"}})
    method, payload = sent[0]
    assert method == "answerInlineQuery"
    assert [r["id"] for r in payload["results"]] == [mine["id"]]


def test_inline_query_treats_percent_literally(app, dara, sent):
    make_poll(dara)
    post(app, {"inline_query": {"id": "q", "from": {"id": 1}, "query": "%"}})
    assert sent[0][1]["results"] == []


def test_telegram_failure_still_returns_200(app, monkeypatch):
    def failing_call(method, **payload):
        raise telegram.TelegramError("down")

    monkeypatch.setattr(telegram, "call", failing_call)
    assert post(app, {"message": {"text": "/start", "chat": {"id": 5}}}).status_code == 200
