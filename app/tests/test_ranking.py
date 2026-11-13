from backend.domain.ranking import VacancyRanking, rank, z_status


def _r(vid, z=2, x=2, lm=0.5, lp=0.5, wm=0.0, wp=0.0):
    return VacancyRanking(vacancy_id=vid, z=z, x=x, l_m=lm, l_p=lp, w_m=wm, w_p=wp,
                          has_mandatory=True, has_preferred=True, label="RANKED")


def test_z_any_failed_is_zero():
    assert z_status(["SATISFIED", "FAILED"]) == 0


def test_z_unresolved_is_one():
    assert z_status(["SATISFIED", "UNRESOLVED"]) == 1


def test_z_all_satisfied_is_two():
    assert z_status(["SATISFIED", "SATISFIED"]) == 2


def test_z_no_mandatory_is_one():
    assert z_status([]) == 1


def test_order_z_then_x_then_l_then_w_then_id():
    rs = [_r("b", z=2), _r("a", z=2), _r("c", z=1)]
    assert [r.vacancy_id for r in rank(rs)] == ["a", "b", "c"]


def test_narrower_uncertainty_wins_on_tie():
    rs = [_r("a", wm=0.4), _r("b", wm=0.1)]
    assert [r.vacancy_id for r in rank(rs)] == ["b", "a"]


def test_uuid_tie_break_string_ascending():
    u1 = "0f1e2d3c-0000-0000-0000-000000000002"
    u2 = "0f1e2d3c-0000-0000-0000-000000000010"
    assert [r.vacancy_id for r in rank([_r(u2), _r(u1)])] == [u1, u2]


def test_extra_experience_not_penalized_in_order():
    assert rank([_r("a", x=2), _r("b", x=1)])[0].vacancy_id == "a"
