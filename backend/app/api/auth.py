import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Invitation, Membership, Organization, PasswordReset, User, UserSession
from app.security import (
    COOKIE,
    PERMISSIONS,
    create_session,
    current_user,
    get_session,
    hash_password,
    new_token,
    token_hash,
    verify_password,
)
from app.services.audit import audit

router = APIRouter(tags=["auth"])
log = logging.getLogger("salespilot.auth")
# verifying against a real hash keeps login timing the same whether or not the email exists
_DUMMY_HASH = hash_password("timing-equaliser")


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)


class Signup(Credentials):
    name: str = Field(default="", max_length=200)


def _set_cookie(resp: Response, raw: str) -> None:
    s = get_settings()
    resp.set_cookie(COOKIE, raw, httponly=True, secure=s.cookie_secure, samesite="lax",
                    max_age=s.session_days * 86400, path="/")


def _first_org(db: Session, user_id) -> uuid.UUID | None:
    return db.scalar(select(Membership.org_id).where(Membership.user_id == user_id).order_by(Membership.created_at))


@router.post("/auth/signup", status_code=201)
def signup(body: Signup, resp: Response, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists")
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    _set_cookie(resp, create_session(db, user, None))
    audit(db, None, user.id, "user.signup")
    db.commit()
    return {"id": str(user.id)}


@router.post("/auth/login")
def login(body: Credentials, resp: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not verify_password(body.password, user.password_hash if user else _DUMMY_HASH) or not user:
        raise HTTPException(401, "Incorrect email or password")
    _set_cookie(resp, create_session(db, user, _first_org(db, user.id)))
    audit(db, None, user.id, "user.login")
    db.commit()
    return {"ok": True}


@router.post("/auth/logout")
def logout(resp: Response, s: UserSession = Depends(get_session), db: Session = Depends(get_db)):
    db.delete(s)
    db.commit()
    resp.delete_cookie(COOKIE, path="/")
    return {"ok": True}


class ResetRequest(BaseModel):
    email: EmailStr


@router.post("/auth/password-reset/request", status_code=202)
def reset_request(body: ResetRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user:
        raw, hashed = new_token()
        db.add(PasswordReset(token_hash=hashed, user_id=user.id, expires_at=datetime.now(UTC) + timedelta(hours=1)))
        db.commit()
        link = f"{get_settings().frontend_origin}/reset-password?token={raw}"
        if get_settings().environment == "development":
            # shortcut: no email provider is wired yet; the link is logged in development only
            log.warning("Password reset link for %s: %s", user.email, link)
    return {"ok": True}  # same response whether or not the account exists


class ResetConfirm(BaseModel):
    token: str
    password: str = Field(min_length=10, max_length=200)


@router.post("/auth/password-reset/confirm")
def reset_confirm(body: ResetConfirm, db: Session = Depends(get_db)):
    pr = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == token_hash(body.token)))
    if not pr or pr.used_at or pr.expires_at < datetime.now(UTC):
        raise HTTPException(400, "This reset link is invalid or has expired")
    user = db.get(User, pr.user_id)
    user.password_hash = hash_password(body.password)
    pr.used_at = datetime.now(UTC)
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))  # sign out everywhere
    audit(db, None, user.id, "user.password_reset")
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(s: UserSession = Depends(get_session), user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Organization, Membership.role).join(Membership, Membership.org_id == Organization.id)
        .where(Membership.user_id == user.id).order_by(Organization.name)
    ).all()
    orgs = [{"id": str(o.id), "name": o.name, "role": r, "onboarding_completed": o.onboarding_completed} for o, r in rows]
    active = next((o for o in orgs if o["id"] == str(s.active_org_id)), None)
    perms = sorted(a for a, roles in PERMISSIONS.items() if active and active["role"] in roles)
    return {"user": {"id": str(user.id), "email": user.email, "name": user.name},
            "organizations": orgs, "active_organization": active, "permissions": perms}


class SwitchOrg(BaseModel):
    organization_id: uuid.UUID


@router.post("/session/organization")
def switch_org(body: SwitchOrg, s: UserSession = Depends(get_session), db: Session = Depends(get_db)):
    if not db.scalar(select(Membership).where(Membership.org_id == body.organization_id,
                                              Membership.user_id == s.user_id)):
        raise HTTPException(404, "Organization not found")
    s.active_org_id = body.organization_id
    db.commit()
    return {"ok": True}


class AcceptInvite(BaseModel):
    token: str


@router.post("/invitations/accept")
def accept_invite(body: AcceptInvite, s: UserSession = Depends(get_session), user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    inv = db.scalar(select(Invitation).where(Invitation.token_hash == token_hash(body.token)))
    if not inv or inv.accepted_at or inv.expires_at < datetime.now(UTC):
        raise HTTPException(400, "This invitation is invalid or has expired")
    if inv.email != user.email:
        raise HTTPException(403, "This invitation was sent to a different email address")
    if not db.scalar(select(Membership).where(Membership.org_id == inv.org_id, Membership.user_id == user.id)):
        db.add(Membership(org_id=inv.org_id, user_id=user.id, role=inv.role))
    inv.accepted_at = datetime.now(UTC)
    s.active_org_id = inv.org_id
    audit(db, inv.org_id, user.id, "invitation.accepted", inv)
    db.commit()
    return {"ok": True}
