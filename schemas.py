from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import (
    UserRole, DeviceStatus, SeverityLevel, ApprovalStatus, TicketPriority, TicketStatus
)


# ---------- Auth / Users ----------

class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole
    contact_info: str | None = Field(default=None, max_length=255)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter")
        return v


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: int
    username: str
    role: UserRole
    contact_info: str | None
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    user_id: int
    username: str


class LoginRequest(BaseModel):
    username: str
    password: str


# ---------- Devices ----------

class DeviceCreate(BaseModel):
    device_name: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=50)
    location: str = Field(min_length=1, max_length=100)
    status: DeviceStatus = DeviceStatus.ONLINE


class DeviceUpdate(BaseModel):
    device_name: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=100)
    status: DeviceStatus | None = None


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    device_id: int
    device_name: str
    category: str
    location: str
    status: DeviceStatus
    last_checked: datetime | None


# ---------- Sensor Readings ----------

class SensorReadingCreate(BaseModel):
    device_id: int
    temperature: float | None = Field(default=None, ge=-50, le=200)
    voltage: float | None = Field(default=None, ge=0, le=1000)
    pressure: float | None = Field(default=None, ge=0, le=10000)
    cpu_load: float | None = Field(default=None, ge=0, le=100)


class SensorReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    reading_id: int
    device_id: int
    temperature: float | None
    voltage: float | None
    pressure: float | None
    cpu_load: float | None
    timestamp: datetime


# ---------- Security Logs ----------

class SecurityLogCreate(BaseModel):
    device_id: int
    log_type: str = Field(min_length=1, max_length=100)
    severity_level: SeverityLevel = SeverityLevel.INFO
    details: str | None = Field(default=None, max_length=4000)


class SecurityLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    log_id: int
    device_id: int
    log_type: str
    severity_level: SeverityLevel | None
    details: str | None
    timestamp: datetime


# ---------- AI Predictions ----------

class PredictionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    prediction_id: int
    device_id: int
    risk_score: float
    predicted_failure_type: str | None
    requires_human_approval: bool
    approval_status: ApprovalStatus
    approved_by: int | None
    approval_notes: str | None
    prediction_time: datetime


class PredictionDecision(BaseModel):
    approve: bool
    notes: str | None = Field(default=None, max_length=2000)
    # If approved, optionally open a ticket in the same action
    open_ticket: bool = True
    priority: TicketPriority | None = None


# ---------- Maintenance Tickets ----------

class TicketCreate(BaseModel):
    device_id: int
    prediction_id: int | None = None
    priority: TicketPriority
    scheduled_for: datetime | None = None
    assigned_to: int | None = None


class TicketUpdate(BaseModel):
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    assigned_to: int | None = None
    scheduled_for: datetime | None = None


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ticket_id: int
    device_id: int
    prediction_id: int | None
    created_by: int | None
    assigned_to: int | None
    priority: TicketPriority
    status: TicketStatus
    created_at: datetime
    scheduled_for: datetime | None


# ---------- Audit ----------

class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    audit_id: int
    user_id: int | None
    action: str
    entity_type: str
    entity_id: int | None
    details: str | None
    ip_address: str | None
    timestamp: datetime
