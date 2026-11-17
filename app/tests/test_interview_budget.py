from backend.domain.interview_budget import (
    MAX_SHOWN_QUESTIONS_PER_ACTION,
    MAX_TOPICS,
    can_ask_question,
    can_start_topic,
)


def test_topic_cap_is_ten():
    assert MAX_TOPICS == 10
    assert can_start_topic(9) is True
    assert can_start_topic(10) is False


def test_question_cap_is_five_per_action():
    assert MAX_SHOWN_QUESTIONS_PER_ACTION == 5
    assert can_ask_question(4) is True
    assert can_ask_question(5) is False


def test_first_weak_answer_needs_second_question():
    from backend.domain.interview_budget import needs_min_followup
    assert needs_min_followup(1, graded=True, score=0.2, sufficient=False) is True
    assert needs_min_followup(1, graded=True, score=None, sufficient=False) is True
    assert needs_min_followup(1, graded=True, score=0.9, sufficient=False) is True  # not marked sufficient


def test_strong_sufficient_first_answer_may_close_topic():
    from backend.domain.interview_budget import EARLY_CLOSE_SCORE, needs_min_followup
    assert EARLY_CLOSE_SCORE == 0.75
    assert needs_min_followup(1, graded=True, score=0.9, sufficient=True) is False
    assert needs_min_followup(1, graded=True, score=0.75, sufficient=True) is False
    assert needs_min_followup(1, graded=True, score=0.74, sufficient=True) is True


def test_min_followup_stops_at_two_and_skips_ungraded():
    from backend.domain.interview_budget import needs_min_followup
    assert needs_min_followup(2, graded=True, score=0.2, sufficient=False) is False
    assert needs_min_followup(5, graded=True, score=None, sufficient=False) is False
    assert needs_min_followup(1, graded=False, score=None, sufficient=False) is False


def test_no_reask_of_unfinished_topic_after_ten_topics():
    from backend.domain.interview_budget import topic_open_for_question
    # below the topic cap an unfinished (null-score) topic may still be re-asked, within the question cap
    assert topic_open_for_question(used=True, distinct_topics=9, shown=2, latest_score_is_null=True) is True
    # once ten distinct topics exist, interview topics are closed: no re-asks, no new topics
    assert topic_open_for_question(used=True, distinct_topics=10, shown=2, latest_score_is_null=True) is False
    assert topic_open_for_question(used=False, distinct_topics=10, shown=0, latest_score_is_null=False) is False
    assert topic_open_for_question(used=False, distinct_topics=9, shown=0, latest_score_is_null=False) is True
    # per-action question cap still applies
    assert topic_open_for_question(used=True, distinct_topics=3, shown=5, latest_score_is_null=True) is False


def test_declined_topic_closes_after_the_first_answer():
    from backend.domain.interview_budget import needs_min_followup
    # the candidate said they have no experience: zero scores with sufficient evidence, nothing more to ask
    assert needs_min_followup(1, graded=True, score=0.0, sufficient=True) is False
    # a weak score without sufficient evidence still gets a second question
    assert needs_min_followup(1, graded=True, score=0.0, sufficient=False) is True
    assert needs_min_followup(1, graded=True, score=0.3, sufficient=True) is True
