"""Immutable P0 (baseline) and P1 (post-interview) effective profile versions.

Ruling: versions are written through a session argument, not a service class — the project is a lean MVP.
"""
import hashlib
import json
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy import select as _select
from backend.models import EvidenceItem, ProfileVersion
from .matching import effective_profile
from .adaptive import observed_successes


def _digest(levels: dict, provenance: dict) -> str:
    raw = json.dumps({"levels": levels, "provenance": provenance}, ensure_ascii=False,
                     sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def create_profile_version(db: Session, *, user_id: str, kind: str, levels: dict, provenance: dict,
                           interview_id: str | None = None, evidence_refs: list | None = None) -> ProfileVersion:
    existing = db.scalar(select(ProfileVersion).where(
        ProfileVersion.user_id == user_id, ProfileVersion.interview_id == interview_id, ProfileVersion.kind == kind))
    if existing is not None:
        return existing
    row = ProfileVersion(user_id=user_id, kind=kind, interview_id=interview_id, levels=levels,
                         provenance=provenance, evidence_refs=list(evidence_refs or []),
                         sha256=_digest(levels, provenance))
    db.add(row)
    db.flush()
    return row


def _is_conflict(baseline: int | None, level: int) -> bool:
    """Self-report 0 vs confirmed >=1, or a gap of two or more levels: keep the topic open, do not overwrite silently."""
    return baseline is not None and ((baseline == 0 and level >= 1) or abs(level - baseline) >= 2)


def verification_topics(db: Session, interview) -> set[str]:
    """Competencies whose claims still need follow-up: proposals awaiting review and open conflicts."""
    topics: set[str] = set()
    for item in db.scalars(_select(EvidenceItem).where(EvidenceItem.interview_id == interview.id)).all():
        if item.status == "PROPOSED":
            topics.add(item.competency_id)
        elif item.status == "CONFIRMED" and _is_conflict(interview.baseline_profile.get(item.competency_id), item.level):
            topics.add(item.competency_id)
    return topics


def ensure_p1(db: Session, interview) -> ProfileVersion:
    """Write P1: baseline + objective passes + HUMAN-CONFIRMED evidence only (idempotent)."""
    observed = observed_successes(interview.turns)
    effective = effective_profile(interview.baseline_profile, observed)
    levels = dict(effective["levels"])
    provenance = dict(effective["provenance"])
    refs = [t.id for t in interview.turns if t.competency_id in observed and t.assessment_status == "DEMO_OBSERVED_LEVEL_1"]
    conflicts = set(effective["conflicts"])
    # Deterministic order: the latest reviewed confirmation wins for the same competency.
    confirmed = db.scalars(_select(EvidenceItem).where(EvidenceItem.interview_id == interview.id,
                                                       EvidenceItem.status == "CONFIRMED")
                           .order_by(EvidenceItem.reviewed_at, EvidenceItem.created_at, EvidenceItem.id)).all()
    for item in confirmed:
        if _is_conflict(interview.baseline_profile.get(item.competency_id), item.level):
            conflicts.add(item.competency_id)
        levels[item.competency_id] = item.level
        provenance[item.competency_id] = "HUMAN_REVIEW"
        refs.append(item.id)
    provenance["__conflicts__"] = sorted(conflicts)
    return create_profile_version(db, user_id=interview.user_id, kind="P1", interview_id=interview.id,
                                  levels=levels, provenance=provenance, evidence_refs=refs)
