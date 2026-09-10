from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_roles, get_current_user, client_ip
from ..audit import log_action
from ..models import UserRole, TicketStatus

router = APIRouter(prefix="/tickets", tags=["tickets"])

MANAGE_ROLES = (UserRole.ADMIN, UserRole.MAINTENANCE_TECH)


@router.get("", response_model=list[schemas.TicketOut])
def list_tickets(
    status_filter: TicketStatus | None = None,
    device_id: int | None = None,
    assigned_to: int | None = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    query = db.query(models.MaintenanceTicket)
    if status_filter:
        query = query.filter(models.MaintenanceTicket.status == status_filter)
    if device_id:
        query = query.filter(models.MaintenanceTicket.device_id == device_id)
    if assigned_to:
        query = query.filter(models.MaintenanceTicket.assigned_to == assigned_to)
    return query.order_by(models.MaintenanceTicket.created_at.desc()).all()


@router.post("", response_model=schemas.TicketOut, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: schemas.TicketCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles(*MANAGE_ROLES)),
):
    device = db.get(models.Device, payload.device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    ticket = models.MaintenanceTicket(
        **payload.model_dump(),
        created_by=user.user_id,
        status=TicketStatus.OPEN,
    )
    db.add(ticket)
    db.flush()

    log_action(
        db, user_id=user.user_id, action="TICKET_CREATED", entity_type="MaintenanceTicket",
        entity_id=ticket.ticket_id, ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(ticket)
    return ticket


@router.patch("/{ticket_id}", response_model=schemas.TicketOut)
def update_ticket(
    ticket_id: int,
    payload: schemas.TicketUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles(*MANAGE_ROLES)),
):
    ticket = db.get(models.MaintenanceTicket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(ticket, field, value)

    log_action(
        db, user_id=user.user_id, action="TICKET_UPDATED", entity_type="MaintenanceTicket",
        entity_id=ticket.ticket_id, details=str(changes), ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(ticket)
    return ticket
