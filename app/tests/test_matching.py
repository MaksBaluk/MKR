from backend.domain.matching import evaluate_group, evaluate_vacancy, rank_snapshot, effective_profile
from backend.domain.adaptive import priorities, choose_topic


def group(items, kind='MANDATORY', gid='g1'):
    return {'id': gid, 'label': 'test', 'kind': kind, 'alternatives': [
        {'competency_id': action, 'required_level': level, 'normalization_status': 'ACCEPTED_CURATED'}
        for action, level in items]}


def vacancy(vid, requirements):
    return {'id': vid, 'title': vid, 'years_min': 0, 'groups': requirements}


def test_or_tristate():
    g = group([('fastapi', 2), ('django', 2)])
    assert evaluate_group(g, {'fastapi': 3})['state'] == 'S'
    assert evaluate_group(g, {'fastapi': 1})['state'] == 'U'
    assert evaluate_group(g, {'fastapi': 1, 'django': 0})['state'] == 'F'
    assert evaluate_group(g, {})['state'] == 'U'
    assert evaluate_group(g, {'django': 2})['state'] == 'S'


def test_empty_and_unknown_match():
    result = evaluate_vacancy(vacancy('v1', [group([('python', 2)])]), {})
    assert result['match'] is None and result['coverage'] == 0 and result['r_score'] == 0
    assert (result['s'], result['f'], result['u']) == (0, 0, 1)
    no_groups = evaluate_vacancy(vacancy('v2', []), {})
    assert not no_groups['evaluable'] and no_groups['match'] is None and no_groups['r_score'] is None


def test_ranking_e_r_coverage_stable():
    vacancies = [
        vacancy('c', [group([('a', 2)]), group([('b', 1)], 'DESIRED', 'c2')]),
        vacancy('b', [group([('a', 1)])]),
        vacancy('a', [group([('a', 1)])]),
    ]
    result = rank_snapshot(vacancies, {'a': 1, 'b': 0})
    assert [r['vacancy_id'] for r in result] == ['a', 'b', 'c']
    assert result[0]['required_class'] == 2
    assert result[2]['required_class'] == 0


def test_mcq_level1_cannot_inflate_advanced_skill():
    p = effective_profile({'python': 2, 'django': None}, {'python', 'django'})
    assert p['levels']['python'] == 2 and p['levels']['django'] == 1
    assert p['provenance']['python'] == 'SELF_REPORT_WITH_DEMO_TASK'


def test_adaptive_uses_all_frozen_vacancies_and_repeats_are_bounded():
    vacancies = [vacancy('v1', [group([('python', 2)])]), vacancy('v2', [group([('python', 2)], gid='g2'), group([('sql', 2)], gid='g3')])]
    p = priorities(vacancies, {})
    assert p[0]['competency_id'] == 'python'
    assert choose_topic(vacancies, {}, set(), {'python': 2})['competency_id'] == 'sql'
