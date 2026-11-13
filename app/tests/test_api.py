import hashlib
import json
from backend.seed import read_fixture, seed_database
from backend.models import Vacancy, Snapshot


def test_seed_idempotency(db):
    with db() as session:
        counts = seed_database(session, demo_mode=True, demo_password='test-demo-password-123')
        assert counts == {'competencies_added': 0,'vacancies_added': 0, 'demo_user_added':0}


def test_catalog_profile_and_snapshot(client, auth):
    res = client.get('/api/v1/vacancies?track=python&page_size=100')
    assert res.status_code == 200 and res.json()['total'] == 30
    assert len(res.json()['items']) == 30
    det = client.get('/api/v1/vacancies/python-01').json()
    assert len(det['groups']) >= 10
    assert not det['source_url']
    p = client.get('/api/v1/profile', headers=auth).json()
    assert p['track'] == 'python'
    skills = client.get('/api/v1/competencies?track=python').json()
    assert len(skills) == 20
    skill_id = skills[0]['id']
    res = client.put(f'/api/v1/profile/skills/{skill_id}',headers=auth,json={'level': 2,'context': 'demo'})
    assert res.status_code == 200
    snap = client.post('/api/v1/snapshots',headers=auth,json={'vacancy_ids':['python-01','python-02'],'name':'test freeze'})
    assert snap.status_code == 201, snap.text
    body = snap.json()
    assert body['status'] == 'FROZEN' and len(body['sha256']) == 64
    raw = json.dumps(body['vacancies'], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    assert hashlib.sha256(raw.encode()).hexdigest() == body['sha256']
    assert client.post('/api/v1/snapshots',headers=auth,json={'vacancy_ids':['python-01','marketing-01'],'name':'mixed'}).status_code == 422


def test_adaptive_interview_and_matches(client,auth):
    snap = client.post('/api/v1/snapshots',headers=auth,json={'vacancy_ids':['python-01','python-02'],'name':'demo'}).json()
    start = client.post('/api/v1/interviews',headers=auth,json={'snapshot_id':snap['id'],'question_budget':4})
    assert start.status_code == 201, start.text
    session = start.json()
    first = client.post(f"/api/v1/interviews/{session['id']}/next-question",headers=auth,json={'state_version': session['state_version']})
    assert first.status_code == 200, first.text
    session = first.json()
    q = session['current_question']
    assert q and q['question_source'] == 'CURATED_BANK'
    assert 'correct_option' not in q
    assert client.post(f"/api/v1/interviews/{session['id']}/next-question", headers=auth,
                       json={'state_version':session['state_version']}).status_code == 409
    if q['question_kind']=='MULTIPLE_CHOICE':
        answer = {'turn_id': q['id'], 'state_version': session['state_version'],
                  'option_id':read_fixture('questions.json')[q['competency_id']][0]['correct_option'],
                  'idempotency_key':'first-answer-00001'}
    else:
        answer = {'turn_id': q['id'], 'state_version': session['state_version'],
                  'answer_text': 'example', 'idempotency_key': 'first-answer-00001'}
    res = client.post(f"/api/v1/interviews/{session['id']}/answers",headers=auth,json=answer)
    assert res.status_code == 200, res.text
    again = client.post(f"/api/v1/interviews/{session['id']}/answers",headers=auth,json=answer)
    assert again.status_code == 200 and again.json()['idempotent_replay']
    session = res.json()
    if session['status'] == 'READY':
        second = client.post(f"/api/v1/interviews/{session['id']}/next-question",headers=auth,json={'state_version':session['state_version']})
        assert second.status_code == 200
        session = second.json()
    finished = client.post(f"/api/v1/interviews/{session['id']}/finish",headers=auth,json={'state_version':session['state_version']})
    assert finished.status_code == 200 and finished.json()['status'] == 'COMPLETED'
    ranked = client.post('/api/v1/matches',headers=auth,json={'snapshot_id':snap['id'],'interview_id':session['id']})
    assert ranked.status_code == 201, ranked.text
    result = ranked.json()
    assert result['total'] == 2 and len(result['items']) == 2
    assert all(item['s']+item['f']+item['u'] == len(item['groups']) for item in result['items'])
    explain = client.get(f"/api/v1/matches/{result['id']}/vacancies/python-01",headers=auth)
    assert explain.status_code == 200


def test_user_isolation_and_wrong_tracks(client,auth):
    demo_snap = client.post('/api/v1/snapshots',headers=auth,json={'vacancy_ids':['python-01'],'name':'private'}).json()
    newcomer = client.post('/api/v1/auth/register',json={'email':'another@local.test','display_name':'New Candidate', 'password':'longpassword123'})
    assert newcomer.status_code == 201
    other = {'Authorization':f"Bearer {newcomer.json()['token']}"}
    assert client.get(f"/api/v1/snapshots/{demo_snap['id']}",headers=other).status_code == 404
    assert client.get('/api/v1/profile',headers=other).json()['skills'] == []
    assert client.post('/api/v1/matches',headers=other,json={'snapshot_id':demo_snap['id']}).status_code == 404
    assert client.get('/api/v1/profile').status_code == 401


def test_profile_purge(client,auth):
    snap = client.post('/api/v1/snapshots',headers=auth,json={'vacancy_ids':['python-01'],'name':'purge'}).json()
    assert client.delete('/api/v1/profile/data',headers=auth).status_code == 204
    assert client.get('/api/v1/snapshots',headers=auth).json() == []
    assert client.get(f"/api/v1/snapshots/{snap['id']}",headers=auth).status_code == 404


def test_config_safe_and_llm_disabled(client):
    status = client.get('/api/v1/config')
    assert status.status_code == 200 and status.json()['parsing'] == 'NOT_IMPLEMENTED'
    assert 'api_key' not in json.dumps(status.json()).lower()
