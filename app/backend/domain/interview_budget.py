"""Interview budgets: max 10 distinct topics, max 5 shown questions per action. CLAUDE_PROMPT §3."""

MAX_TOPICS = 10
MAX_SHOWN_QUESTIONS_PER_ACTION = 5


def can_start_topic(distinct_topics_so_far: int) -> bool:
    return distinct_topics_so_far < MAX_TOPICS


def can_ask_question(shown_for_action: int) -> bool:
    return shown_for_action < MAX_SHOWN_QUESTIONS_PER_ACTION
