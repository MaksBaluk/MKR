from backend.domain.market import VacancyInput, compute_market


def test_repeated_mention_counts_once():
    vs = [VacancyInput("v1", (("py",), ("py", "sql"))), VacancyInput("v2", (("sql",),))]
    m = {e.action_id: e for e in compute_market(vs)}
    assert m["py"].prevalence == 0.5
    assert m["sql"].prevalence == 1.0


def test_mass_sums_to_one():
    vs = [VacancyInput("v1", (("a",), ("b", "c"))), VacancyInput("v2", (("a",),))]
    assert abs(sum(e.mass for e in compute_market(vs)) - 1.0) < 1e-12


def test_or_alternatives_split_group_mass():
    m = {e.action_id: e.mass for e in compute_market([VacancyInput("v1", (("a", "b"),))])}
    assert m["a"] == 0.5 and m["b"] == 0.5


def test_empty_catalog_returns_empty():
    assert compute_market([]) == []


def test_ordering_prevalence_then_mass_then_id():
    # N=2. F: a=b=c=0.5. I: a=0.5, b=0.25, c=0.25 → order a, then b<c by id.
    vs = [VacancyInput("v1", (("b",), ("c",))), VacancyInput("v2", (("a",),))]
    assert [e.action_id for e in compute_market(vs)] == ["a", "b", "c"]
