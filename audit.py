from sqlalchemy.orm import Session

from . import models


def log_action(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    details: str | None = None,
    ip_address: str | None = None,
) -> models.AuditLog:
    """
    Writes one immutable audit row. Called from inside the same request/
    transaction as the state change it describes, so an audit entry and
    the change it documents are committed together.
    """
    entry = models.AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    return entry
