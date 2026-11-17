from backend.api.core import _revisions
from backend.domain.core_flow import eval_group, rank_vacancy, self_claim_metrics
from backend.domain.planner import OpenState, choose_next
from backend.domain.ranking import VacancyRanking, rank
from backend.domain.topic_summary import TopicSummary, needs_verification
from backend.models import CohortSnapshot
from tests.test_interview_flow import cohort, no_llm  # noqa: F401


def _g(*acts, kind="MANDATORY", level=2):
    return {"kind": kind, "alternatives": [{"competency_id": a, "required_level": level} for a in acts]}


def _r(vid, t=0.0, j=0.0, lm=0.5):
    return VacancyRanking(vid, 2, 2, lm, 0.5, 0.0, 0.0, True, True, "RANKED", t_v=t, j_v=j)


def test_tv_jv_hand_example():
    groups = [_g("a", "b"), _g("c"), _g("d")]
    t, j = self_claim_metrics(groups, {"a": 0.8, "b": 0.4, "c": None, "d": 0.6})
    assert abs(t - (0.8 + 0.6) / 3) < 1e-12 and abs(j - 2 / 3) < 1e-12
    assert self_claim_metrics([], {"a": 1.0}) == (0.0, 0.0)


def test_tie_break_only_on_exact_key_tie():
    assert [r.vacancy_id for r in rank([_r("a", t=0.1), _r("b", t=0.9)])] == ["b", "a"]
    assert [r.vacancy_id for r in rank([_r("a", t=0.5, j=0.1), _r("b", t=0.5, j=0.9)])] == ["b", "a"]
    assert [r.vacancy_id for r in rank([_r("a", t=0.1, lm=0.6), _r("b", t=0.9, lm=0.5)])] == ["a", "b"]


def test_self_rating_cannot_satisfy_mandatory():
    v = {"id": "v", "years_min": 0, "groups": [_g("a")]}
    r = rank_vacancy(v, {}, {}, 3, {"a": 0.95})
    assert eval_group(v["groups"][0]["alternatives"], {}, {}).status == "UNRESOLVED"
    assert r.z == 1 and r.l_m == 0.0 and r.t_v == 0.95 and r.label == "LOW_INFORMATION"


def test_missing_self_rating_not_penalised():
    v = {"id": "v", "years_min": 0, "groups": [_g("a")]}
    a = rank_vacancy(v, {}, {}, 3, {})
    b = rank_vacancy({**v, "id": "w"}, {}, {}, 3, {"a": None})
    assert (a.t_v, a.j_v) == (b.t_v, b.j_v) == (0.0, 0.0)


def test_planner_prefers_self_claimed_action_on_tie():
    g1, g2 = ("v", 0), ("v", 1)
    mk = lambda flags: OpenState(frozenset({g1, g2}), {g1: frozenset({"a"}), g2: frozenset({"b"})},
                                 frozenset({g1, g2}), frozenset(flags))
    w = {g1: 0.5, g2: 0.5}
    assert choose_next(mk(()), w, ["a", "b"], {}) == "a"
    assert choose_next(mk({"b"}), w, ["a", "b"], {}) == "b"


def _s(m, e):
    return TopicSummary(m, e, (), (), e >= 0.6)


def test_needs_verification():
    assert needs_verification(0.95, None)
    assert not needs_verification(0.95, _s(0.9, 1.0))
    assert needs_verification(0.95, _s(0.5, 1.0))
    assert not needs_verification(0.3, None)
    assert not needs_verification(None, None)


def test_recommendations_order_follows_215_then_tv_jv(client, auth, cohort, db, no_llm):  # noqa: F811
    skills = client.get(f"/api/v1/cohorts/{cohort}/market", headers=auth).json()["skills"][:25]
    ratings = {}
    for i, s in enumerate(skills):
        v = round(0.1 + 0.8 * ((i * 7) % 10) / 10, 2)
        assert client.put(f"/api/v1/profile/self-ratings/{s['action_id']}", json={"value": v}, headers=auth).status_code == 200
        ratings[s["action_id"]] = v
    items = client.post("/api/v1/recommendations", json={"cohort_id": cohort}, headers=auth).json()["items"]
    revs = {r["id"]: r for r in _revisions(db().get(CohortSnapshot, cohort))}
    keys = []
    for i in items:
        t, j = self_claim_metrics(revs[i["vacancy_id"]]["groups"], ratings)
        keys.append((-i["z"], -i["x"], -i["l_mandatory"], -i["l_preferred"], i["w_mandatory"], i["w_preferred"],
                     -t, -j, i["vacancy_id"]))
    assert len(items) == 5 and keys == sorted(keys)
    assert any(a[:6] == b[:6] and a[6] != b[6] for a, b in zip(keys, keys[1:]))  # some exact (2.15) tie is broken by T_v
