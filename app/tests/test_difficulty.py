from backend.domain.difficulty import (
    DEFAULT_CONFIG, ControllerState, Difficulty, DifficultyConfig, initial_difficulty, market_level, next_step, rank,
)

B, I, A = Difficulty.BASIC, Difficulty.INTERMEDIATE, Difficulty.ADVANCED


def step(level, scores, *, targeted=None, shown=1, topic_score=0.5, sufficient=True, open_=("c3",), goal=False,
         cfg=DEFAULT_CONFIG):
    return next_step(ControllerState(level, shown, ()), cfg, targeted=targeted if targeted is not None else list(scores),
                     scores=scores, topic_score=topic_score, sufficient=sufficient, open_criteria=list(open_),
                     goal_open=goal)


def test_initial():
    assert initial_difficulty("junior", None) == (B, "LEVEL:junior")
    assert initial_difficulty("senior", None)[0] == A
    assert initial_difficulty(None, "middle") == (I, "MARKET:middle")
    assert initial_difficulty(None, None) == (I, "DEFAULT")
    assert initial_difficulty("junior", "senior")[0] == B


def test_market_level():
    assert market_level([1, 2, 6]) == "middle"
    assert market_level([None, None]) is None
    assert market_level([0, 1]) == "junior"
    assert market_level([5, None, 7]) == "senior"


def test_rank():
    assert [rank(d) for d in (B, I, A)] == [0, 1, 2]


def test_junior_strong_steps_up_one_at_a_time():
    s = {"c1": 0.9, "c2": 0.8}
    d1 = step(B, s)
    assert d1.next_level == I and d1.reason == "STRONG" and d1.action == "CONTINUE"
    assert step(I, s).next_level == A
    assert step(A, s).next_level == A


def test_senior_weak_steps_down_to_floor():
    s = {"c1": 0.2}
    d = step(A, s)
    assert d.next_level == I and d.reason == "WEAK"
    assert step(I, s).next_level == B
    assert step(B, s).next_level == B


def test_incomplete_weak_answer_does_not_lower():
    d = step(I, {"c1": 0.1, "c2": None})
    assert d.next_level == I and d.reason == "PARTIAL" and d.action == "FOLLOWUP"


def test_all_null_no_change():
    d = step(A, {"c1": None})
    assert d.next_level == A and d.reason == "NO_EVIDENCE" and d.action == "FOLLOWUP"
    assert d.target_criteria == ("c3",)
    d = step(A, {}, targeted=["c1", "c2"])
    assert d.reason == "NO_EVIDENCE"
    assert step(A, {}, targeted=[]).reason == "NO_EVIDENCE"


def test_strong_but_not_sufficient_no_raise():
    d = step(B, {"c1": 0.9}, sufficient=False)
    assert d.next_level == B and d.reason == "PARTIAL"


def test_close_when_no_open_criteria():
    d = step(I, {"c1": 0.9}, open_=())
    assert d.action == "CLOSE" and d.reason == "NO_OPEN_CRITERIA" and d.next_level == I


def test_close_at_question_cap():
    d = step(I, {"c1": 0.1}, shown=5)
    assert d.action == "CLOSE" and d.reason == "QUESTION_CAP" and d.next_level == I


def test_close_when_min_two_met_and_no_goal():
    d = step(B, {"c1": 0.9}, shown=2, topic_score=0.8)
    assert d.action == "CLOSE" and d.reason == "STRONG+ENOUGH" and d.next_level == I


def test_continue_when_goal_open():
    d = step(B, {"c1": 0.9}, shown=2, topic_score=0.8, goal=True)
    assert d.action == "CONTINUE"


def test_no_close_when_min_followup_owed_or_null_topic():
    assert step(I, {"c1": 0.6}, shown=1, topic_score=0.6).action == "FOLLOWUP"
    assert step(I, {"c1": 0.6}, shown=2, topic_score=None).action == "FOLLOWUP"


def test_difficulty_does_not_change_scores():
    s = {"c1": 0.6}
    a, b = step(A, s), step(B, s)
    assert a.next_level == A and b.next_level == B
    assert (a.reason, a.action, a.target_criteria) == (b.reason, b.action, b.target_criteria)
    assert s == {"c1": 0.6}


def test_config_thresholds_respected():
    s = {"c1": 0.85}
    assert step(B, s, cfg=DifficultyConfig(up_score=0.9)).next_level == B
    assert step(B, s).next_level == I
