"""Vote counting. Pure functions with no database or Flask, so they are easy to test.

A ballot is a list of option ids:
  single  [chosen]
  swipe   every option the voter said yes to (may be empty)
  ranked  options in order of preference (may be partial)
"""
from collections import Counter


def count_simple(option_ids: list[int], ballots: list[list[int]]) -> tuple[dict[int, int], list[int]]:
    """Single choice and swipe: each mention is one vote. Returns (counts, leaders)."""
    counts = Counter({option: 0 for option in option_ids})
    for ballot in ballots:
        counts.update(c for c in set(ballot) if c in counts)
    top = max(counts.values(), default=0)
    leaders = [o for o in option_ids if counts[o] == top] if top else []
    return dict(counts), leaders


def _ranking_scores(remaining: list[int], ballots: list[list[int]]) -> dict[int, int]:
    """Borda score: higher positions on every ballot earn more points."""
    scores = {o: 0 for o in remaining}
    for ballot in ballots:
        kept = [c for c in ballot if c in scores]
        for position, option in enumerate(kept):
            scores[option] += len(remaining) - position
    return scores


def instant_runoff(option_ids: list[int], ballots: list[list[int]]) -> tuple[list[dict], list[int]]:
    """Ranked choice. Returns (rounds, winners); more than one winner means a tie.

    Each round gives every ballot to its highest-ranked option still in the race.
    An option with over half the active ballots wins. Otherwise the last-place
    option is eliminated and its ballots move to their next choice.

    A tie for last place is settled by overall ranking score, one elimination at
    a time. If that is also level, all of those options go together, unless they
    are everything left, which is a real tie.
    """
    ranked_by_someone = {c for ballot in ballots for c in ballot}
    remaining = [o for o in option_ids if o in ranked_by_someone]
    rounds: list[dict] = []

    while True:
        counts = {o: 0 for o in remaining}
        for ballot in ballots:
            first = next((c for c in ballot if c in counts), None)
            if first is not None:
                counts[first] += 1

        active = sum(counts.values())
        current = {
            "counts": counts,
            "eliminated": [],
            "exhausted": len(ballots) - active,
            "tiebreak": False,
        }
        rounds.append(current)
        if active == 0:
            return rounds, []

        leader = max(remaining, key=lambda o: counts[o])
        if counts[leader] * 2 > active:
            return rounds, [leader]

        low = min(counts.values())
        last_place = [o for o in remaining if counts[o] == low]
        if len(last_place) == len(remaining):
            scores = _ranking_scores(remaining, ballots)
            lowest_score = min(scores.values())
            out = [o for o in remaining if scores[o] == lowest_score]
            if len(out) == len(remaining):
                return rounds, remaining
            current["tiebreak"] = True
        elif len(last_place) > 1:
            scores = _ranking_scores(remaining, ballots)
            lowest_score = min(scores[o] for o in last_place)
            out = [o for o in last_place if scores[o] == lowest_score]
            current["tiebreak"] = True
        else:
            out = last_place

        current["eliminated"] = out
        remaining = [o for o in remaining if o not in out]
