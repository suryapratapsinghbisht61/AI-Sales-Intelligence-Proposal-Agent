import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Invitation, Membership, Organization, User, UserSession
from app.security import Ctx, ctx, current_user, get_session, new_token
from app.services.audit import audit

router = APIRouter(tags=["organizations"])
Role = Literal["owner", "admin", "sales_manager", "sales_rep"]


class OrgFields(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    website: str | None = Field(default=None, max_length=500)
    industry: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    offerings: str | None = Field(default=None, max_length=5000)
    target_customer: str | None = Field(default=None, max_length=5000)
    target_markets: str | None = Field(default=None, max_length=2000)
    team_size: int | None = Field(default=None, ge=1, le=100000)
    currency: str | None = Field(default=None, pattern="^[A-Z]{3}$")
    timezone: str | None = Field(default=None, max_length=64)
    onboarding_completed: bool | None = None


class OrgCreate(OrgFields):
    name: str = Field(min_length=1, max_length=200)


FIELDS = list(OrgFields.model_fields)


def org_out(o: Organization) -> dict:
    return {"id": str(o.id), **{f: getattr(o, f) for f in FIELDS}}


@router.post("/organizations", status_code=201)
def create_org(body: OrgCreate, s: UserSession = Depends(get_session), user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    org = Organization(**body.model_dump(exclude_none=True))
    db.add(org)
    db.flush()
    db.add(Membership(org_id=org.id, user_id=user.id, role="owner"))
    s.active_org_id = org.id
    audit(db, org.id, user.id, "organization.created", org)
    db.commit()
    return org_out(org)


@router.get("/organizations/current")
def get_org(c: Ctx = Depends(ctx)):
    return org_out(c.org)


@router.patch("/organizations/current")
def update_org(body: OrgFields, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    c.require("org.manage")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        if v is not None:
            setattr(c.org, k, v)
    db.add(c.org)
    audit(db, c.org_id, c.user.id, "organization.updated", c.org, fields=sorted(changes))
    db.commit()
    return org_out(c.org)


@router.get("/members")
def list_members(c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    rows = db.execute(select(Membership, User).join(User, User.id == Membership.user_id)
                      .where(Membership.org_id == c.org_id).order_by(User.email)).all()
    return [{"id": str(m.id), "user_id": str(u.id), "email": u.email, "name": u.name, "role": m.role,
             "joined_at": m.created_at} for m, u in rows]


class RoleChange(BaseModel):
    role: Role


def _owner_count(db: Session, org_id) -> int:
    return db.scalar(select(func.count()).where(Membership.org_id == org_id, Membership.role == "owner"))


@router.patch("/members/{member_id}")
def change_role(member_id: uuid.UUID, body: RoleChange, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    c.require("members.manage")
    m = db.get(Membership, member_id)
    if not m or m.org_id != c.org_id:
        raise HTTPException(404, "Not found")
    if "owner" in (m.role, body.role) and c.role != "owner":
        raise HTTPException(403, "Only owners can grant or remove the owner role")
    if m.role == "owner" and body.role != "owner" and _owner_count(db, c.org_id) == 1:
        raise HTTPException(409, "An organization must keep at least one owner")
    audit(db, c.org_id, c.user.id, "member.role_changed", m, old=m.role, new=body.role)
    m.role = body.role
    db.commit()
    return {"ok": True}


@router.delete("/members/{member_id}", status_code=204)
def remove_member(member_id: uuid.UUID, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    c.require("members.manage")
    m = db.get(Membership, member_id)
    if not m or m.org_id != c.org_id:
        raise HTTPException(404, "Not found")
    if m.role == "owner" and (c.role != "owner" or _owner_count(db, c.org_id) == 1):
        raise HTTPException(409, "Cannot remove this owner")
    audit(db, c.org_id, c.user.id, "member.removed", m, user_id=m.user_id)
    db.delete(m)
    db.commit()


class InviteIn(BaseModel):
    email: EmailStr
    role: Role = "sales_rep"


@router.post("/invitations", status_code=201)
def invite(body: InviteIn, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    c.require("members.manage")
    if body.role == "owner" and c.role != "owner":
        raise HTTPException(403, "Only owners can invite owners")
    raw, hashed = new_token()
    inv = Invitation(org_id=c.org_id, email=body.email.lower(), role=body.role, token_hash=hashed,
                     invited_by=c.user.id, expires_at=datetime.now(UTC) + timedelta(days=7))
    db.add(inv)
    audit(db, c.org_id, c.user.id, "invitation.created", inv, email=inv.email, role=inv.role)
    db.commit()
    # No email provider is configured, so the inviter shares this link themselves.
    return {"id": str(inv.id), "link": f"{get_settings().frontend_origin}/invite?token={raw}"}


@router.get("/invitations")
def list_invitations(c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    c.require("members.manage")
    rows = db.scalars(select(Invitation).where(Invitation.org_id == c.org_id, Invitation.accepted_at.is_(None),
                                               Invitation.expires_at > datetime.now(UTC))).all()
    return [{"id": str(i.id), "email": i.email, "role": i.role, "expires_at": i.expires_at} for i in rows]


@router.delete("/invitations/{inv_id}", status_code=204)
def revoke_invitation(inv_id: uuid.UUID, c: Ctx = Depends(ctx), db: Session = Depends(get_db)):
    c.require("members.manage")
    inv = db.get(Invitation, inv_id)
    if not inv or inv.org_id != c.org_id:
        raise HTTPException(404, "Not found")
    db.delete(inv)
    db.commit()
