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
