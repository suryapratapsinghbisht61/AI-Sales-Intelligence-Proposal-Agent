import csv
import io
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Membership, OutreachDraft, Prospect, ProspectSource, QualificationRubric, ResearchRun
from app.security import Ctx, ctx, get_owned
from app.services import jobs, qualification
from app.services.audit import audit
from app.services.webfetch import normalize_domain

router = APIRouter(tags=["prospects"])

FIELDS = ("name", "domain", "industry", "description", "location", "company_size", "contact_name", "contact_email",
          "source_url", "tags", "notes")


class ProspectIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    domain: str = Field(default="", max_length=300)
    industry: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=5000)
    location: str = Field(default="", max_length=200)
    company_size: str = Field(default="", max_length=100)
    contact_name: str = Field(default="", max_length=200)
    contact_email: str = Field(default="", max_length=320)
    source_url: str = Field(default="", max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    notes: str = Field(default="", max_length=20000)
    assigned_to: uuid.UUID | None = None

    @field_validator("domain")
    @classmethod
    def _domain(cls, v: str) -> str:
        return normalize_domain(v) if v.strip() else ""


class ProspectPatch(ProspectIn):
    name: str | None = Field(default=None, min_length=1, max_length=300)


def p_out(p: Prospect) -> dict:
    return {"id": str(p.id), **{f: getattr(p, f) for f in FIELDS},
            "assigned_to": str(p.assigned_to) if p.assigned_to else None, "research_status": p.research_status,
            "score": p.score, "last_researched_at": p.last_researched_at, "created_at": p.created_at,
            "latest_research_id": str(p.latest_research_id) if p.latest_research_id else None}


def _check_assignee(db: Session, c: Ctx, user_id) -> None:
    if user_id and not db.scalar(select(Membership).where(Membership.org_id == c.org_id,
                                                          Membership.user_id == user_id)):
        raise HTTPException(422, "Assignee is not a member of this organization")


def _duplicate(db: Session, c: Ctx, name: str, domain: str, exclude=None) -> Prospect | None:
    cond = func.lower(Prospect.name) == name.strip().lower()
    if domain:
        cond = or_(cond, Prospect.domain == domain)
    stmt = select(Prospect).where(Prospect.org_id == c.org_id, cond)
    if exclude:
        stmt = stmt.where(Prospect.id != exclude)
    return db.scalar(stmt.limit(1))


@router.post("/prospects", status_code=201)
def create(body: ProspectIn, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    if dup := _duplicate(db, c, body.name, body.domain):
        raise HTTPException(409, f"Possible duplicate of existing prospect '{dup.name}'")
    _check_assignee(db, c, body.assigned_to)
    p = Prospect(org_id=c.org_id, **body.model_dump())
    db.add(p)
    audit(db, c.org_id, c.user.id, "prospect.created", p)
    db.commit()
    return p_out(p)


SORTS = {"name": Prospect.name, "score": Prospect.score, "created_at": Prospect.created_at,
         "last_researched_at": Prospect.last_researched_at}


@router.get("/prospects")
def list_prospects(q: str = "", status: str = "", tag: str = "", sort: str = "created_at", desc: bool = True,
                   limit: int = 50, offset: int = 0, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    stmt = select(Prospect).where(Prospect.org_id == c.org_id)
    if q:
        stmt = stmt.where(or_(Prospect.name.ilike(f"%{q}%"), Prospect.domain.ilike(f"%{q}%"),
                              Prospect.industry.ilike(f"%{q}%")))
    if status:
        stmt = stmt.where(Prospect.research_status == status)
    if tag:
        stmt = stmt.where(Prospect.tags.any(tag))
    col = SORTS.get(sort, Prospect.created_at)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(col.desc().nulls_last() if desc else col.asc().nulls_last())
                      .limit(min(limit, 200)).offset(offset)).all()
    return {"items": [p_out(p) for p in rows], "total": total}


@router.get("/prospects/export")
def export(c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    buf = io.StringIO()
    w = csv.writer(buf)
    cols = [f for f in FIELDS if f != "notes"] + ["score", "research_status"]
    w.writerow(cols)
    for p in db.scalars(select(Prospect).where(Prospect.org_id == c.org_id).order_by(Prospect.name)):
        row = [";".join(p.tags) if f == "tags" else getattr(p, f) for f in cols]
        # neutralise spreadsheet formula injection
        w.writerow(["'" + v if isinstance(v, str) and v[:1] in "=+-@" else v for v in row])
    audit(db, c.org_id, c.user.id, "prospect.exported")
    db.commit()
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="prospects.csv"'})


@router.post("/prospects/import")
async def import_csv(file: UploadFile = File(...), c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    data = await file.read(2_000_001)
    if len(data) > 2_000_000:
        raise HTTPException(413, "CSV must be under 2 MB")
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    except UnicodeDecodeError:
        raise HTTPException(415, "CSV must be UTF-8") from None
    created, skipped, errors = 0, [], []
    for i, row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        try:
            body = ProspectIn(name=row.get("name", ""), domain=row.get("domain") or row.get("website", ""),
                              industry=row.get("industry", ""), location=row.get("location", ""),
                              company_size=row.get("company_size", ""), description=row.get("description", ""),
                              source_url=row.get("source_url", ""),
                              tags=[t for t in row.get("tags", "").split(";") if t])
        except ValueError as e:
            errors.append({"row": i, "error": str(e).splitlines()[0]})
            continue
        if dup := _duplicate(db, c, body.name, body.domain):
            skipped.append({"row": i, "name": body.name, "duplicate_of": dup.name})
            continue
        db.add(Prospect(org_id=c.org_id, **body.model_dump()))
        db.flush()
        created += 1
        if i > 5001:
            errors.append({"row": i, "error": "Import is limited to 5000 rows"})
            break
    audit(db, c.org_id, c.user.id, "prospect.imported", created=created)
    db.commit()
    return {"created": created, "skipped_duplicates": skipped, "errors": errors}


@router.get("/prospects/{pid}")
def get_prospect(pid: uuid.UUID, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    p = get_owned(db, Prospect, pid, c)
    out = p_out(p)
    out["research"] = research_out(db, db.get(ResearchRun, p.latest_research_id)) if p.latest_research_id else None
    out["drafts"] = [draft_out(d) for d in db.scalars(select(OutreachDraft).where(
        OutreachDraft.prospect_id == p.id).order_by(OutreachDraft.created_at.desc()))]
    return out


@router.patch("/prospects/{pid}")
def update_prospect(pid: uuid.UUID, body: ProspectPatch, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    p = get_owned(db, Prospect, pid, c)
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes or "domain" in changes:
        if dup := _duplicate(db, c, changes.get("name", p.name), changes.get("domain", p.domain), exclude=p.id):
            raise HTTPException(409, f"Possible duplicate of existing prospect '{dup.name}'")
    _check_assignee(db, c, changes.get("assigned_to"))
    for k, v in changes.items():
        if v is not None or k == "assigned_to":
            setattr(p, k, v)
    try:
        db.commit()
    except IntegrityError:
        raise HTTPException(409, "Another prospect already uses this domain") from None
    return p_out(p)


@router.delete("/prospects/{pid}", status_code=204)
def delete_prospect(pid: uuid.UUID, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    p = get_owned(db, Prospect, pid, c)
    audit(db, c.org_id, c.user.id, "prospect.deleted", p, name=p.name)
    db.delete(p)
    db.commit()


# --- research -----------------------------------------------------------------


class ResearchIn(BaseModel):
    target_offering: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=20000, description="Pasted public info about the company")
    force: bool = False


def research_out(db: Session, rr: ResearchRun) -> dict:
    sources = db.scalars(select(ProspectSource).where(ProspectSource.research_run_id == rr.id)).all()
    return {"id": str(rr.id), "prospect_id": str(rr.prospect_id), "status": rr.status, "error": rr.error,
            "facts": rr.facts, "needs": rr.needs, "unknowns": rr.unknowns, "qualification": rr.qualification,
            "score": rr.score, "rubric_version": rr.rubric_version, "recommended_offering": rr.recommended_offering,
            "value_proposition": rr.value_proposition, "warnings": rr.warnings, "created_at": rr.created_at,
            "sources": [{"url": s.url, "title": s.title, "retrieved_at": s.retrieved_at} for s in sources]}


@router.post("/prospects/{pid}/research", status_code=202)
def start_research(pid: uuid.UUID, body: ResearchIn, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    p = get_owned(db, Prospect, pid, c)
    if p.research_status in ("queued", "running"):
        raise HTTPException(409, "Research is already in progress for this prospect")
    fresh = datetime.now(UTC) - timedelta(days=get_settings().research_cache_days)
    if not body.force and p.latest_research_id and p.last_researched_at and p.last_researched_at > fresh:
        return {"cached": True, "research": research_out(db, db.get(ResearchRun, p.latest_research_id))}
    if not p.domain and not body.notes.strip():
        raise HTTPException(422, "Add the prospect's website or paste notes about the company to research it")
    rr = ResearchRun(org_id=c.org_id, prospect_id=p.id, user_id=c.user.id, inputs=body.model_dump(exclude={"force"}))
    db.add(rr)
    db.flush()
    p.research_status = "queued"
    jobs.enqueue(db, c.org_id, "research", research_run_id=rr.id)
    audit(db, c.org_id, c.user.id, "research.started", p)
    db.commit()
    return {"cached": False, "research": research_out(db, rr)}


@router.get("/research/{run_id}")
def get_research(run_id: uuid.UUID, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    return research_out(db, get_owned(db, ResearchRun, run_id, c))


# --- outreach drafts ----------------------------------------------------------


def draft_out(d: OutreachDraft) -> dict:
    return {"id": str(d.id), "kind": d.kind, "subject": d.subject, "body": d.body, "rationale": d.rationale,
            "status": d.status, "created_at": d.created_at, "updated_at": d.updated_at}


class DraftPatch(BaseModel):
    subject: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, min_length=1, max_length=10000)
    status: Literal["draft", "sent"] | None = None


@router.patch("/drafts/{draft_id}")
def update_draft(draft_id: uuid.UUID, body: DraftPatch, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    d = get_owned(db, OutreachDraft, draft_id, c)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(d, k, v)
    if body.status == "sent":
        audit(db, c.org_id, c.user.id, "outreach.marked_sent", d)
    db.commit()
    return draft_out(d)


# --- qualification rubric -----------------------------------------------------


class Criterion(BaseModel):
    key: str = Field(pattern="^[a-z0-9_]{2,40}$")
    label: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    weight: int = Field(ge=0, le=100)


class RubricIn(BaseModel):
    criteria: list[Criterion] = Field(min_length=1, max_length=15)


@router.get("/rubric")
def get_rubric(c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    r = qualification.active_rubric(db, c.org_id)
    db.commit()
    return {"version": r.version, "criteria": r.criteria}


@router.put("/rubric")
def set_rubric(body: RubricIn, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    """Each change creates a new version so past scores stay interpretable."""
    c.require("rubric.manage")
    if len({x.key for x in body.criteria}) != len(body.criteria):
        raise HTTPException(422, "Criterion keys must be unique")
    if sum(x.weight for x in body.criteria) == 0:
        raise HTTPException(422, "At least one criterion needs a weight above zero")
    current = qualification.active_rubric(db, c.org_id)
    r = QualificationRubric(org_id=c.org_id, version=current.version + 1, created_by=c.user.id,
                            criteria=[x.model_dump() for x in body.criteria])
    db.add(r)
    audit(db, c.org_id, c.user.id, "rubric.updated", r, version=r.version)
    db.commit()
    return {"version": r.version, "criteria": r.criteria}
