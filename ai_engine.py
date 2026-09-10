"""
Narrow AI anomaly-detection engine.

Deliberately NOT a black box: this is a transparent, auditable statistical
model (rolling z-score deviation per metric) rather than an opaque neural
net, because a hospital equipment governance system needs predictions a
human reviewer can actually reason about before approving. It is easy to
swap this module for a trained model later (e.g. an sklearn IsolationForest
or a small time-series model) without touching any router code — every
caller only depends on `evaluate_device()`'s return shape.

Metrics considered: temperature, voltage, pressure, cpu_load.
"""
import statistics
from dataclasses import dataclass

from sqlalchemy.orm import Session

from . import models
from .config import settings

METRICS = ("temperature", "voltage", "pressure", "cpu_load")

# Minimum history required before we trust a z-score; below this we fall
# back to a much more conservative flat-threshold check.
MIN_HISTORY_FOR_ZSCORE = 8

# Static safety bounds used as a fallback / hard ceiling regardless of
# historical baseline, so a first-ever extreme reading is never ignored.
HARD_BOUNDS = {
    "temperature": (10.0, 45.0),   # deg C
    "voltage": (100.0, 260.0),     # V
    "pressure": (0.0, 150.0),      # kPa (device-dependent, illustrative)
    "cpu_load": (0.0, 95.0),       # %
}


@dataclass
class AnomalyResult:
    risk_score: float                 # 0-100
    predicted_failure_type: str | None
    contributing_metrics: list[str]
    rationale: str


def _zscore(value: float, history: list[float]) -> float:
    if len(history) < 2:
        return 0.0
    mean = statistics.mean(history)
    stdev = statistics.pstdev(history) or 1e-6
    return abs(value - mean) / stdev


def evaluate_device(db: Session, device_id: int, window: int = 30) -> AnomalyResult | None:
    """
    Pulls the most recent `window` readings for a device, compares the
    latest reading against the historical baseline for each metric, and
    returns a composite risk score. Returns None if there isn't at least
    one reading to evaluate.
    """
    readings = (
        db.query(models.SensorReading)
        .filter(models.SensorReading.device_id == device_id)
        .order_by(models.SensorReading.timestamp.desc())
        .limit(window)
        .all()
    )
    if not readings:
        return None

    latest = readings[0]
    history_by_metric = {m: [] for m in METRICS}
    for r in readings[1:]:
        for m in METRICS:
            val = getattr(r, m)
            if val is not None:
                history_by_metric[m].append(val)

    contributing: list[str] = []
    metric_scores: dict[str, float] = {}

    for m in METRICS:
        current = getattr(latest, m)
        if current is None:
            continue

        # Hard bound check (always applied, catches first-ever extreme readings)
        lo, hi = HARD_BOUNDS[m]
        out_of_bounds = current < lo or current > hi

        history = history_by_metric[m]
        if len(history) >= MIN_HISTORY_FOR_ZSCORE:
            z = _zscore(current, history)
            # Map z-score to a 0-100 scale: z=0 -> 0, z>=4 -> 100
            score = min(100.0, (z / 4.0) * 100.0)
        else:
            score = 100.0 if out_of_bounds else 0.0

        if out_of_bounds:
            score = max(score, 80.0)

        metric_scores[m] = score
        if score >= settings.anomaly_risk_threshold:
            contributing.append(m)

    if not metric_scores:
        return None

    # Composite risk score: weighted toward the worst offending metric,
    # but informed by the overall pattern (a device drifting on multiple
    # sensors at once is riskier than one metric alone).
    worst = max(metric_scores.values())
    avg = sum(metric_scores.values()) / len(metric_scores)
    composite = round(0.7 * worst + 0.3 * avg, 1)

    failure_map = {
        "temperature": "Overheating / thermal failure",
        "voltage": "Power supply instability",
        "pressure": "Pressure seal / pump failure",
        "cpu_load": "Compute overload / firmware fault",
    }
    predicted_type = None
    if contributing:
        top_metric = max(contributing, key=lambda m: metric_scores[m])
        predicted_type = failure_map.get(top_metric)

    rationale = "; ".join(
        f"{m} deviation score={score:.0f}" for m, score in metric_scores.items()
    )

    return AnomalyResult(
        risk_score=composite,
        predicted_failure_type=predicted_type,
        contributing_metrics=contributing,
        rationale=rationale,
    )


def evaluate_and_maybe_create_prediction(
    db: Session, device_id: int
) -> models.AIPrediction | None:
    """
    Runs evaluate_device() and, if the composite risk score clears the
    configured threshold, writes a new AIPrediction row. Every prediction
    is created with requires_human_approval=True — this engine never
    auto-triggers a ticket on its own; a human must approve it first
    (see routers/predictions.py).
    """
    result = evaluate_device(db, device_id)
    if result is None or result.risk_score < settings.anomaly_risk_threshold:
        return None

    prediction = models.AIPrediction(
        device_id=device_id,
        risk_score=result.risk_score,
        predicted_failure_type=result.predicted_failure_type,
        requires_human_approval=True,
    )
    db.add(prediction)
    db.flush()  # populate prediction_id without committing the outer transaction
    return prediction
