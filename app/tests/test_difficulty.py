from backend.domain.difficulty import (
    CONTROLLER_V1, CONTROLLER_V2, DEFAULT_CONFIG, ControllerState, Difficulty, DifficultyConfig, initial_difficulty,
    market_level, next_step, rank,
)

V1 = DifficultyConfig(version=CONTROLLER_V1)

B, M, A = Difficulty.BASIC, Difficulty.INTERMEDIATE, Difficulty.ADVANCED


def step(level, scores, *, targeted=None, shown=1, topic_score=0.5, sufficient=True, open_=("c3",), goal=False,
         cfg=DEFAULT_CONFIG):
    return next_step(ControllerState(level, shown, ()), cfg, targeted=targeted if targeted is not None else list(scores),
                     scores=scores, topic_score=topic_score, sufficient=sufficient, open_criteria=list(open_),
                     goal_open=goal)


def test_initial():
    assert initial_difficulty("junior", None) == (B, "LEVEL:junior")
    assert initial_difficulty("senior", None)[0] == A
    assert initial_difficulty(None, "middle") == (M, "MARKET:middle")
    assert initial_difficulty(None, None) == (M, "DEFAULT")
    assert initial_difficulty("junior", "senior")[0] == B


def test_market_level():
    assert market_level([1, 2, 6]) == "middle"
    assert market_level([None, None]) is None
    assert market_level([0, 1]) == "junior"
    assert market_level([5, None, 7]) == "senior"


def test_rank():
    assert [rank(d) for d in (B, M, A)] == [0, 1, 2]


def test_junior_strong_steps_up_one_at_a_time():
    s = {"c1": 0.9, "c2": 0.8}
    d1 = step(B, s)
    assert d1.next_level == M and d1.reason == "STRONG" and d1.action == "CONTINUE"
    assert step(M, s).next_level == A
    assert step(A, s).next_level == A


def test_senior_weak_steps_down_to_floor():
    s = {"c1": 0.2}
    d = step(A, s)
    assert d.next_level == M and d.reason == "WEAK"
    assert step(M, s).next_level == B
    assert step(B, s).next_level == B


def test_v1_incomplete_weak_answer_does_not_lower():
    d = step(M, {"c1": 0.1, "c2": None}, cfg=V1)
    assert d.next_level == M and d.reason == "PARTIAL" and d.action == "FOLLOWUP"


def test_v2_weak_graded_focus_lowers_even_if_another_focus_criterion_is_null():
    d = step(M, {"c1": 0.1, "c2": None})
    assert (d.next_level, d.reason, d.action) == (B, "WEAK", "CONTINUE")
    assert step(M, {"c1": 0.1, "c2": None, "c3": None}, targeted=["c2", "c3", "c1"]).reason == "NO_EVIDENCE"


def test_all_null_no_change():
    d = step(A, {"c1": None})
    assert d.next_level == A and d.reason == "NO_EVIDENCE" and d.action == "FOLLOWUP"
    assert d.target_criteria == ("c3",)
    d = step(A, {}, targeted=["c1", "c2"])
    assert d.reason == "NO_EVIDENCE"
    assert step(A, {}, targeted=[]).reason == "NO_EVIDENCE"


def test_v1_strong_but_not_sufficient_no_raise():
    d = step(B, {"c1": 0.9}, sufficient=False, cfg=V1)
    assert d.next_level == B and d.reason == "PARTIAL"


def test_v2_strong_focus_raises_without_whole_topic_sufficiency():
    """D-3: Python forces sufficient=false while any topic criterion is null, so v1 could never step up there."""
    assert DEFAULT_CONFIG.version == CONTROLLER_V2 and DEFAULT_CONFIG.focus == 2
    many = ["c1", "c2", "c3", "c4", "c5"]  # targeted = every open criterion; one narrow question covered the first
    d = step(B, {"c1": 0.9}, targeted=many, sufficient=False)
    assert (d.next_level, d.reason) == (M, "STRONG")
    assert step(M, {"c1": 0.9}, targeted=many, sufficient=False).next_level == A
    assert step(B, {"c1": 0.9}, targeted=many, sufficient=False, cfg=V1).reason == "PARTIAL"
    # the third criterion is outside the focus: graded there, it does not count
    assert step(B, {"c3": 0.9}, targeted=many, sufficient=False).reason == "NO_EVIDENCE"
    assert step(B, {"c1": 0.7}, targeted=many, sufficient=False).reason == "PARTIAL"  # mean below up_score


def test_level_open_keeps_topic_open_like_a_goal():
    assert step(B, {"c1": 0.9}, shown=2, topic_score=0.8).action == "CLOSE"
    d = next_step(ControllerState(B, 2, ()), DEFAULT_CONFIG, targeted=["c1"], scores={"c1": 0.9}, topic_score=0.8,
                  sufficient=True, open_criteria=["c3"], level_open=True)
    assert (d.action, d.next_level) == ("CONTINUE", M)
    capped = next_step(ControllerState(B, 5, ()), DEFAULT_CONFIG, targeted=["c1"], scores={"c1": 0.9}, topic_score=0.8,
                       sufficient=True, open_criteria=["c3"], level_open=True)
    assert capped.action == "CLOSE" and capped.reason == "QUESTION_CAP"


def test_close_when_no_open_criteria():
    d = step(M, {"c1": 0.9}, open_=())
    assert d.action == "CLOSE" and d.reason == "NO_OPEN_CRITERIA" and d.next_level == M


def test_close_at_question_cap():
    d = step(M, {"c1": 0.1}, shown=5)
    assert d.action == "CLOSE" and d.reason == "QUESTION_CAP" and d.next_level == M


def test_close_when_min_two_met_and_no_goal():
    d = step(B, {"c1": 0.9}, shown=2, topic_score=0.8)
    assert d.action == "CLOSE" and d.reason == "STRONG+ENOUGH" and d.next_level == M


def test_continue_when_goal_open():
    d = step(B, {"c1": 0.9}, shown=2, topic_score=0.8, goal=True)
    assert d.action == "CONTINUE"


def test_no_close_when_min_followup_owed_or_null_topic():
    assert step(M, {"c1": 0.6}, shown=1, topic_score=0.6).action == "FOLLOWUP"
    assert step(M, {"c1": 0.6}, shown=2, topic_score=None).action == "FOLLOWUP"


def test_difficulty_does_not_change_scores():
    s = {"c1": 0.6}
    a, b = step(A, s), step(B, s)
    assert a.next_level == A and b.next_level == B
    assert (a.reason, a.action, a.target_criteria) == (b.reason, b.action, b.target_criteria)
    assert s == {"c1": 0.6}


def test_config_thresholds_respected():
    s = {"c1": 0.85}
    assert step(B, s, cfg=DifficultyConfig(up_score=0.9)).next_level == B
    assert step(B, s).next_level == M


def test_no_evidence_still_closes_early_when_min_two_not_owed():
    st = ControllerState(M, 1, (M,))
    kw = dict(targeted=[], scores={"c": 0.9}, topic_score=0.9, sufficient=True, open_criteria=["d"])
    d = next_step(st, DEFAULT_CONFIG, **kw)
    assert (d.action, d.reason, d.next_level) == ("CLOSE", "NO_EVIDENCE+ENOUGH", M)
    d = next_step(st, DEFAULT_CONFIG, **kw, goal_open=True)
    assert (d.action, d.reason, d.next_level) == ("FOLLOWUP", "NO_EVIDENCE", M)
