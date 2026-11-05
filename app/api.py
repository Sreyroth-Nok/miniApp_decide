"""JSON API used by the Mini App."""
import json
import secrets
import string
import time

from flask import Blueprint, current_app, g, jsonify, request

from . import telegram, voting
from .auth import require_user
from .db import get_db

bp = Blueprint("api", __name__, url_prefix="/api")

MODES = ("single", "ranked", "swipe", "spin")
MAX_QUESTION = 140
MAX_LABEL = 40
MIN_OPTIONS = 2
MAX_OPTIONS = 12
CLOSE_AFTER_CHOICES = {0, 60, 24 * 60}  # minutes; 0 means stay open

# How long the wheel animates. A second spin inside this window returns the
# running spin, so a double tap or two people tapping together can't re-roll it.
SPIN_LOCK_SECONDS = 6
ALPHABET = string.ascii_letters + string.digits


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        self.message = message
        self.status = status


@bp.app_errorhandler(ApiError)
def handle_api_error(err: ApiError):
    return jsonify(error=err.message), err.status


# ---------- helpers ----------


def body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Send a JSON object.")
    return data


def clean_text(value, limit: int, what: str) -> str:
    if not isinstance(value, str):
        raise ApiError(f"{what} is required.")
    text = " ".join(value.split())
    if not text:
        raise ApiError(f"{what} is required.")
    if len(text) > limit:
        raise ApiError(f"{what} can be {limit} characters at most.")
    return text


def load_poll(poll_id: str):
    row = get_db().execute("SELECT * FROM polls WHERE id = ?", (poll_id,)).fetchone()
    if row is None:
        raise ApiError("This decision doesn't exist. The link may be wrong.", 404)
    return row


def load_options(poll_id: str) -> list[dict]:
    rows = get_db().execute(
        "SELECT id, label, added_by FROM options WHERE poll_id = ? ORDER BY id", (poll_id,)
    )
    return [dict(row) for row in rows]


def load_ballots(poll_id: str) -> list[dict]:
    rows = get_db().execute(
        "SELECT user_id, user_name, choices FROM ballots WHERE poll_id = ? ORDER BY updated_at",
        (poll_id,),
    )
    return [{**dict(row), "choices": json.loads(row["choices"])} for row in rows]


def is_closed(poll) -> bool:
    if poll["closed_at"]:
        return True
    return bool(poll["closes_at"]) and time.time() >= poll["closes_at"]


def require_owner(poll) -> None:
    if poll["owner_id"] != g.user.id:
        raise ApiError("Only the person who created this can do that.", 403)


def remember_chat(poll_id: str) -> None:
    """chat_instance arrives on direct links, so a group can see its own decisions."""
    if g.user.chat_instance and g.user.chat_type in ("group", "supergroup"):
        db = get_db()
        db.execute(
            "INSERT OR IGNORE INTO poll_chats (poll_id, chat_instance) VALUES (?, ?)",
            (poll_id, g.user.chat_instance),
        )
        db.commit()


def can_see_results(poll, ballots: list[dict]) -> bool:
    """Votes stay hidden until you've voted, so early results don't sway anyone."""
    return (
        poll["owner_id"] == g.user.id
        or is_closed(poll)
        or any(b["user_id"] == g.user.id for b in ballots)
    )


def compute_results(poll, options: list[dict], ballots: list[dict]) -> dict:
    ids = [o["id"] for o in options]
    labels = {o["id"]: o["label"] for o in options}
    papers = [b["choices"] for b in ballots]
    rounds_out = None

    if poll["mode"] == "ranked":
        rounds, winners = voting.instant_runoff(ids, papers)
        counts = {o: 0 for o in ids}
        counts.update(rounds[-1]["counts"])
        first_round = {o: 0 for o in ids}
        first_round.update(rounds[0]["counts"])
        rounds_out = [
            {
                "counts": [{"id": o, "label": labels[o], "count": n} for o, n in r["counts"].items()],
                "eliminated": [{"id": o, "label": labels[o]} for o in r["eliminated"]],
                "exhausted": r["exhausted"],
                "tiebreak": r["tiebreak"],
            }
            for r in rounds
        ]
        weights = first_round
    else:
        counts, winners = voting.count_simple(ids, papers)
        weights = counts

    tally = sorted(
        ({"id": o, "label": labels[o], "count": counts[o]} for o in ids),
        key=lambda item: (item["id"] not in winners, -item["count"]),
    )
    return {
        "tally": tally,
        "winners": winners,
        "tied": len(winners) > 1,
        "rounds": rounds_out,
        "spin_weights": weights,
    }


def latest_spin(poll_id: str) -> dict | None:
    row = get_db().execute(
        "SELECT * FROM spins WHERE poll_id = ? ORDER BY id DESC LIMIT 1", (poll_id,)
    ).fetchone()
    return spin_json(row) if row else None


def spin_json(row) -> dict:
    return {
        "id": row["id"],
        "slices": json.loads(row["slices"]),
        "landed_id": row["landed_id"],
        "jitter": row["jitter"],
        "by": row["by_name"],
        "age": max(0.0, time.time() - row["created_at"]),
    }


def poll_json(poll) -> dict:
    options = load_options(poll["id"])
    ballots = load_ballots(poll["id"])
    me = g.user.id
    my_ballot = next((b["choices"] for b in ballots if b["user_id"] == me), None)
    closed = is_closed(poll)
    is_owner = poll["owner_id"] == me
    is_wheel = poll["mode"] == "spin"
    visible = is_wheel or can_see_results(poll, ballots)
    results = compute_results(poll, options, ballots) if visible and not is_wheel else None
    decision = None
    if poll["decided_option_id"]:
        label = next(o["label"] for o in options if o["id"] == poll["decided_option_id"])
        decision = {"id": poll["decided_option_id"], "label": label, "source": poll["decided_source"]}
    elif closed and poll["mode"] != "spin":
        full = results or compute_results(poll, options, ballots)
        if len(full["winners"]) == 1:
            winner = full["winners"][0]
            label = next(o["label"] for o in options if o["id"] == winner)
            decision = {"id": winner, "label": label, "source": "vote"}

    # Slice sizes on a weighted wheel would reveal the votes, so spins are hidden too.
    spins = get_db().execute(
        "SELECT * FROM spins WHERE poll_id = ? ORDER BY id DESC LIMIT 6", (poll["id"],)
    ).fetchall() if visible else []

    return {
        "id": poll["id"],
        "question": poll["question"],
        "mode": poll["mode"],
        "allow_add": bool(poll["allow_add"]),
        "anonymous": bool(poll["anonymous"]),
        "owner_name": poll["owner_name"],
        "is_owner": is_owner,
        "closes_at": poll["closes_at"],
        "closed": closed,
        "options": [{"id": o["id"], "label": o["label"]} for o in options],
        "my_ballot": my_ballot,
        "voter_count": len(ballots),
        "voters": [] if poll["anonymous"] else [b["user_name"] for b in ballots],
        "results": results,
        "decision": decision,
        "last_spin": spin_json(spins[0]) if spins else None,
        "spin_history": [{"id": s["id"], "by": s["by_name"], "landed_id": s["landed_id"]} for s in spins],
        "links": {
            "vote": telegram.app_link(f"v_{poll['id']}"),
            "results": telegram.app_link(f"r_{poll['id']}"),
            "spin": telegram.app_link(f"s_{poll['id']}"),
        },
    }


# ---------- routes ----------


@bp.get("/config")
def config():
    cfg = current_app.config["APP"]
    return jsonify(dev_mode=cfg.dev_mode, app_link=telegram.app_link())


@bp.post("/polls")
@require_user
def create_poll():
    data = body()
    question = clean_text(data.get("question"), MAX_QUESTION, "A question")
    mode = data.get("mode")
    if mode not in MODES:
        raise ApiError("Choose how the group should decide.")

    raw_options = data.get("options")
    if not isinstance(raw_options, list):
        raise ApiError("Add at least two options.")
    labels: list[str] = []
    seen: set[str] = set()
    for raw in raw_options:
        if isinstance(raw, str) and not raw.strip():
            continue  # empty rows left in the form
        label = clean_text(raw, MAX_LABEL, "An option")
        if label.casefold() not in seen:
            seen.add(label.casefold())
            labels.append(label)
    if len(labels) < MIN_OPTIONS:
        raise ApiError("Add at least two different options.")
    if len(labels) > MAX_OPTIONS:
        raise ApiError(f"Use {MAX_OPTIONS} options at most.")

    close_after = data.get("close_after_minutes", 0)
    if close_after not in CLOSE_AFTER_CHOICES:
        raise ApiError("Choose a valid closing time.")

    now = int(time.time())
    poll_id = "".join(secrets.choice(ALPHABET) for _ in range(8))
    db = get_db()
    db.execute(
        """INSERT INTO polls (id, owner_id, owner_name, question, mode, allow_add,
                              anonymous, created_at, closes_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            poll_id, g.user.id, g.user.name, question, mode,
            int(bool(data.get("allow_add"))), int(bool(data.get("anonymous"))),
            now, now + close_after * 60 if close_after else None,
        ),
    )
    db.executemany(
        "INSERT INTO options (poll_id, label, added_by) VALUES (?, ?, ?)",
        [(poll_id, label, g.user.name) for label in labels],
    )
    db.commit()
    remember_chat(poll_id)
    return jsonify(poll_json(load_poll(poll_id))), 201


@bp.get("/polls/<poll_id>")
@require_user
def get_poll(poll_id):
    poll = load_poll(poll_id)
    remember_chat(poll_id)
    return jsonify(poll_json(poll))


@bp.post("/polls/<poll_id>/vote")
@require_user
def vote(poll_id):
    poll = load_poll(poll_id)
    if poll["mode"] == "spin":
        raise ApiError("This one is a wheel, so there's nothing to vote on.")
    if is_closed(poll):
        raise ApiError("Voting has closed.", 409)

    choices = body().get("choices")
    valid = {o["id"] for o in load_options(poll_id)}
    if (
        not isinstance(choices, list)
        or not all(type(c) is int and c in valid for c in choices)
        or len(set(choices)) != len(choices)
    ):
        raise ApiError("That vote contains an option that isn't in this poll.")
    if poll["mode"] == "single" and len(choices) != 1:
        raise ApiError("Pick one option.")
    if poll["mode"] == "ranked" and not choices:
        raise ApiError("Rank at least one option.")

    db = get_db()
    db.execute(
        """INSERT INTO ballots (poll_id, user_id, user_name, choices, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT (poll_id, user_id) DO UPDATE SET
             user_name = excluded.user_name,
             choices = excluded.choices,
             updated_at = excluded.updated_at""",
        (poll_id, g.user.id, g.user.name, json.dumps(choices), int(time.time())),
    )
    db.commit()
    return jsonify(poll_json(poll))


@bp.post("/polls/<poll_id>/options")
@require_user
def add_option(poll_id):
    poll = load_poll(poll_id)
    if not poll["allow_add"] and poll["owner_id"] != g.user.id:
        raise ApiError("The creator hasn't allowed new options.", 403)
    if is_closed(poll):
        raise ApiError("This decision has closed.", 409)

    label = clean_text(body().get("label"), MAX_LABEL, "An option")
    options = load_options(poll_id)
    if len(options) >= MAX_OPTIONS:
        raise ApiError(f"This already has the maximum of {MAX_OPTIONS} options.")
    if any(o["label"].casefold() == label.casefold() for o in options):
        raise ApiError("That option is already on the list.")

    db = get_db()
    db.execute(
        "INSERT INTO options (poll_id, label, added_by) VALUES (?, ?, ?)",
        (poll_id, label, g.user.name),
    )
    db.commit()
    return jsonify(poll_json(poll)), 201


@bp.post("/polls/<poll_id>/spin")
@require_user
def spin(poll_id):
    """The server picks the result, so everyone in the chat sees the same spin.

    scope     "all" or "tied" (only the options tied for first)
    weighted  slice sizes follow the vote counts
    exclude   options already removed in an elimination run
    """
    poll = load_poll(poll_id)
    if poll_json(poll)["decision"]:
        raise ApiError("This has already been decided.", 409)

    ballots = load_ballots(poll_id)
    if poll["mode"] != "spin" and not can_see_results(poll, ballots):
        raise ApiError("Vote first, then you can use the wheel.", 403)

    data = body()
    scope = data.get("scope", "all")
    weighted = bool(data.get("weighted"))
    exclude = data.get("exclude", [])
    if scope not in ("all", "tied") or not isinstance(exclude, list):
        raise ApiError("That spin request isn't valid.")

    db = get_db()
    last = db.execute(
        "SELECT * FROM spins WHERE poll_id = ? ORDER BY id DESC LIMIT 1", (poll_id,)
    ).fetchone()
    if last and time.time() - last["created_at"] < SPIN_LOCK_SECONDS:
        return jsonify(spin_json(last) | {"reused": True})

    options = load_options(poll_id)
    results = None
    if scope == "tied" or weighted:
        if poll["mode"] == "spin":
            raise ApiError("A plain wheel has no votes to use.")
        results = compute_results(poll, options, ballots)

    candidates = [o for o in options if o["id"] not in exclude]
    if scope == "tied":
        if not results["tied"]:
            raise ApiError("There's no tie to break.", 409)
        candidates = [o for o in candidates if o["id"] in results["winners"]]

    weights = {o["id"]: 1 for o in candidates}
    if weighted:
        weights = {
            o["id"]: results["spin_weights"].get(o["id"], 0)
            for o in candidates
            if results["spin_weights"].get(o["id"], 0) > 0
        }
        candidates = [o for o in candidates if o["id"] in weights]
    if len(candidates) < 2:
        raise ApiError("The wheel needs at least two options with a chance of winning.")

    slices = [{"id": o["id"], "label": o["label"], "weight": weights[o["id"]]} for o in candidates]
    ticket = secrets.randbelow(sum(weights.values()))
    landed = None
    for item in slices:
        ticket -= item["weight"]
        if ticket < 0:
            landed = item["id"]
            break

    jitter = secrets.randbelow(1000) / 1000  # where in the slice the pointer stops
    cursor = db.execute(
        """INSERT INTO spins (poll_id, slices, landed_id, jitter, by_name, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (poll_id, json.dumps(slices, ensure_ascii=False), landed, jitter, g.user.name, time.time()),
    )
    db.commit()
    row = db.execute("SELECT * FROM spins WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return jsonify(spin_json(row) | {"reused": False}), 201


@bp.post("/polls/<poll_id>/close")
@require_user
def close_poll(poll_id):
    poll = load_poll(poll_id)
    require_owner(poll)
    db = get_db()
    db.execute(
        "UPDATE polls SET closed_at = COALESCE(closed_at, ?) WHERE id = ?",
        (int(time.time()), poll_id),
    )
    db.commit()
    return jsonify(poll_json(load_poll(poll_id)))


@bp.post("/polls/<poll_id>/decide")
@require_user
def decide(poll_id):
    """The creator locks in a final answer, from a vote or a spin."""
    poll = load_poll(poll_id)
    require_owner(poll)
    option_id = body().get("option_id")
    if option_id not in {o["id"] for o in load_options(poll_id)}:
        raise ApiError("That option isn't in this poll.")

    last = latest_spin(poll_id)
    source = "spin" if last and last["landed_id"] == option_id else "vote"
    db = get_db()
    db.execute(
        """UPDATE polls SET decided_option_id = ?, decided_source = ?,
                            closed_at = COALESCE(closed_at, ?) WHERE id = ?""",
        (option_id, source, int(time.time()), poll_id),
    )
    db.commit()
    return jsonify(poll_json(load_poll(poll_id)))


@bp.post("/polls/<poll_id>/reopen")
@require_user
def reopen(poll_id):
    poll = load_poll(poll_id)
    require_owner(poll)
    db = get_db()
    db.execute(
        """UPDATE polls SET closed_at = NULL, closes_at = NULL,
                            decided_option_id = NULL, decided_source = NULL WHERE id = ?""",
        (poll_id,),
    )
    db.commit()
    return jsonify(poll_json(load_poll(poll_id)))


@bp.post("/polls/<poll_id>/prepared-message")
@require_user
def prepared_message(poll_id):
    """Prepares a rich message for Telegram.WebApp.shareMessage (Bot API 8.0+).

    The front end falls back to a plain t.me/share link if this fails.
    """
    poll = load_poll(poll_id)
    try:
        prepared = telegram.call(
            "savePreparedInlineMessage",
            user_id=g.user.id,
            result=telegram.inline_result(dict(poll)),
            allow_user_chats=True,
            allow_group_chats=True,
        )
    except telegram.TelegramError:
        raise ApiError("Rich sharing isn't available right now.", 503)
    return jsonify(id=prepared["id"])


def status_line(poll) -> str:
    """A few words for the home list, such as "Tied" or "Pizza leads".

    It never shows who is ahead to someone who isn't allowed to see results yet.
    """
    options = load_options(poll["id"])
    labels = {o["id"]: o["label"] for o in options}
    if poll["decided_option_id"]:
        return f"Decided: {labels.get(poll['decided_option_id'], '')}"
    if poll["mode"] == "spin":
        return "Closed" if is_closed(poll) else "Ready to spin"

    ballots = load_ballots(poll["id"])
    if not ballots:
        return "Closed" if is_closed(poll) else "No votes yet"
    if not can_see_results(poll, ballots):
        count = len(ballots)
        return f"{count} vote{'' if count == 1 else 's'} · vote to see"

    winners = compute_results(poll, options, ballots)["winners"]
    if len(winners) != 1:
        return "Closed · Tied" if is_closed(poll) else "Tied"
    label = labels[winners[0]]
    return f"Won: {label}" if is_closed(poll) else f"{label} leads"


@bp.get("/recent")
@require_user
def recent():
    """Your own decisions, plus the ones opened from the current group chat."""
    db = get_db()
    summary = "p.*"
    mine = db.execute(
        f"SELECT {summary} FROM polls p WHERE p.owner_id = ? ORDER BY p.created_at DESC LIMIT 8",
        (g.user.id,),
    ).fetchall()
    in_chat = []
    if g.user.chat_instance:
        in_chat = db.execute(
            f"""SELECT {summary} FROM polls p
                JOIN poll_chats c ON c.poll_id = p.id
                WHERE c.chat_instance = ? ORDER BY p.created_at DESC LIMIT 8""",
            (g.user.chat_instance,),
        ).fetchall()

    def item(row):
        return {
            "id": row["id"],
            "question": row["question"],
            "mode": row["mode"],
            "closed": is_closed(row),
            "status": status_line(row),
        }

    return jsonify(mine=[item(r) for r in mine], chat=[item(r) for r in in_chat])
