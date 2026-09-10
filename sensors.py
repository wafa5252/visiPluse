from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_roles, get_current_user, client_ip
from ..audit import log_action
from ..ai_engine import evaluate_and_maybe_create_prediction
from ..models import UserRole

router = APIRouter(prefix="/sensor-readings", tags=["telemetry"])

# In production this endpoint would typically be called by IoT gateway
# devices authenticating with a scoped service credential rather than a
# human user token — the RBAC guard below is illustrative for the demo.
INGEST_ROLES = (UserRole.ADMIN, UserRole.MAINTENANCE_TECH)


@router.post("", response_model=schemas.SensorReadingOut, status_code=status.HTTP_201_CREATED)
def ingest_reading(
    payload: schemas.SensorReadingCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles(*INGEST_ROLES)),
):
    device = db.get(models.Device, payload.device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    reading = models.SensorReading(**payload.model_dump(), timestamp=datetime.utcnow())
    db.add(reading)
    device.last_checked = datetime.utcnow()
    db.flush()

    # --- Core predictive pipeline step 1 -> 2: telemetry in, AI evaluation out ---
    prediction = evaluate_and_maybe_create_prediction(db, payload.device_id)

    log_action(
        db, user_id=user.user_id, action="SENSOR_READING_INGESTED", entity_type="SensorReading",
        entity_id=reading.reading_id, ip_address=client_ip(request),
    )
    if prediction:
        log_action(
            db, user_id=None, action="AI_PREDICTION_GENERATED", entity_type="AIPrediction",
            entity_id=prediction.prediction_id,
            details=f"risk_score={prediction.risk_score}, device_id={payload.device_id}",
            ip_address=client_ip(request),
        )

    db.commit()
    db.refresh(reading)
    return reading


@router.get("/device/{device_id}", response_model=list[schemas.SensorReadingOut])
def get_readings_for_device(
    device_id: int,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    return (
        db.query(models.SensorReading)
        .filter(models.SensorReading.device_id == device_id)
        .order_by(models.SensorReading.timestamp.desc())
        .limit(min(limit, 500))
        .all()
    )
