import json
import pytest
from backend.providers import llm


def test_dynamic_question_generation_and_shape(monkeypatch):
    cfg = llm.get_settings()
    monkeypatch.setattr(cfg, 'llm_provider', 'anthropic')
    monkeypatch.setattr(cfg, 'llm_api_key', 'dummy-secret-test')
    monkeypatch.setattr(cfg, 'llm_question_generation', True)
    monkeypatch.setattr(llm, '_text', lambda prompt, max_tokens=280: json.dumps({
        'question': 'How would you diagnose a production outage in this stack, and what evidence would you capture?',
        'focus': 'incident response'
    }))
    question = llm.generate_interview_question(competency_label='Backend', mode='VERIFY',baseline_level=2,
        vacancy_requirements=[{'vacancy_title':'Backend developer','requirement':'REST APIs'}],
        recent_turns=[{'answer':'I used SQL'}],previous_question='What is SQL?')
    assert question['source'] == 'LLM_GENERATED'
    assert question['question'].endswith('?')


def test_dynamic_question_rejects_invalid_output(monkeypatch):
    cfg = llm.get_settings()
    monkeypatch.setattr(cfg, 'llm_provider', 'anthropic')
    monkeypatch.setattr(cfg, 'llm_api_key', 'dummy-secret-test')
    monkeypatch.setattr(cfg, 'llm_question_generation', True)
    monkeypatch.setattr(llm, '_text', lambda prompt, max_tokens=280: '{"question":"hi"}')
    with pytest.raises(llm.LLMUnavailable):
        llm.generate_interview_question(competency_label='Backend',mode='DISCOVER',baseline_level=None,
            vacancy_requirements=[],recent_turns=[],previous_question='x')


def test_review_proposal_never_contains_numeric_level(monkeypatch):
    cfg = llm.get_settings()
    monkeypatch.setattr(cfg, 'llm_provider', 'anthropic')
    monkeypatch.setattr(cfg, 'llm_api_key', 'dummy-secret-test')
    monkeypatch.setattr(llm, '_text', lambda prompt, max_tokens=420: json.dumps({
        'summary':'one scenario', 'evidence':'mentioned indexes', 'limitations':'no external validation'}))
    proposal=llm.assessment_proposal('SQL','How optimize','Indexes')
    assert proposal['status']=='PENDING_HUMAN_REVIEW' and 'level' not in proposal
