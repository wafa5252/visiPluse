from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_roles, get_current_user, client_ip
from ..audit import log_action
from ..models import UserRole

router = APIRouter(prefix="/devices", tags=["devices"])

# All authenticated roles can read device data; only admins and
# maintenance technicians can create/modify device records.
WRITE_ROLES = (UserRole.ADMIN, UserRole.MAINTENANCE_TECH)


@router.get("", response_model=list[schemas.DeviceOut])
def list_devices(
    status_filter: models.DeviceStatus | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    query = db.query(models.Device)
    if status_filter:
        query = query.filter(models.Device.status == status_filter)
    if category:
        query = query.filter(models.Device.category == category)
    return query.order_by(models.Device.device_name).all()


@router.get("/{device_id}", response_model=schemas.DeviceOut)
def get_device(
    device_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    device = db.get(models.Device, device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return device


@router.post("", response_model=schemas.DeviceOut, status_code=status.HTTP_201_CREATED)
def create_device(
    payload: schemas.DeviceCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles(*WRITE_ROLES)),
):
    device = models.Device(**payload.model_dump(), last_checked=datetime.utcnow())
    db.add(device)
    db.flush()

    log_action(
        db, user_id=user.user_id, action="DEVICE_CREATED", entity_type="Device",
        entity_id=device.device_id, ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(device)
    return device


@router.put("/{device_id}", response_model=schemas.DeviceOut)
def update_device(
    device_id: int,
    payload: schemas.DeviceUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles(*WRITE_ROLES)),
):
    device = db.get(models.Device, device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(device, field, value)
    device.last_checked = datetime.utcnow()

    log_action(
        db, user_id=user.user_id, action="DEVICE_UPDATED", entity_type="Device",
        entity_id=device.device_id, details=str(changes), ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(device)
    return device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_roles(UserRole.ADMIN)),
):
    device = db.get(models.Device, device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    log_action(
        db, user_id=admin.user_id, action="DEVICE_DELETED", entity_type="Device",
        entity_id=device.device_id, details=device.device_name, ip_address=client_ip(request),
    )
    db.delete(device)
    db.commit()
