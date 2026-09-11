from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import verify_password, create_access_token
from ..deps import get_current_user, client_ip
from ..audit import log_action

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.Token)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()

    # Constant-shape failure path: don't reveal whether the username exists.
    if not user or not verify_password(form_data.password, user.password_hash):
        log_action(
            db, user_id=user.user_id if user else None, action="LOGIN_FAILED",
            entity_type="User", entity_id=user.user_id if user else None,
            details=f"Failed login attempt for username='{form_data.username}'",
            ip_address=client_ip(request),
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    token = create_access_token(subject=user.username, role=user.role.value, user_id=user.user_id)

    log_action(
        db, user_id=user.user_id, action="LOGIN_SUCCESS", entity_type="User",
        entity_id=user.user_id, ip_address=client_ip(request),
    )
    db.commit()

    return schemas.Token(
        access_token=token, role=user.role, user_id=user.user_id, username=user.username
    )


@router.get("/me", response_model=schemas.UserOut)
def read_current_user(current_user: models.User = Depends(get_current_user)):
    return current_user
