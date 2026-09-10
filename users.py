from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_roles, client_ip, get_current_user
from ..security import hash_password
from ..audit import log_action
from ..models import UserRole

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: schemas.UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_roles(UserRole.ADMIN)),
):
    existing = db.query(models.User).filter(models.User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    user = models.User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        contact_info=payload.contact_info,
    )
    db.add(user)
    db.flush()

    log_action(
        db, user_id=admin.user_id, action="USER_CREATED", entity_type="User",
        entity_id=user.user_id, details=f"role={payload.role.value}", ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(user)
    return user


@router.get("", response_model=list[schemas.UserOut])
def list_users(
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_roles(UserRole.ADMIN)),
):
    return db.query(models.User).order_by(models.User.username).all()


@router.patch("/{user_id}/deactivate", response_model=schemas.UserOut)
def deactivate_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_roles(UserRole.ADMIN)),
):
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.is_active = False

    log_action(
        db, user_id=admin.user_id, action="USER_DEACTIVATED", entity_type="User",
        entity_id=user.user_id, ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(user)
    return user


@router.get("/me/summary", response_model=schemas.UserOut)
def my_summary(current_user: models.User = Depends(get_current_user)):
    return current_user
