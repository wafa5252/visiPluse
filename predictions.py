from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_roles, get_current_user, client_ip
from ..audit import log_action
from ..ai_engine import evaluate_and_maybe_create_prediction
from ..models import UserRole, ApprovalStatus, TicketPriority

router = APIRouter(prefix="/predictions", tags=["predictions"])

# Only clinical/operational decision-makers approve predictions that will
# spawn maintenance action on hospital equipment — technicians execute
# tickets but do not self-approve the AI's risk assessment.
APPROVAL_ROLES = (UserRole.ADMIN, UserRole.MEDICAL_STAFF)


@router.post("/run/{device_id}", response_model=schemas.PredictionOut | None)
def run_prediction(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles(UserRole.ADMIN, UserRole.MAINTENANCE_TECH)),
):
    """Manually trigger the anomaly-detection engine against a device's latest telemetry."""
    device = db.get(models.Device, device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    prediction = evaluate_and_maybe_create_prediction(db, device_id)
    if prediction:
        log_action(
            db, user_id=user.user_id, action="AI_PREDICTION_GENERATED", entity_type="AIPrediction",
            entity_id=prediction.prediction_id, details=f"manual_trigger, risk={prediction.risk_score}",
            ip_address=client_ip(request),
        )
    db.commit()
    if prediction:
        db.refresh(prediction)
    return prediction


@router.get("", response_model=list[schemas.PredictionOut])
def list_predictions(
    status_filter: ApprovalStatus | None = None,
    device_id: int | None = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    query = db.query(models.AIPrediction)
    if status_filter:
        query = query.filter(models.AIPrediction.approval_status == status_filter)
    if device_id:
        query = query.filter(models.AIPrediction.device_id == device_id)
    return query.order_by(models.AIPrediction.prediction_time.desc()).all()


@router.post("/{prediction_id}/decision", response_model=schemas.PredictionOut)
def decide_prediction(
    prediction_id: int,
    payload: schemas.PredictionDecision,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles(*APPROVAL_ROLES)),
):
    """
    Core human-in-the-loop step. A medical staff member or admin reviews
    an AI-generated risk prediction and either approves it (optionally
    auto-opening a maintenance ticket in the same transaction) or rejects
    it. Every decision is attributed to the approving user and audit-logged.
    """
    prediction = db.get(models.AIPrediction, prediction_id)
    if not prediction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction not found")
    if prediction.approval_status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Prediction already {prediction.approval_status.value}",
        )

    prediction.approval_status = ApprovalStatus.APPROVED if payload.approve else ApprovalStatus.REJECTED
    prediction.approved_by = user.user_id
    prediction.approval_notes = payload.notes

    log_action(
        db, user_id=user.user_id, action=f"PREDICTION_{prediction.approval_status.value.upper()}",
        entity_type="AIPrediction", entity_id=prediction.prediction_id,
        details=payload.notes, ip_address=client_ip(request),
    )

    ticket = None
    if payload.approve and payload.open_ticket:
        priority = payload.priority or _priority_from_risk(prediction.risk_score)
        ticket = models.MaintenanceTicket(
            device_id=prediction.device_id,
            prediction_id=prediction.prediction_id,
            created_by=user.user_id,
            priority=priority,
            status=models.TicketStatus.OPEN,
        )
        db.add(ticket)
        db.flush()
        log_action(
            db, user_id=user.user_id, action="TICKET_AUTO_CREATED", entity_type="MaintenanceTicket",
            entity_id=ticket.ticket_id, details=f"from_prediction={prediction.prediction_id}",
            ip_address=client_ip(request),
        )

    db.commit()
    db.refresh(prediction)
    return prediction


def _priority_from_risk(risk_score: float) -> TicketPriority:
    if risk_score >= 85:
        return TicketPriority.URGENT
    if risk_score >= 70:
        return TicketPriority.HIGH
    if risk_score >= 60:
        return TicketPriority.MEDIUM
    return TicketPriority.LOW
