from app.voting import count_simple, instant_runoff

A, B, C, D = 1, 2, 3, 4


def test_single_choice_winner():
    counts, leaders = count_simple([A, B], [[A], [A], [B]])
    assert counts == {A: 2, B: 1}
    assert leaders == [A]


def test_simple_tie_lists_all_leaders():
    assert count_simple([A, B, C], [[A], [B]])[1] == [A, B]


def test_no_votes_means_no_leader():
    assert count_simple([A, B], [])[1] == []


def test_approval_counts_each_yes():
    counts, leaders = count_simple([A, B, C], [[A, B], [B], [], [B, C]])
    assert counts == {A: 1, B: 3, C: 1}
    assert leaders == [B]


def test_runoff_majority_in_first_round():
    rounds, winners = instant_runoff([A, B], [[A], [A], [B]])
    assert winners == [A]
    assert len(rounds) == 1


def test_runoff_transfer_changes_the_winner():
    # A leads on first choices, but C's voters all prefer B.
    ballots = [[A]] * 4 + [[B, A]] * 3 + [[C, B]] * 2
    rounds, winners = instant_runoff([A, B, C], ballots)
    assert winners == [B]
    assert rounds[0]["eliminated"] == [C]
    assert rounds[1]["counts"] == {A: 4, B: 5}


def test_runoff_exhausted_ballots_shrink_the_majority():
    ballots = [[A], [A], [B], [B], [C]]
    rounds, winners = instant_runoff([A, B, C], ballots)
    assert rounds[1]["exhausted"] == 1
    assert winners == [A, B]


def test_runoff_true_tie():
    _, winners = instant_runoff([A, B], [[A, B], [B, A]])
    assert sorted(winners) == [A, B]


def test_runoff_last_place_tie_uses_ranking_score():
    # B and C tie on first choices, but C appears higher overall.
    ballots = [[A, C], [A, C], [D, C], [D, C], [B, A], [C, A]]
    rounds, _ = instant_runoff([A, B, C, D], ballots)
    assert rounds[0]["eliminated"] == [B]
    assert rounds[0]["tiebreak"] is True


def test_runoff_three_way_cycle_is_a_tie():
    ballots = [[A, B, C], [B, C, A], [C, A, B]]
    assert sorted(instant_runoff([A, B, C], ballots)[1]) == [A, B, C]


def test_runoff_ignores_options_nobody_ranked():
    rounds, winners = instant_runoff([A, B, C], [[A], [A], [B]])
    assert winners == [A]
    assert C not in rounds[0]["counts"]


def test_runoff_always_terminates_with_partial_ballots():
    rounds, winners = instant_runoff([A, B, C, D], [[A, B], [C], [D, A], [B]])
    assert winners
    assert len(rounds) <= 4


def test_runoff_no_ballots():
    rounds, winners = instant_runoff([A, B], [])
    assert winners == []
    assert len(rounds) == 1
