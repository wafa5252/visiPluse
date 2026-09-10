from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_roles, get_current_user, client_ip
from ..audit import log_action
from ..models import UserRole

router = APIRouter(prefix="/security-logs", tags=["security"])


@router.post("", response_model=schemas.SecurityLogOut, status_code=status.HTTP_201_CREATED)
def create_security_log(
    payload: schemas.SecurityLogCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles(UserRole.ADMIN, UserRole.MAINTENANCE_TECH)),
):
    device = db.get(models.Device, payload.device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    entry = models.SoftwareSecurityLog(**payload.model_dump())
    db.add(entry)
    db.flush()

    log_action(
        db, user_id=user.user_id, action="SECURITY_LOG_CREATED", entity_type="SoftwareSecurityLog",
        entity_id=entry.log_id, details=f"severity={payload.severity_level.value}",
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(entry)
    return entry


@router.get("", response_model=list[schemas.SecurityLogOut])
def list_security_logs(
    device_id: int | None = None,
    severity: models.SeverityLevel | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    query = db.query(models.SoftwareSecurityLog)
    if device_id:
        query = query.filter(models.SoftwareSecurityLog.device_id == device_id)
    if severity:
        query = query.filter(models.SoftwareSecurityLog.severity_level == severity)
    return query.order_by(models.SoftwareSecurityLog.timestamp.desc()).limit(min(limit, 500)).all()
