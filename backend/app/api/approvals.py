import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (ApprovalRequest, AuditLog, Document, ModelUsageEvent, Proposal, Prospect, ResearchRun, User,
                        WorkflowRun, Conversation)
from app.security import Ctx, ctx, get_owned
from app.services.audit import audit

router = APIRouter(tags=["approvals", "analytics"])


def approval_out(db: Session, a: ApprovalRequest) -> dict:
    users = {u.id: u.email for u in db.scalars(select(User).where(User.id.in_(
        [x for x in (a.requested_by, a.decided_by) if x])))}
    return {"id": str(a.id), "kind": a.kind, "target_type": a.target_type, "target_id": str(a.target_id),
            "target_version": a.target_version, "status": a.status, "summary": a.summary,
            "requested_by": users.get(a.requested_by), "decided_by": users.get(a.decided_by),
            "decided_at": a.decided_at, "comment": a.comment, "created_at": a.created_at}


@router.get("/approvals")
def list_approvals(status: str = "", c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    stmt = select(ApprovalRequest).where(ApprovalRequest.org_id == c.org_id)
    if status:
        stmt = stmt.where(ApprovalRequest.status == status)
    return [approval_out(db, a) for a in db.scalars(stmt.order_by(ApprovalRequest.created_at.desc()).limit(200))]


@router.get("/approvals/{aid}")
def get_approval(aid: uuid.UUID, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    a = get_owned(db, ApprovalRequest, aid, c)
    out = approval_out(db, a)
    out["history"] = [{"action": l.action, "at": l.created_at, "detail": l.detail} for l in db.scalars(
        select(AuditLog).where(AuditLog.org_id == c.org_id, AuditLog.target_id == str(a.target_id))
        .order_by(AuditLog.created_at))]
    return out


class Decision(BaseModel):
    comment: str = Field(default="", max_length=5000)


OUTCOME = {"approve": ("approved", "approved"), "reject": ("rejected", "rejected"),
           "request-changes": ("changes_requested", "changes_requested")}


@router.post("/approvals/{aid}/{action}")
def decide(aid: uuid.UUID, action: str, body: Decision, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    if action not in OUTCOME:
        raise HTTPException(404, "Not found")
    c.require("approvals.decide")
    # lock the row so two approvers cannot both decide (replayed/duplicate requests are rejected below)
    a = db.scalar(select(ApprovalRequest).where(ApprovalRequest.id == aid, ApprovalRequest.org_id == c.org_id)
                  .with_for_update())
    if not a:
        raise HTTPException(404, "Not found")
    if a.status != "pending":
        raise HTTPException(409, f"This request was already {a.status.replace('_', ' ')}")
    if a.requested_by == c.user.id and c.role != "owner":
        raise HTTPException(403, "You cannot approve your own request")
    if action != "approve" and not body.comment.strip():
        raise HTTPException(422, "Please explain what needs to change")
    p = db.get(Proposal, a.target_id)
    if p is None or p.org_id != c.org_id:
        raise HTTPException(409, "The proposal no longer exists")
    if p.current_version != a.target_version:  # revalidate: approve exactly what was reviewed
        raise HTTPException(409, "The proposal changed after it was submitted; it must be resubmitted")
    a.status, p.status = OUTCOME[action]
    a.decided_by, a.decided_at, a.comment = c.user.id, datetime.now(UTC), body.comment.strip()
    audit(db, c.org_id, c.user.id, f"proposal.{a.status}", p, version=a.target_version, comment=a.comment)
    db.commit()
    return approval_out(db, a)


# --- analytics & operations ---------------------------------------------------


def _since(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=max(1, min(days, 365)))


@router.get("/analytics/overview")
def overview(days: int = 30, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    since, o = _since(days), c.org_id

    def count(model, *where):
        return db.scalar(select(func.count()).select_from(model).where(model.org_id == o, *where))

    runs = dict(db.execute(select(WorkflowRun.status, func.count()).where(
        WorkflowRun.org_id == o, WorkflowRun.created_at >= since).group_by(WorkflowRun.status)).all())
    usage = db.execute(select(func.coalesce(func.sum(ModelUsageEvent.input_tokens), 0),
                              func.coalesce(func.sum(ModelUsageEvent.output_tokens), 0),
                              func.sum(ModelUsageEvent.est_cost_usd))
                       .where(ModelUsageEvent.org_id == o, ModelUsageEvent.created_at >= since)).one()
    daily = db.execute(select(func.date_trunc("day", WorkflowRun.created_at).label("d"), WorkflowRun.kind, func.count())
                       .where(WorkflowRun.org_id == o, WorkflowRun.created_at >= since)
                       .group_by("d", WorkflowRun.kind).order_by("d")).all()
    by_day: dict = {}
    for d, kind, n in daily:
        by_day.setdefault(d.date().isoformat(), {"date": d.date().isoformat()})[kind] = n
    return {
        "documents_indexed": count(Document, Document.status == "ready"),
        "documents_total": count(Document),
        "questions_asked": count(WorkflowRun, WorkflowRun.kind == "qa", WorkflowRun.created_at >= since),
        "conversations": count(Conversation),
        "prospects": count(Prospect),
        "prospects_researched": count(ResearchRun, ResearchRun.status == "done", ResearchRun.created_at >= since),
        "proposals_generated": count(Proposal, Proposal.created_at >= since),
        "pending_approvals": count(ApprovalRequest, ApprovalRequest.status == "pending"),
        "workflow_succeeded": runs.get("succeeded", 0),
        "workflow_failed": runs.get("failed", 0),
        "tokens_in": usage[0], "tokens_out": usage[1],
        "est_cost_usd": float(usage[2]) if usage[2] is not None else None,
        "daily": list(by_day.values()),
    }


@router.get("/usage")
def usage(days: int = 30, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    rows = db.execute(select(ModelUsageEvent.model, ModelUsageEvent.purpose, func.count(),
                             func.sum(ModelUsageEvent.input_tokens), func.sum(ModelUsageEvent.output_tokens),
                             func.sum(ModelUsageEvent.est_cost_usd))
                      .where(ModelUsageEvent.org_id == c.org_id, ModelUsageEvent.created_at >= _since(days))
                      .group_by(ModelUsageEvent.model, ModelUsageEvent.purpose)).all()
    failures = db.scalars(select(WorkflowRun).where(WorkflowRun.org_id == c.org_id, WorkflowRun.status == "failed")
                          .order_by(WorkflowRun.created_at.desc()).limit(20)).all()
    return {
        "by_model": [{"model": m, "purpose": p, "calls": n, "input_tokens": ti or 0, "output_tokens": to or 0,
                      "est_cost_usd": float(cost) if cost is not None else None} for m, p, n, ti, to, cost in rows],
        "recent_failures": [{"id": str(w.id), "kind": w.kind, "error": w.error, "at": w.created_at} for w in failures],
        "monthly_token_budget": c.org.monthly_token_budget,
    }


@router.get("/activity")
def activity(limit: int = 50, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    rows = db.execute(select(AuditLog, User.email).outerjoin(User, User.id == AuditLog.user_id)
                      .where(AuditLog.org_id == c.org_id).order_by(AuditLog.created_at.desc())
                      .limit(min(limit, 200))).all()
    return [{"id": str(l.id), "action": l.action, "user": email, "target_type": l.target_type,
             "target_id": l.target_id, "detail": l.detail if c.can("audit.read") else {}, "at": l.created_at}
            for l, email in rows]
