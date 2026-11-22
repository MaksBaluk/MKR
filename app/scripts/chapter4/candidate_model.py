"""SIMULATED candidate behaviour model for the chapter-4 mode comparison (stage 5) and adaptivity evidence (stage 6).

Not real candidates and not a sample of real candidates: every profile is a hand-defined vector of latent competence
per rubric criterion. The generative algorithm (documented for thesis section 4.2 in
artifacts/chapter4/simulation_method.md):

1. Latent truth t(c) in [0, 1] per criterion c (profile rule: exact criterion -> topic prefix -> policy level group ->
   default). Practice criteria (practice-backend.*) have their own latent values.
2. The Interviewer stub (UaModel, Ukrainian-only question text) asks about the follow-up goal criteria if the product
   passed one, else the first `per_q` unmet criteria it received, at the difficulty Python chose.
3. The candidate answers ONLY the criteria that question targeted: one sentence per criterion with the phrase of the
   anchor quant(t(c)) in {0.9, 0.78, 0.6, 0.3, 0.0}. Practice aspects are disclosed only when the question invites them
   (Python's practice_gaps hint; rationale/diagnosis at INTERMEDIATE; five aspects at ADVANCED). A bank fallback question
   (no targets known) gets a generic sentence that evidences nothing.
4. The Evaluator stub grades only criteria an answer sentence addresses, quoting it verbatim, with deterministic noise
   Noise(seed): jitter +-0.10, miss 8 %, over-/under-grade +-0.15 at 5 % each, keyed by (seed, criterion, topic answer
   index) so a rerun is identical and the same answer position gets the same noise in every mode.
5. Everything else is the product: profile, system cohort, planner Q_t, caps, difficulty/v2, follow-up rules, level
   probe, validation, storage, SeniorityEstimator (policy python-backend/v4), ranking (2.15).

Answers do not depend on question difficulty except practice disclosure (step 3): this is a stated model assumption.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from backend.domain.seniority import CriterionEvidence, estimate
from backend.domain.seniority_policy import PRACTICE_CRITERIA, Level, policy_for
from backend.experiments.providers import CandidateSpec
from backend.seed import read_fixture
from scripts.seniority_realistic import Candidate, quant

_RUBRICS = read_fixture("rubrics.json")["rubrics"]
TRACK_ACTIONS = {"python": [r["action_id"] for r in _RUBRICS[:20]], "marketing": [r["action_id"] for r in _RUBRICS[20:40]],
                 "design": [r["action_id"] for r in _RUBRICS[40:]]}
CRITERIA = {r["action_id"]: [c["criterion_id"] for c in r["criteria"]] for r in _RUBRICS}


def _members(level: Level) -> frozenset[str]:
    rule = next(r for r in policy_for("python").rules if r.level == level)
    return frozenset(c for p in rule.pools for c in p.members if not c.startswith("practice"))


J, M, S = _members(Level.JUNIOR), _members(Level.MIDDLE), _members(Level.SENIOR)
CRITICAL = J | M | S  # level-critical technical criteria of python-backend/v4


@dataclass(frozen=True)
class SimProfile:
    """One simulated candidate. `rules` maps an exact criterion id, a topic prefix ("kafka") or a group name
    ("J", "M", "S", "practice", "practice-backend.<aspect>") to latent competence; lookup order: criterion, topic,
    group (J before M before S), practice, default. `intended` is the level the profile was designed to have."""
    profile_id: str
    track: str
    desired: str
    years: int
    intended: str
    pattern: str
    rules: Mapping[str, float]
    default: float
    self_ratings: Mapping[str, float] = field(default_factory=dict)

    def truth(self, cid: str) -> float:
        r = self.rules
        if cid in r:
            return r[cid]
        topic = cid.split(".", 1)[0]
        if topic in r:
            return r[topic]
        if cid.startswith("practice-backend."):
            return r.get("practice", self.default)
        for name, group in (("J", J), ("M", M), ("S", S)):
            if cid in group and name in r:
                return r[name]
        return self.default

    def spec(self) -> CandidateSpec:
        title = {"python": "Python Developer", "marketing": "Digital Marketing Specialist",
                 "design": "Product Designer"}[self.track]
        return CandidateSpec(self.profile_id, title, self.years, self.desired, self.track, "Київ", "remote",
                             dict(self.self_ratings))

    def candidate(self, model: str = "insensitive") -> Candidate:
        return CANDIDATE_MODELS[model](self.profile_id, self.truth)


_PRACT_MID = {"practice-backend.independence": 0.85, "practice-backend.rationale": 0.82,
              "practice-backend.diagnosis": 0.82}
_PRACT_JUN = {"practice-backend.independence": 0.8}


def _p(pid, desired, years, intended, pattern, default, rules, track="python", self_ratings=None) -> SimProfile:
    return SimProfile(pid, track, desired, years, intended, pattern, rules, default, self_ratings or {})


JUNIOR = {"J": 0.8, "M": 0.45, "S": 0.2, "practice": 0.4, **_PRACT_JUN}
MIDDLE = {"J": 0.85, "M": 0.82, "S": 0.55, "practice": 0.55, **_PRACT_MID}
SENIOR = {"J": 0.9, "M": 0.9, "S": 0.9, "practice": 0.88}

_SYS = {"rest-api": 0.3, "fastapi.dependencies": 0.3, "django.architecture": 0.3, "async-python": 0.3,
        "fastapi.async": 0.3}  # service design / async (system design) weak
_DECLINE_INFRA = {"aws": 0.0, "kafka": 0.0}  # "never used" -> declines (validated no_experience)
_SYS_MID = {"fastapi.dependencies": 0.3, "rest-api.pagination": 0.3, "django.architecture": 0.3}  # service design weak

# 18 pilot python-backend profiles: 6 designed JUNIOR, 6 MIDDLE, 6 SENIOR, with mixed strengths. The `pattern` and the
# latent rules are HIDDEN scenario data (data/hidden/scenario_definitions.json); the product only sees spec().
PROFILES: tuple[SimProfile, ...] = (
    _p("C01", "junior", 1, "JUNIOR", "solid Junior basics, weak beyond", 0.4, JUNIOR),
    _p("C02", "junior", 1, "JUNIOR", "strong Python, weak PostgreSQL", 0.4,
       {**JUNIOR, "python-core": 0.92, "postgresql": 0.3}),
    _p("C03", "junior", 2, "JUNIOR", "strong SQL, weak system design", 0.4,
       {**JUNIOR, "sql": 0.92, **_SYS}),
    _p("C04", "middle", 2, "JUNIOR", "good basics, low independence", 0.4,
       {**JUNIOR, "practice-backend.independence": 0.4}),
    _p("C05", "senior", 3, "JUNIOR", "high desired level, weak evidence beyond Junior", 0.4, JUNIOR,
       self_ratings={"postgresql": 0.9, "kubernetes": 0.85, "kafka": 0.8}),
    _p("C06", "junior", 1, "JUNIOR", "strong answers on few topics, declines the rest (low coverage)", 0.0,
       {"J": 0.85, "practice": 0.0, **_PRACT_JUN}),
    _p("C07", "middle", 4, "MIDDLE", "solid Middle", 0.7, MIDDLE),
    _p("C08", "middle", 4, "MIDDLE", "strong Python, weak PostgreSQL", 0.7,
       {**MIDDLE, "python-core": 0.92, "postgresql": 0.3}),
    _p("C09", "middle", 5, "MIDDLE", "strong SQL, weak service design", 0.7, {**MIDDLE, "sql": 0.92, **_SYS_MID}),
    _p("C10", "middle", 4, "MIDDLE", "good basics, low independence", 0.7,
       {**MIDDLE, "practice-backend.independence": 0.4}),
    _p("C11", "senior", 6, "MIDDLE", "high desired level, Middle evidence (over-claim)", 0.7, MIDDLE,
       self_ratings={"postgresql": 0.95, "kafka": 0.9, "kubernetes": 0.9}),
    _p("C12", "middle", 4, "MIDDLE", "Middle with one weak criterion (postgresql.indexes)", 0.7,
       {**MIDDLE, "postgresql.indexes": 0.3}),
    _p("C13", "senior", 8, "SENIOR", "full Senior", 0.85, SENIOR),
    _p("C14", "junior", 8, "SENIOR", "full Senior evidence, desired Junior", 0.85, SENIOR),
    _p("C15", "senior", 9, "SENIOR", "strong architecture, handles incomplete information poorly", 0.85,
       {**SENIOR, "practice-backend.ambiguity": 0.4}),
    _p("C16", "senior", 8, "SENIOR", "strong professional answers, declines AWS and Kafka (lower coverage)", 0.85,
       {**SENIOR, **_DECLINE_INFRA}),
    _p("C17", "senior", 10, "SENIOR", "strong Python, weaker PostgreSQL basics (indexes/schema partial)", 0.85,
       {**SENIOR, "python-core": 0.95, "postgresql.indexes": 0.6, "postgresql.schema": 0.6}),
    _p("C18", "senior", 7, "SENIOR", "Senior with a weak version-control criterion (git.branching)", 0.85,
       {**SENIOR, "git.branching": 0.4}),
)
BY_ID = {p.profile_id: p for p in PROFILES}


def oracle_level(profile: SimProfile) -> str:
    """Level of the estimator on a PERFECT-OBSERVATION evidence set: every python criterion graded at quant(truth),
    confirmed by two distinct answers, practice traced in three topics. It is the generator's reference level
    (SIMULATED_GROUND_TRUTH), not a real expert label. NOT_APPLICABLE without a policy."""
    pol = policy_for(profile.track)
    if pol is None:
        return "NOT_APPLICABLE"
    ev: dict[str, CriterionEvidence] = {}
    for action in TRACK_ACTIONS["python"]:
        for c in CRITERIA[action]:
            s = quant(profile.truth(c))
            ev[c] = CriterionEvidence(c, s, ("o1", "o2"), s == 0.0, (), ((s, ("o1",)), (s, ("o2",))))
    for c in PRACTICE_CRITERIA:
        s = quant(profile.truth(c))
        ev[c] = CriterionEvidence(c, s, ("o1",), False, (s, s, s), ())
    return estimate(pol, ev).assessed_level


def truth_table(profile: SimProfile) -> dict[str, float]:
    ids = [c for a in TRACK_ACTIONS[profile.track] for c in CRITERIA[a]]
    if profile.track == "python":
        ids += list(PRACTICE_CRITERIA)
    return {c: profile.truth(c) for c in ids}


class TruthProvider:
    """AnswerProvider: answers only what the Interviewer stub targeted (model.questions maps question text -> meta)."""

    source = "SIMULATED"

    def __init__(self, model, candidate: Candidate):
        self.model, self.cand = model, candidate

    def answer(self, candidate: CandidateSpec, turn: Mapping) -> str:
        return self.cand.answer(self.model.questions.get(turn["question_text"]))


TruthFn = Callable[[str], float]


# Sensitivity variant (labelled DIFFICULTY_SENSITIVE): the question's difficulty changes what an answer can show.
# A BASIC question cannot demonstrate more than the "applied in practice" anchor (latent value capped at 0.80); a
# question above the candidate's latent level (INTERMEDIATE for t < 0.50, ADVANCED for t < 0.75) is answered one step
# weaker (latent value - 0.15). The numbers are a modelling assumption for the ablation, not a measured fact.
CEILING = {"BASIC": 0.80}
STRETCH = {"INTERMEDIATE": 0.50, "ADVANCED": 0.75}


def sensitive_truth(t: float, difficulty: str) -> float:
    t = min(t, CEILING.get(difficulty, 1.0))
    return max(0.0, t - 0.15) if t < STRETCH.get(difficulty, 0.0) else t


class DifficultySensitiveCandidate(Candidate):
    def answer(self, meta: dict | None) -> str:
        if meta is None:
            return super().answer(meta)
        base = self.truth
        return Candidate(self.name, lambda c: sensitive_truth(base(c), meta["difficulty"])).answer(meta)


CANDIDATE_MODELS = {"insensitive": Candidate, "sensitive": DifficultySensitiveCandidate}
