import io
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ApprovalRequest, PriceItem, Proposal, ProposalVersion, Prospect, User
from app.security import Ctx, ctx, get_owned
from app.services import jobs
from app.services.audit import audit
from app.workflows.proposal import LLM_SECTIONS, ProposalInputs, compute_pricing, validate_sections

router = APIRouter(tags=["proposals"])

# --- approved price list ------------------------------------------------------


class PriceItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=2000)
    unit: str = Field(default="unit", max_length=60)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    currency: str = Field(pattern="^[A-Z]{3}$")
    active: bool = True


def price_out(i: PriceItem) -> dict:
    return {"id": str(i.id), "name": i.name, "description": i.description, "unit": i.unit,
            "unit_price": str(i.unit_price), "currency": i.currency, "active": i.active}


@router.get("/price-items")
def list_prices(c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    return [price_out(i) for i in db.scalars(select(PriceItem).where(PriceItem.org_id == c.org_id)
                                             .order_by(PriceItem.name))]


@router.post("/price-items", status_code=201)
def create_price(body: PriceItemIn, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    c.require("pricing.manage")
    i = PriceItem(org_id=c.org_id, **body.model_dump())
    db.add(i)
    audit(db, c.org_id, c.user.id, "price_item.created", i, name=i.name, unit_price=str(i.unit_price))
    db.commit()
    return price_out(i)


@router.put("/price-items/{item_id}")
def update_price(item_id: uuid.UUID, body: PriceItemIn, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    c.require("pricing.manage")
    i = get_owned(db, PriceItem, item_id, c)
    audit(db, c.org_id, c.user.id, "price_item.updated", i, old_price=str(i.unit_price), new_price=str(body.unit_price))
    for k, v in body.model_dump().items():
        setattr(i, k, v)
    db.commit()
    return price_out(i)


# --- proposals ----------------------------------------------------------------


def proposal_out(db: Session, p: Proposal, with_version: bool = True) -> dict:
    out = {"id": str(p.id), "prospect_id": str(p.prospect_id), "title": p.title, "status": p.status,
           "current_version": p.current_version, "inputs": p.inputs, "error": p.error,
           "created_at": p.created_at, "updated_at": p.updated_at}
    prospect = db.get(Prospect, p.prospect_id)
    out["prospect_name"] = prospect.name if prospect else ""
    if with_version and p.current_version:
        out["version"] = version_out(_version(db, p, p.current_version))
    return out


def version_out(v: ProposalVersion) -> dict:
    return {"version": v.version, "sections": v.sections, "pricing": v.pricing, "warnings": v.warnings,
            "note": v.note, "created_at": v.created_at}


def _version(db: Session, p: Proposal, n: int) -> ProposalVersion:
    v = db.scalar(select(ProposalVersion).where(ProposalVersion.proposal_id == p.id, ProposalVersion.version == n))
    if not v:
        raise HTTPException(404, "Version not found")
    return v


@router.post("/proposals", status_code=202)
def create_proposal(body: ProposalInputs, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    prospect = get_owned(db, Prospect, body.prospect_id, c)
    try:
        compute_pricing(db, c.org_id, body.price_lines, body.currency)  # fail fast on bad price lines
    except (ValueError, ArithmeticError, KeyError) as e:
        raise HTTPException(422, str(e)) from None
    p = Proposal(org_id=c.org_id, prospect_id=prospect.id, title=body.title, created_by=c.user.id,
                 inputs=body.model_dump(mode="json"))
    db.add(p)
    db.flush()
    jobs.enqueue(db, c.org_id, "proposal", proposal_id=p.id, version=1, user_id=c.user.id)
    audit(db, c.org_id, c.user.id, "proposal.created", p)
    db.commit()
    return proposal_out(db, p)


@router.get("/proposals")
def list_proposals(status: str = "", c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    stmt = select(Proposal).where(Proposal.org_id == c.org_id)
    if status:
        stmt = stmt.where(Proposal.status == status)
    return [proposal_out(db, p, with_version=False) for p in db.scalars(stmt.order_by(Proposal.updated_at.desc()))]


@router.get("/proposals/{pid}")
def get_proposal(pid: uuid.UUID, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    return proposal_out(db, get_owned(db, Proposal, pid, c))


@router.get("/proposals/{pid}/versions")
def list_versions(pid: uuid.UUID, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    p = get_owned(db, Proposal, pid, c)
    rows = db.execute(select(ProposalVersion, User.email).outerjoin(User, User.id == ProposalVersion.created_by)
                      .where(ProposalVersion.proposal_id == p.id).order_by(ProposalVersion.version.desc())).all()
    return [{"version": v.version, "note": v.note, "created_at": v.created_at, "created_by": email}
            for v, email in rows]


@router.get("/proposals/{pid}/versions/{n}")
def get_version(pid: uuid.UUID, n: int, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    return version_out(_version(db, get_owned(db, Proposal, pid, c), n))


EDITABLE = ("draft", "changes_requested", "rejected")


def _editable(p: Proposal) -> None:
    if p.status not in EDITABLE:
        raise HTTPException(409, f"A proposal that is '{p.status.replace('_', ' ')}' cannot be edited")


class SectionEdit(BaseModel):
    key: str
    content: str = Field(max_length=50000)


class ProposalEdit(BaseModel):
    base_version: int  # optimistic concurrency: reject edits made against a stale version
    sections: list[SectionEdit]
    note: str = Field(default="Manual edit", max_length=300)


@router.patch("/proposals/{pid}")
def edit_proposal(pid: uuid.UUID, body: ProposalEdit, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    p = get_owned(db, Proposal, pid, c)
    _editable(p)
    stale = HTTPException(409, "This proposal changed since you opened it. Reload to see the latest version.")
    if body.base_version != p.current_version:
        raise stale
    cur = _version(db, p, p.current_version)
    edits = {e.key: e.content for e in body.sections}
    sections = [{**s, "content": edits.get(s["key"], s["content"])} for s in cur.sections]
    sections = validate_sections(sections, set(), cur.pricing)
    n = p.current_version + 1
    db.add(ProposalVersion(org_id=c.org_id, proposal_id=p.id, version=n, sections=sections, pricing=cur.pricing,
                           warnings=cur.warnings, note=body.note, created_by=c.user.id))
    p.current_version, p.status = n, "draft"
    try:
        db.commit()
    except IntegrityError:
        raise stale from None
    return proposal_out(db, p)


class RegenIn(BaseModel):
    section: Literal[tuple(LLM_SECTIONS)] | None = None  # type: ignore[valid-type]


@router.post("/proposals/{pid}/regenerate", status_code=202)
def regenerate(pid: uuid.UUID, body: RegenIn, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    p = get_owned(db, Proposal, pid, c)
    if p.status != "failed":
        _editable(p)
    if body.section and not p.current_version:
        raise HTTPException(409, "Generate the full proposal first")
    p.status = "generating"
    jobs.enqueue(db, c.org_id, "proposal", proposal_id=p.id, version=p.current_version + 1, user_id=c.user.id,
                 section=body.section or "")
    db.commit()
    return proposal_out(db, p)


@router.post("/proposals/{pid}/submit")
def submit(pid: uuid.UUID, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    p = get_owned(db, Proposal, pid, c)
    _editable(p)
    if not p.current_version:
        raise HTTPException(409, "Nothing to submit yet")
    v = _version(db, p, p.current_version)
    flags = [f for s in v.sections for f in s.get("flags", [])]
    a = ApprovalRequest(org_id=c.org_id, kind="proposal", target_type="proposal", target_id=p.id,
                        target_version=p.current_version, requested_by=c.user.id,
                        summary={"title": p.title, "total": v.pricing.get("total"),
                                 "currency": v.pricing.get("currency"), "flags": flags, "warnings": v.warnings})
    db.add(a)
    p.status = "pending_approval"
    audit(db, c.org_id, c.user.id, "proposal.submitted", p, version=p.current_version)
    try:
        db.commit()
    except IntegrityError:
        raise HTTPException(409, "This proposal already has a pending approval") from None
    return {"approval_id": str(a.id)}


def _md_to_docx(doc, text: str) -> None:
    for block in text.split("\n"):
        line = block.strip()
        if not line or set(line) <= set("|-: "):
            continue
        if line.startswith("|"):
            doc.add_paragraph("   ".join(c.strip() for c in line.strip("|").split("|")))
        elif line.startswith(("- ", "* ")):
            doc.add_paragraph(line[2:].replace("**", ""), style="List Bullet")
        elif m := re.match(r"^#{1,6}\s+(.*)", line):
            doc.add_heading(m.group(1), level=3)
        else:
            doc.add_paragraph(line.replace("**", ""))


@router.post("/proposals/{pid}/export")
def export(pid: uuid.UUID, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    import docx

    p = get_owned(db, Proposal, pid, c)
    if not p.current_version:
        raise HTTPException(409, "Nothing to export yet")
    v = _version(db, p, p.current_version)
    d = docx.Document()
    if p.status != "approved":
        d.add_paragraph(f"DRAFT - not approved (status: {p.status.replace('_', ' ')}, version {v.version})")
    d.add_heading(p.title, level=0)
    d.add_paragraph(f"Prepared for {db.get(Prospect, p.prospect_id).name} by {c.org.name} - "
                    f"{datetime.now(UTC):%d %B %Y}")
    for s in v.sections:
        d.add_heading(s["title"], level=1)
        _md_to_docx(d, s["content"])
    buf = io.BytesIO()
    d.save(buf)
    audit(db, c.org_id, c.user.id, "proposal.exported", p, version=v.version, approved=p.status == "approved")
    db.commit()
    name = re.sub(r"[^A-Za-z0-9_-]+", "-", p.title)[:80] or "proposal"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{name}-v{v.version}.docx"'},
    )
