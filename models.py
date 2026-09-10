import enum
from datetime import datetime

from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Text, ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MEDICAL_STAFF = "medical_staff"
    MAINTENANCE_TECH = "maintenance_tech"


class DeviceStatus(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNDER_MAINTENANCE = "under_maintenance"
    DECOMMISSIONED = "decommissioned"


class SeverityLevel(str, enum.Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class TicketPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class User(Base):
    __tablename__ = "user"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), nullable=False)
    contact_info: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    assigned_tickets = relationship(
        "MaintenanceTicket", back_populates="assignee", foreign_keys="MaintenanceTicket.assigned_to"
    )
    created_tickets = relationship(
        "MaintenanceTicket", back_populates="creator", foreign_keys="MaintenanceTicket.created_by"
    )
    approved_predictions = relationship("AIPrediction", back_populates="approver")


class Device(Base):
    __tablename__ = "device"

    device_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    location: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[DeviceStatus] = mapped_column(SAEnum(DeviceStatus), default=DeviceStatus.ONLINE, nullable=False)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    readings = relationship("SensorReading", back_populates="device", cascade="all, delete-orphan")
    security_logs = relationship("SoftwareSecurityLog", back_populates="device", cascade="all, delete-orphan")
    predictions = relationship("AIPrediction", back_populates="device", cascade="all, delete-orphan")
    tickets = relationship("MaintenanceTicket", back_populates="device", cascade="all, delete-orphan")


class SensorReading(Base):
    __tablename__ = "sensor_reading"

    reading_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("device.device_id", ondelete="CASCADE"), nullable=False)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    voltage: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_load: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    device = relationship("Device", back_populates="readings")


class SoftwareSecurityLog(Base):
    __tablename__ = "software_security_log"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("device.device_id", ondelete="CASCADE"), nullable=False)
    log_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity_level: Mapped[SeverityLevel | None] = mapped_column(SAEnum(SeverityLevel), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    device = relationship("Device", back_populates="security_logs")


class AIPrediction(Base):
    __tablename__ = "ai_prediction"

    prediction_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("device.device_id", ondelete="CASCADE"), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_failure_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        SAEnum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False
    )
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user.user_id"), nullable=True)
    approval_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    prediction_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    device = relationship("Device", back_populates="predictions")
    approver = relationship("User", back_populates="approved_predictions")
    ticket = relationship("MaintenanceTicket", back_populates="prediction", uselist=False)


class MaintenanceTicket(Base):
    __tablename__ = "maintenance_ticket"

    ticket_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("device.device_id", ondelete="CASCADE"), nullable=False)
    prediction_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_prediction.prediction_id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.user_id"), nullable=True)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("user.user_id"), nullable=True)
    priority: Mapped[TicketPriority] = mapped_column(SAEnum(TicketPriority), nullable=False)
    status: Mapped[TicketStatus] = mapped_column(SAEnum(TicketStatus), default=TicketStatus.OPEN, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    device = relationship("Device", back_populates="tickets")
    prediction = relationship("AIPrediction", back_populates="ticket")
    creator = relationship("User", back_populates="created_tickets", foreign_keys=[created_by])
    assignee = relationship("User", back_populates="assigned_tickets", foreign_keys=[assigned_to])


class AuditLog(Base):
    """
    Immutable-by-convention record of every security-relevant or
    state-changing event, required for NCA ECC-style audit trails.
    Rows are only ever inserted, never updated or deleted by the API.
    """
    __tablename__ = "audit_log"

    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user.user_id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
