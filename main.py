import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.database import Base, engine
from backend.routers import auth, users, devices, sensors, security_logs, predictions, tickets, audit_router
# Creates tables on first run. For real production use, replace with
# Alembic migrations so schema changes are versioned and reviewable.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="VisiPulse API",
    description="Predictive Health-Tech Hospital Monitoring System",
    version="1.0.0",
    # Hide interactive docs outside development — don't advertise the API
    # surface to unauthenticated clients in production.
    docs_url="/docs" if settings.env != "production" else None,
    redoc_url="/redoc" if settings.env != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """
    Baseline security headers on every response. In production this app
    should sit behind TLS termination (nginx / a managed load balancer);
    HSTS below assumes HTTPS is already enforced upstream.
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response


# --- Minimal in-memory rate limiter for the login endpoint ---
# Prevents brute-force credential guessing. For multi-instance deployments,
# back this with Redis instead of an in-process dict.
_login_attempts: dict[str, deque] = defaultdict(deque)
LOGIN_WINDOW_SECONDS = 60
LOGIN_MAX_ATTEMPTS = 10


@app.middleware("http")
async def login_rate_limit(request: Request, call_next):
    if request.url.path == "/auth/login" and request.method == "POST":
        client_key = request.client.host if request.client else "unknown"
        now = time.time()
        attempts = _login_attempts[client_key]
        while attempts and now - attempts[0] > LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= LOGIN_MAX_ATTEMPTS:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Too many login attempts. Try again shortly."},
            )
        attempts.append(now)
    return await call_next(request)


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(devices.router)
app.include_router(sensors.router)
app.include_router(security_logs.router)
app.include_router(predictions.router)
app.include_router(tickets.router)
app.include_router(audit_router.router)


@app.get("/health", tags=["system"])
def health_check():
    return {"status": "ok"}
