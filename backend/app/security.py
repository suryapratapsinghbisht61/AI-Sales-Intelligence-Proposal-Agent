import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Membership, Organization, User, UserSession

COOKIE = "sp_session"
_hasher = PasswordHasher()

# Deterministic RBAC: action -> roles allowed. Checked server-side on every mutating route.
PERMISSIONS: dict[str, set[str]] = {
    "org.manage": {"owner", "admin"},
    "members.manage": {"owner", "admin"},
    "pricing.manage": {"owner", "admin"},
    "rubric.manage": {"owner", "admin", "sales_manager"},
    "documents.manage_any": {"owner", "admin", "sales_manager"},
    "approvals.decide": {"owner", "admin", "sales_manager"},
    "audit.read": {"owner", "admin", "sales_manager"},
}


def hash_password(pw: str) -> str:
    return _hasher.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, pw)
    except VerificationError:
        return False


def new_token() -> tuple[str, str]:
    """Returns (raw token for the client, sha256 hash for the DB)."""
    raw = secrets.token_urlsafe(32)
    return raw, token_hash(raw)


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_session(db: Session, user: User, org_id: uuid.UUID | None) -> str:
    raw, hashed = new_token()
    expires = datetime.now(UTC) + timedelta(days=get_settings().session_days)
    db.add(UserSession(token_hash=hashed, user_id=user.id, active_org_id=org_id, expires_at=expires))
    return raw


def get_session(
    db: Session = Depends(get_db), sp_session: str | None = Cookie(default=None)
) -> UserSession:
    if not sp_session:
        raise HTTPException(401, "Not signed in")
    s = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(sp_session)))
    if not s or s.expires_at < datetime.now(UTC):
        raise HTTPException(401, "Session expired")
    return s


def current_user(s: UserSession = Depends(get_session), db: Session = Depends(get_db)) -> User:
    return db.get(User, s.user_id)


@dataclass
class Ctx:
    """The authenticated user acting inside one organization. Every tenant query filters on org_id."""

    user: User
    org: Organization
    role: str

    @property
    def org_id(self) -> uuid.UUID:
        return self.org.id

    def can(self, action: str) -> bool:
        return self.role in PERMISSIONS[action]

    def require(self, action: str) -> None:
        if not self.can(action):
            raise HTTPException(403, "You do not have permission to do this")


def ctx(s: UserSession = Depends(get_session), db: Session = Depends(get_db)) -> Ctx:
    if not s.active_org_id:
        raise HTTPException(409, "No organization selected")
    m = db.scalar(select(Membership).where(Membership.org_id == s.active_org_id, Membership.user_id == s.user_id))
    if not m:  # membership revoked after the session picked this org
        raise HTTPException(403, "Not a member of this organization")
    return Ctx(user=db.get(User, s.user_id), org=db.get(Organization, s.active_org_id), role=m.role)


def get_owned(db: Session, model, id_: uuid.UUID, c: Ctx):
    """Load a tenant-owned row or 404. Never reveals whether the id exists in another org."""
    obj = db.get(model, id_)
    if obj is None or obj.org_id != c.org_id:
        raise HTTPException(404, "Not found")
    return obj
