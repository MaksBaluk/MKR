"""Interview budgets: max 10 distinct topics, max 5 shown questions per action. CLAUDE_PROMPT §3."""

MAX_TOPICS = 10
MAX_SHOWN_QUESTIONS_PER_ACTION = 5


def can_start_topic(distinct_topics_so_far: int) -> bool:
    return distinct_topics_so_far < MAX_TOPICS


def can_ask_question(shown_for_action: int) -> bool:
    return shown_for_action < MAX_SHOWN_QUESTIONS_PER_ACTION

MIN_SHOWN_QUESTIONS_PER_ACTION = 2
EARLY_CLOSE_SCORE = 0.75  # MATH_SPEC band [.75,.90): "good"; one strong, sufficient answer may close a topic
DECLINED_SCORE = 0.05  # all criteria ~0 with sufficient evidence: the candidate said they have no experience


def needs_min_followup(shown_for_action: int, *, graded: bool, score: float | None, sufficient: bool) -> bool:
    """A graded topic gets a second shown question unless the first answer was sufficient and scored >= 0.75,
    or sufficient and ~0 (the candidate said they do not know or have not worked with it).

    Ungraded topics (no accepted assessment, e.g. no LLM) move on: a fallback bank question would only repeat."""
    if not graded or not can_ask_question(shown_for_action) or shown_for_action >= MIN_SHOWN_QUESTIONS_PER_ACTION:
        return False
    return not (sufficient and score is not None and (score >= EARLY_CLOSE_SCORE or score <= DECLINED_SCORE))


def topic_open_for_question(*, used: bool, distinct_topics: int, shown: int, latest_score_is_null: bool,
                            goal_open: bool = False) -> bool:
    """Whether a topic may receive another planned question.

    New topics need budget left. A started topic is re-asked only while the question cap allows, its latest
    evidence is insufficient (null score) or a validated Evaluator goal still names an open criterion (goal_open),
    and the interview still has topic budget (after ten topics the interview is closed).

    Keep equivalent with needs_min_followup and difficulty.next_step (`enough`): the continuation rule lives in all three."""
    if not used:
        return can_start_topic(distinct_topics)
    return can_ask_question(shown) and (latest_score_is_null or goal_open) and distinct_topics < MAX_TOPICS
