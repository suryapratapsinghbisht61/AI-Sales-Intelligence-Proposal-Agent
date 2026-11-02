"""Deterministic scoring. The model only supplies per-criterion ratings with quoted evidence; code does the maths."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import QualificationRubric

DEFAULT_CRITERIA = [
    {"key": "industry_fit", "label": "Industry fit", "weight": 20,
     "description": "The prospect operates in an industry we target."},
    {"key": "service_relevance", "label": "Service relevance", "weight": 25,
     "description": "The prospect's business plausibly needs one of our offerings."},
    {"key": "size_fit", "label": "Company size fit", "weight": 15,
     "description": "The prospect's size matches our target customer profile."},
    {"key": "geography_fit", "label": "Geography fit", "weight": 10,
     "description": "The prospect operates in our target markets."},
    {"key": "evidence_of_need", "label": "Evidence of need", "weight": 20,
     "description": "Public evidence of an initiative or problem our offerings address."},
    {"key": "capability_match", "label": "Capability match", "weight": 10,
     "description": "Their requirements are within what we can deliver."},
]

RATING_VALUE = {"strong": 1.0, "partial": 0.5, "none": 0.0, "unknown": 0.0}


def active_rubric(db: Session, org_id) -> QualificationRubric:
    r = db.scalar(
        select(QualificationRubric)
        .where(QualificationRubric.org_id == org_id)
        .order_by(QualificationRubric.version.desc())
        .limit(1)
    )
    if r is None:
        r = QualificationRubric(org_id=org_id, version=1, criteria=DEFAULT_CRITERIA)
        db.add(r)
        db.flush()
    return r


def score(criteria: list[dict], ratings: dict[str, str]) -> dict:
    """ratings: key -> strong|partial|none|unknown. Unknowns score 0 and are reported, never guessed."""
    total_w = sum(c["weight"] for c in criteria) or 1
    got = sum(c["weight"] * RATING_VALUE.get(ratings.get(c["key"], "unknown"), 0) for c in criteria)
    unknown = [c["key"] for c in criteria if ratings.get(c["key"], "unknown") == "unknown"]
    known_w = sum(c["weight"] for c in criteria if c["key"] not in unknown)
    disqualified = [c["key"] for c in criteria if ratings.get(c["key"]) == "none"]
    value = round(100 * got / total_w)
    if known_w / total_w < 0.5:
        next_step = "Gather more information before outreach: over half of the criteria are unverified."
    elif value >= 70:
        next_step = "Good fit on available evidence: review the outreach draft and reach out."
    elif value >= 40:
        next_step = "Partial fit: validate the open criteria in a discovery call."
    else:
        next_step = "Weak fit on available evidence: deprioritise unless new information appears."
    return {
        "score": value,
        "evidence_coverage": round(100 * known_w / total_w),
        "unknown": unknown,
        "disqualifiers": disqualified,
        "next_step": next_step,
    }


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def quote_in(quote: str, text: str) -> bool:
    q = _norm(quote)
    return len(q) >= 12 and q in _norm(text)


if __name__ == "__main__":
    crit = DEFAULT_CRITERIA
    r = score(crit, {c["key"]: "strong" for c in crit})
    assert r["score"] == 100 and r["unknown"] == [], r
    r = score(crit, {"industry_fit": "strong", "service_relevance": "partial"})
    assert r["score"] == round(100 * (20 + 12.5) / 100) and len(r["unknown"]) == 4, r
    assert "more information" in r["next_step"]
    assert quote_in("Cloud  migration services", "We offer cloud migration services worldwide")
    assert not quote_in("short", "short")
    print("ok")
