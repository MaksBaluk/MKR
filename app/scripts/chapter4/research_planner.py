"""RESEARCH planner for mode C ADAPTIVE_NO_MARKET (chapter-4 experiment only; NOT a product mode).

Everything of the product's adaptive interview stays as is (follow-up goals, minimum two questions, difficulty/v2, level
probe, evidence-based closing of requirement groups, caps, Evaluator, estimator, ranking). Only the next-topic choice is
replaced: instead of backend.domain.planner.choose_next (argmax of the market-weighted coverage gain Q_t, ties by
mandatory groups, self-rating verification and market mass I(c)) the research planner picks uniformly at random
(deterministic per run seed) among the topics that still have an open requirement group. It reads neither the group
weights (F(c), I(c)), nor Q_t, nor the market mass, nor which groups are mandatory.

The candidate pool itself (competencies that occur in the frozen cohort) is the same relevance set every mode uses;
only its ordering by market importance is removed. Applied by patching the name `choose_next` inside backend.api.core
for the duration of one run (product source unchanged; tests/test_chapter4_modes.py checks the patch is restored).
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from contextlib import contextmanager

import backend.api.core as core

VERSION = "research-no-market/v1"


def no_market_choice(seed: int):
    def choose(state, weights: Mapping, available: Sequence[str], market_mass: Mapping[str, float]) -> str | None:
        del weights, market_mass  # deliberately unused: no market prioritisation
        open_topics = [c for c in available
                       if any(c in state.open_alternatives.get(g, frozenset()) for g in state.open_groups)]
        if not open_topics:
            return None  # same stopping rule as the product: no open group left -> plan exhausted
        return min(open_topics, key=lambda c: hashlib.sha256(f"{seed}:{c}".encode()).hexdigest())
    return choose


@contextmanager
def no_market_planner(seed: int):
    original = core.choose_next
    core.choose_next = no_market_choice(seed)
    try:
        yield
    finally:
        core.choose_next = original
