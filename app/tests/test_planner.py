from backend.domain.planner import OpenState, choose_next, coverage


def _state(open_groups, alts, mandatory=(), needs_verify=()):
    return OpenState(
        open_groups=frozenset(open_groups),
        open_alternatives={k: frozenset(v) for k, v in alts.items()},
        mandatory_groups=frozenset(mandatory),
        self_rating_needs_verification=frozenset(needs_verify),
    )


G1 = ("v1", 0)
G2 = ("v2", 0)


def test_coverage_monotone_for_fixed_state():
    st = _state([G1, G2], {G1: {"a", "b"}, G2: {"c"}})
    w = {G1: 0.5, G2: 0.5}
    assert coverage(st, w, frozenset()) == 0.0
    assert coverage(st, w, frozenset({"a"})) <= coverage(st, w, frozenset({"a", "c"}))


def test_coverage_diminishing_returns():
    st = _state([G1, G2], {G1: {"a"}, G2: {"a"}})
    w = {G1: 0.5, G2: 0.5}
    gain_empty = coverage(st, w, frozenset({"a"})) - coverage(st, w, frozenset())
    gain_after = coverage(st, w, frozenset({"a", "x"})) - coverage(st, w, frozenset({"x"}))
    assert gain_after <= gain_empty + 1e-12


def test_closed_group_not_counted():
    st = _state([], {G1: {"a"}})
    assert coverage(st, {G1: 1.0}, frozenset({"a"})) == 0.0


def test_self_rating_alone_not_closing():
    # self rating never appears in open_groups changes; planner only uses open state
    st = _state([G1], {G1: {"a"}}, needs_verify={"a"})
    assert coverage(st, {G1: 1.0}, frozenset({"a"})) == 1.0


def test_choose_next_prefers_higher_marginal_gain():
    st = _state([G1, G2], {G1: {"a"}, G2: {"b", "c"}})
    w = {G1: 0.5, G2: 0.6}
    assert choose_next(st, w, ["a", "b"], {"a": 0.1, "b": 0.1}) == "b"


def test_tie_prefers_mandatory_then_verify_then_mass_then_id():
    st = _state([G1, G2], {G1: {"a"}, G2: {"b"}}, mandatory=[G1])
    w = {G1: 0.5, G2: 0.5}
    assert choose_next(st, w, ["a", "b"], {"a": 0.1, "b": 0.1}) == "a"
    st2 = _state([G1, G2], {G1: {"a"}, G2: {"b"}}, needs_verify=["b"])
    assert choose_next(st2, w, ["a", "b"], {"a": 0.1, "b": 0.1}) == "b"
    assert choose_next(st, w, ["b", "a"], {"a": 0.2, "b": 0.1}) == "a"


def test_returns_none_on_zero_gain():
    st = _state([], {})
    assert choose_next(st, {}, ["a"], {"a": 0.5}) is None
