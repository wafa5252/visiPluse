from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_roles
from ..models import UserRole

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[schemas.AuditLogOut])
def list_audit_log(
    entity_type: str | None = None,
    user_id: int | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles(UserRole.ADMIN)),
):
    """
    Admin-only. Every login, approval, ticket change, and device edit in the
    system is recorded here for compliance review (NCA ECC-style audit trail).
    """
    query = db.query(models.AuditLog)
    if entity_type:
        query = query.filter(models.AuditLog.entity_type == entity_type)
    if user_id:
        query = query.filter(models.AuditLog.user_id == user_id)
    return query.order_by(models.AuditLog.timestamp.desc()).limit(min(limit, 1000)).all()
