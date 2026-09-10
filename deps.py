from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import get_db
from .security import decode_access_token
from . import models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_error

    user_id = payload.get("user_id")
    if user_id is None:
        raise credentials_error

    user = db.get(models.User, user_id)
    if user is None or not user.is_active:
        raise credentials_error

    # Stash on request.state so route handlers can pull the client IP etc.
    # for audit logging without re-deriving it.
    request.state.current_user = user
    return user


def require_roles(*allowed_roles: models.UserRole):
    """
    RBAC guard factory. Usage:
        @router.post(..., dependencies=[Depends(require_roles(UserRole.ADMIN))])
    """
    def _guard(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role.value}' is not permitted to perform this action.",
            )
        return user
    return _guard


def client_ip(request: Request) -> str | None:
    # Respect a trusted reverse-proxy header if present, else fall back to peer address.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
