import json
import time

import pytest

from app.auth import InvalidInitData, validate_init_data

from .conftest import BOT_TOKEN, init_data_for, sign_init_data


def check(raw, token=BOT_TOKEN, max_age=3600):
    return validate_init_data(raw, token, max_age)


def test_valid_data_returns_the_user():
    user = check(init_data_for(42, "Dara", chat_instance="-99", chat_type="group"))
    assert (user.id, user.name) == (42, "Dara")
    assert (user.chat_instance, user.chat_type) == ("-99", "group")


def test_signature_field_stays_in_the_check():
    assert check(init_data_for(42, signature="abc123")).id == 42


def test_unicode_names_survive():
    assert check(init_data_for(7, "សុខា")).name == "សុខា"


def test_tampered_user_is_rejected():
    raw = init_data_for(42).replace("%22id%22%3A+42", "%22id%22%3A+1")
    assert "%22id%22%3A+1" in raw
    with pytest.raises(InvalidInitData):
        check(raw)


def test_wrong_bot_token_is_rejected():
    with pytest.raises(InvalidInitData):
        check(init_data_for(), token="999:other")


def test_expired_login_is_rejected():
    with pytest.raises(InvalidInitData):
        check(init_data_for(age=7200))


def test_missing_hash_is_rejected():
    with pytest.raises(InvalidInitData):
        check("auth_date=1&user=%7B%7D")


def test_duplicate_fields_are_rejected():
    with pytest.raises(InvalidInitData):
        check(init_data_for() + "&auth_date=1")


def test_missing_user_is_rejected():
    with pytest.raises(InvalidInitData):
        check(sign_init_data({"auth_date": str(int(time.time()))}))


def test_empty_token_never_validates():
    with pytest.raises(InvalidInitData):
        check(init_data_for(), token="")


def test_api_rejects_anonymous_and_dev_headers_outside_dev_mode(app):
    client = app.test_client()
    assert client.get("/api/recent").status_code == 401
    assert client.get("/api/recent", headers={"X-Dev-User": "Dara"}).status_code == 401
    assert client.get("/api/recent", headers={"Authorization": "tma bad"}).status_code == 401
