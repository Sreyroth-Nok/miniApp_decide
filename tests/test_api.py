import app.api as api_module
import pytest

from app import telegram

from .conftest import Person, make_poll


def option_ids(poll):
    return [o["id"] for o in poll["options"]]


@pytest.fixture
def no_spin_lock(monkeypatch):
    monkeypatch.setattr(api_module, "SPIN_LOCK_SECONDS", 0)


def test_create_cleans_and_dedupes_options(dara):
    poll = make_poll(dara, options=["  Pizza ", "pizza", "", "Rice"])
    assert [o["label"] for o in poll["options"]] == ["Pizza", "Rice"]


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "", "mode": "single", "options": ["a", "b"]},
        {"question": "Q", "mode": "nope", "options": ["a", "b"]},
        {"question": "Q", "mode": "single", "options": ["a"]},
        {"question": "Q", "mode": "single", "options": ["a", "A"]},
        {"question": "Q", "mode": "single", "options": [str(i) for i in range(13)]},
        {"question": "Q", "mode": "single", "options": [1, 2]},
        {"question": "Q" * 141, "mode": "single", "options": ["a", "b"]},
        {"question": "Q", "mode": "single", "options": ["a", "b"], "close_after_minutes": 7},
    ],
)
def test_create_rejects_bad_input(dara, payload):
    assert dara.post("/api/polls", payload).status_code == 400


def test_deep_links_use_startapp(dara):
    poll = make_poll(dara)
    assert poll["links"]["vote"] == f"https://t.me/decide_bot/decide?startapp=v_{poll['id']}"
    assert poll["links"]["results"].endswith(f"startapp=r_{poll['id']}")
    assert poll["links"]["spin"].endswith(f"startapp=s_{poll['id']}")


def test_results_stay_hidden_until_you_vote(dara, sok):
    poll = make_poll(dara)
    url = f"/api/polls/{poll['id']}"
    assert sok.get(url).get_json()["results"] is None
    sok.post(f"{url}/vote", {"choices": [option_ids(poll)[0]]})
    assert sok.get(url).get_json()["results"]["tally"][0]["count"] == 1


def test_changing_a_vote_replaces_it(dara, sok):
    poll = make_poll(dara)
    a, b, _ = option_ids(poll)
    url = f"/api/polls/{poll['id']}"
    sok.post(f"{url}/vote", {"choices": [a]})
    data = sok.post(f"{url}/vote", {"choices": [b]}).get_json()
    assert data["voter_count"] == 1
    assert data["my_ballot"] == [b]


@pytest.mark.parametrize("choices", [[], [999], "x", [True], None])
def test_single_vote_rejects_bad_ballots(dara, choices):
    poll = make_poll(dara)
    assert dara.post(f"/api/polls/{poll['id']}/vote", {"choices": choices}).status_code == 400


def test_ranked_rejects_duplicates(dara):
    poll = make_poll(dara, "ranked")
    a = option_ids(poll)[0]
    assert dara.post(f"/api/polls/{poll['id']}/vote", {"choices": [a, a]}).status_code == 400


def test_ranked_results_include_rounds(dara, sok, lina):
    poll = make_poll(dara, "ranked", options=("A", "B", "C", "D"))
    a, b, c, _ = option_ids(poll)
    url = f"/api/polls/{poll['id']}/vote"
    dara.post(url, {"choices": [a, b]})
    sok.post(url, {"choices": [b, a]})
    result = lina.post(url, {"choices": [c, b]}).get_json()["results"]
    assert result["winners"] == [b]
    assert result["rounds"][1]["counts"]
    assert result["tally"][0]["label"] == "B"


def test_swipe_allows_all_no(dara):
    poll = make_poll(dara, "swipe")
    assert dara.post(f"/api/polls/{poll['id']}/vote", {"choices": []}).status_code == 200


def test_anonymous_polls_hide_names(dara, sok):
    poll = make_poll(dara, anonymous=True)
    a = option_ids(poll)[0]
    data = sok.post(f"/api/polls/{poll['id']}/vote", {"choices": [a]}).get_json()
    assert data["voters"] == []
    assert data["voter_count"] == 1


def test_add_option_needs_permission(dara, sok):
    closed_list = make_poll(dara)
    assert sok.post(f"/api/polls/{closed_list['id']}/options", {"label": "Soup"}).status_code == 403
    open_list = make_poll(dara, allow_add=True)
    url = f"/api/polls/{open_list['id']}/options"
    assert sok.post(url, {"label": "Soup"}).status_code == 201
    assert sok.post(url, {"label": "soup"}).status_code == 400


def test_closed_poll_rejects_votes_and_picks_a_winner(dara, sok):
    poll = make_poll(dara)
    a = option_ids(poll)[0]
    url = f"/api/polls/{poll['id']}"
    sok.post(f"{url}/vote", {"choices": [a]})
    assert sok.post(f"{url}/close").status_code == 403
    closed = dara.post(f"{url}/close").get_json()
    assert closed["decision"]["label"] == "Pizza"
    assert closed["decision"]["source"] == "vote"
    assert sok.post(f"{url}/vote", {"choices": [a]}).status_code == 409


def test_deadline_closes_a_poll(dara, monkeypatch):
    poll = make_poll(dara, close_after_minutes=60)
    url = f"/api/polls/{poll['id']}"
    real_time = api_module.time.time
    monkeypatch.setattr(api_module.time, "time", lambda: real_time() + 3601)
    assert dara.get(url).get_json()["closed"] is True


def test_spin_lands_on_a_slice_and_everyone_sees_it(dara, sok):
    poll = make_poll(dara, "spin")
    url = f"/api/polls/{poll['id']}"
    spin = dara.post(f"{url}/spin").get_json()
    assert spin["landed_id"] in option_ids(poll)
    assert {s["id"] for s in spin["slices"]} == set(option_ids(poll))
    seen = sok.get(url).get_json()["last_spin"]
    assert (seen["id"], seen["jitter"]) == (spin["id"], spin["jitter"])


def test_double_tap_cannot_reroll(dara, sok):
    poll = make_poll(dara, "spin")
    url = f"/api/polls/{poll['id']}/spin"
    first = dara.post(url)
    second = sok.post(url)
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.get_json()["reused"] is True
    assert second.get_json()["id"] == first.get_json()["id"]


def test_spin_is_roughly_fair(dara, no_spin_lock):
    poll = make_poll(dara, "spin")
    url = f"/api/polls/{poll['id']}/spin"
    landed = [dara.post(url).get_json()["landed_id"] for _ in range(300)]
    for option in option_ids(poll):
        assert 60 < landed.count(option) < 145


def test_weighted_spin_follows_votes(dara, sok, lina, no_spin_lock):
    poll = make_poll(dara)
    a, b, c = option_ids(poll)
    url = f"/api/polls/{poll['id']}"
    dara.post(f"{url}/vote", {"choices": [a]})
    sok.post(f"{url}/vote", {"choices": [a]})
    lina.post(f"{url}/vote", {"choices": [b]})
    spin = dara.post(f"{url}/spin", {"weighted": True}).get_json()
    assert {s["id"]: s["weight"] for s in spin["slices"]} == {a: 2, b: 1}
    assert c not in {s["id"] for s in spin["slices"]}
    landed = [dara.post(f"{url}/spin", {"weighted": True}).get_json()["landed_id"] for _ in range(240)]
    assert landed.count(a) > landed.count(b) * 1.3


def test_tiebreak_only_uses_tied_options(dara, sok):
    poll = make_poll(dara)
    a, b, _ = option_ids(poll)
    url = f"/api/polls/{poll['id']}"
    dara.post(f"{url}/vote", {"choices": [a]})
    sok.post(f"{url}/vote", {"choices": [b]})
    spin = dara.post(f"{url}/spin", {"scope": "tied"}).get_json()
    assert {s["id"] for s in spin["slices"]} == {a, b}


def test_tiebreak_needs_a_tie(dara):
    poll = make_poll(dara)
    url = f"/api/polls/{poll['id']}"
    dara.post(f"{url}/vote", {"choices": [option_ids(poll)[0]]})
    assert dara.post(f"{url}/spin", {"scope": "tied"}).status_code == 409


def test_wheel_does_not_leak_results_to_non_voters(dara, sok):
    poll = make_poll(dara)
    a = option_ids(poll)[0]
    url = f"/api/polls/{poll['id']}"
    dara.post(f"{url}/vote", {"choices": [a]})
    assert sok.post(f"{url}/spin", {"weighted": True}).status_code == 403
    assert sok.post(f"{url}/spin").status_code == 403
    assert dara.post(f"{url}/spin", {"weighted": False}).status_code == 201
    hidden = sok.get(url).get_json()
    assert hidden["last_spin"] is None and hidden["spin_history"] == []


def test_a_closed_poll_with_a_winner_cannot_be_spun(dara):
    poll = make_poll(dara)
    url = f"/api/polls/{poll['id']}"
    dara.post(f"{url}/vote", {"choices": [option_ids(poll)[0]]})
    dara.post(f"{url}/close")
    assert dara.post(f"{url}/spin").status_code == 409


def test_a_closed_tie_can_still_be_spun(dara, sok):
    poll = make_poll(dara)
    a, b, _ = option_ids(poll)
    url = f"/api/polls/{poll['id']}"
    dara.post(f"{url}/vote", {"choices": [a]})
    sok.post(f"{url}/vote", {"choices": [b]})
    dara.post(f"{url}/close")
    assert dara.post(f"{url}/spin", {"scope": "tied"}).status_code == 201


def test_elimination_excludes_removed_options(dara, no_spin_lock):
    poll = make_poll(dara, "spin")
    a, b, c = option_ids(poll)
    url = f"/api/polls/{poll['id']}/spin"
    spin = dara.post(url, {"exclude": [a]}).get_json()
    assert {s["id"] for s in spin["slices"]} == {b, c}
    assert dara.post(url, {"exclude": [a, b]}).status_code == 400


def test_decide_from_spin_then_no_more_spins(dara, sok, no_spin_lock):
    poll = make_poll(dara, "spin")
    url = f"/api/polls/{poll['id']}"
    landed = dara.post(f"{url}/spin").get_json()["landed_id"]
    assert sok.post(f"{url}/decide", {"option_id": landed}).status_code == 403
    decided = dara.post(f"{url}/decide", {"option_id": landed}).get_json()
    assert decided["decision"]["source"] == "spin"
    assert decided["closed"] is True
    assert dara.post(f"{url}/spin").status_code == 409
    reopened = dara.post(f"{url}/reopen").get_json()
    assert reopened["decision"] is None and reopened["closed"] is False


def test_unknown_poll_is_404(dara):
    assert dara.get("/api/polls/missing").status_code == 404


def test_group_chat_sees_its_own_decisions(app, dara):
    poll = make_poll(dara)
    sok = Person(app, 2, "Sok", chat_instance="group-1", chat_type="group")
    other = Person(app, 3, "Lina", chat_instance="group-2", chat_type="group")
    sok.get(f"/api/polls/{poll['id']}")
    assert [p["id"] for p in sok.get("/api/recent").get_json()["chat"]] == [poll["id"]]
    assert other.get("/api/recent").get_json()["chat"] == []


def test_private_chat_instance_is_not_recorded(app, dara):
    poll = make_poll(dara)
    sok = Person(app, 2, "Sok", chat_instance="private-1", chat_type="sender")
    sok.get(f"/api/polls/{poll['id']}")
    assert sok.get("/api/recent").get_json()["chat"] == []


def test_prepared_message_success_and_fallback(dara, monkeypatch):
    poll = make_poll(dara)
    url = f"/api/polls/{poll['id']}/prepared-message"
    calls = []

    def fake_call(method, **payload):
        calls.append((method, payload))
        return {"id": "prepared-1", "expiration_date": 0}

    monkeypatch.setattr(telegram, "call", fake_call)
    assert dara.post(url).get_json() == {"id": "prepared-1"}
    method, payload = calls[0]
    assert method == "savePreparedInlineMessage"
    button = payload["result"]["reply_markup"]["inline_keyboard"][0][0]
    assert button["url"].endswith(f"startapp=v_{poll['id']}")

    def failing_call(method, **payload):
        raise telegram.TelegramError("no")

    monkeypatch.setattr(telegram, "call", failing_call)
    assert dara.post(url).status_code == 503
