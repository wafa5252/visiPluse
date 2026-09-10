"""
Populates the database with demo users, devices, and a burst of telemetry
so the dashboard has something to show immediately after setup.

Run with:  python seed.py
"""
import random
from datetime import datetime, timedelta

from app.database import SessionLocal, Base, engine
from app import models
from app.security import hash_password
from app.ai_engine import evaluate_and_maybe_create_prediction

Base.metadata.create_all(bind=engine)
db = SessionLocal()

DEMO_USERS = [
    ("admin", "AdminPass123", models.UserRole.ADMIN, "admin@visipulse.hospital"),
    ("dr.hana", "ClinicPass123", models.UserRole.MEDICAL_STAFF, "hana@visipulse.hospital"),
    ("tech.omar", "TechPass123", models.UserRole.MAINTENANCE_TECH, "omar@visipulse.hospital"),
]

DEMO_DEVICES = [
    ("MRI Scanner A1", "Imaging", "Radiology Wing - Room 204"),
    ("Ventilator V-12", "Life Support", "ICU - Bay 3"),
    ("Infusion Pump P-07", "Patient Care", "Ward 5 - Bed 12"),
    ("CT Scanner C2", "Imaging", "Radiology Wing - Room 210"),
    ("Dialysis Unit D-04", "Life Support", "Nephrology - Room 3"),
]


def run():
    if db.query(models.User).count() > 0:
        print("Database already seeded — skipping. Delete visipulse.db to reset.")
        return

    users = {}
    for username, password, role, contact in DEMO_USERS:
        u = models.User(
            username=username, password_hash=hash_password(password),
            role=role, contact_info=contact,
        )
        db.add(u)
        users[username] = u
    db.flush()

    devices = []
    for name, category, location in DEMO_DEVICES:
        d = models.Device(
            device_name=name, category=category, location=location,
            status=models.DeviceStatus.ONLINE, last_checked=datetime.utcnow(),
        )
        db.add(d)
        devices.append(d)
    db.flush()

    # Normal telemetry history for every device
    base_time = datetime.utcnow() - timedelta(hours=5)
    for d in devices:
        for i in range(20):
            reading = models.SensorReading(
                device_id=d.device_id,
                temperature=round(random.uniform(20, 24), 1),
                voltage=round(random.uniform(215, 225), 1),
                pressure=round(random.uniform(95, 105), 1),
                cpu_load=round(random.uniform(10, 40), 1),
                timestamp=base_time + timedelta(minutes=i * 15),
            )
            db.add(reading)
    db.flush()

    # Inject one anomalous reading on the MRI scanner to demonstrate the
    # predictive pipeline end-to-end
    mri = devices[0]
    anomalous = models.SensorReading(
        device_id=mri.device_id,
        temperature=41.5,   # well outside normal / hard bounds
        voltage=224.0,
        pressure=98.0,
        cpu_load=35.0,
        timestamp=datetime.utcnow(),
    )
    db.add(anomalous)
    db.flush()

    prediction = evaluate_and_maybe_create_prediction(db, mri.device_id)

    # A resolved historical example too
    vent = devices[1]
    old_prediction = models.AIPrediction(
        device_id=vent.device_id, risk_score=72.0,
        predicted_failure_type="Power supply instability",
        requires_human_approval=True,
        approval_status=models.ApprovalStatus.APPROVED,
        approved_by=users["dr.hana"].user_id,
        approval_notes="Confirmed with biomedical engineering; scheduling inspection.",
        prediction_time=datetime.utcnow() - timedelta(days=1),
    )
    db.add(old_prediction)
    db.flush()
    ticket = models.MaintenanceTicket(
        device_id=vent.device_id, prediction_id=old_prediction.prediction_id,
        created_by=users["dr.hana"].user_id, assigned_to=users["tech.omar"].user_id,
        priority=models.TicketPriority.HIGH, status=models.TicketStatus.IN_PROGRESS,
        created_at=datetime.utcnow() - timedelta(days=1),
        scheduled_for=datetime.utcnow() + timedelta(days=1),
    )
    db.add(ticket)

    db.commit()

    print("Seed complete.")
    print("Demo accounts (username / password):")
    for username, password, role, _ in DEMO_USERS:
        print(f"  {username} / {password}  ({role.value})")
    if prediction:
        print(f"\nGenerated a live pending AI prediction on '{mri.device_name}' "
              f"(risk_score={prediction.risk_score}) — approve it as dr.hana or admin.")


if __name__ == "__main__":
    run()
    db.close()
