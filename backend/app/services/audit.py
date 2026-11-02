import uuid

from sqlalchemy.orm import Session

from app.models import AuditLog


def audit(db: Session, org_id, user_id, action: str, target=None, **detail) -> None:
    """Append-only audit record; caller commits. Never pass secrets or document bodies in detail."""
    db.add(
        AuditLog(
            org_id=org_id,
            user_id=user_id,
            action=action,
            target_type=type(target).__name__.lower() if target is not None else "",
            target_id=str(getattr(target, "id", "")) if target is not None else "",
            detail={k: str(v) if isinstance(v, uuid.UUID) else v for k, v in detail.items()},
        )
    )
