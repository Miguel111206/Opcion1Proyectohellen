import logging
import os
import time
from datetime import date, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from .analysis import build_analysis, consumption_level_for, energy_for, estimate_power
from .auth import create_access_token, get_current_user, hash_password, verify_password
from .database import Base, engine, get_db
from .models import Activity, AnalysisResult, Device, User
from .schemas import ActivityCreate, ActivityOut, AnalysisOut, DeviceCreate, DeviceOut, LoginIn, TokenOut, UserCreate, UserOut


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("batterycurve.api")


def initialize_database(max_attempts: int = 20, delay_seconds: float = 2.0) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            Base.metadata.create_all(bind=engine)
            ensure_schema_updates()
            logger.info("Base de datos lista")
            return
        except OperationalError:
            if attempt == max_attempts:
                logger.exception("No se pudo conectar a la base de datos despues de %s intentos", max_attempts)
                raise
            logger.warning("Base de datos no disponible, reintento %s/%s", attempt, max_attempts)
            time.sleep(delay_seconds)


def ensure_schema_updates() -> None:
    inspector = inspect(engine)
    if "activities" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("activities")}
    if "activity_date" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE activities ADD COLUMN activity_date DATE NULL"))
            connection.execute(text("UPDATE activities SET activity_date = DATE(created_at) WHERE activity_date IS NULL"))


initialize_database()

app = FastAPI(title="BatteryCurve AI API")

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5723,http://127.0.0.1:5723",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ApiPrefixMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.scope["path"].startswith("/api/"):
            request.scope["path"] = request.scope["path"][4:]
        return await call_next(request)


app.add_middleware(ApiPrefixMiddleware)


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    logger.exception("Error inesperado en %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor. Revisa los logs del backend para mas detalle."},
    )


def owned_device(db: Session, user: User, device_id: int) -> Device:
    device = db.query(Device).filter(Device.id == device_id, Device.user_id == user.id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    return device


def period_bounds(period: str, reference_date: date | None) -> tuple[date | None, date | None, str]:
    if period == "all":
        return None, None, "Todo el historial"
    anchor = reference_date or date.today()
    if period == "day":
        return anchor, anchor, f"Dia {anchor}"
    if period == "week":
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=6)
        return start, end, f"Semana {start} a {end}"
    if period == "month":
        start = anchor.replace(day=1)
        end = (start.replace(year=start.year + 1, month=1, day=1) if start.month == 12 else start.replace(month=start.month + 1, day=1)) - timedelta(days=1)
        return start, end, f"Mes {start:%Y-%m}"
    raise HTTPException(status_code=422, detail="Periodo invalido. Usa day, week, month o all.")


def device_activities_query(db: Session, user: User, device_id: int, period: str = "all", reference_date: date | None = None):
    start, end, _ = period_bounds(period, reference_date)
    query = db.query(Activity).filter(Activity.device_id == device_id, Activity.user_id == user.id)
    if start:
        query = query.filter(Activity.activity_date >= start, Activity.activity_date <= end)
    return query.order_by(Activity.activity_date, Activity.created_at)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/register", response_model=TokenOut)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="El correo ya esta registrado")
    user = User(name=payload.name, email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"access_token": create_access_token(user.id), "user": user}


@app.post("/auth/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales invalidas")
    return {"access_token": create_access_token(user.id), "user": user}


@app.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@app.get("/devices", response_model=list[DeviceOut])
def list_devices(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Device).filter(Device.user_id == user.id).order_by(Device.created_at.desc()).all()


@app.post("/devices", response_model=DeviceOut)
def create_device(payload: DeviceCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.type.lower() == "celular" and payload.battery_capacity_wh > 35:
        raise HTTPException(status_code=422, detail="Para celulares usa una capacidad realista entre 10 y 25 Wh. 300 Wh haria que el porcentaje baje muy poco.")
    device = Device(user_id=user.id, **payload.model_dump())
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@app.delete("/devices/{device_id}")
def delete_device(device_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    device = owned_device(db, user, device_id)
    db.delete(device)
    db.commit()
    return {"ok": True}


@app.get("/devices/{device_id}/activities", response_model=list[ActivityOut])
def list_activities(device_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned_device(db, user, device_id)
    activities = db.query(Activity).filter(Activity.device_id == device_id, Activity.user_id == user.id).order_by(Activity.activity_date, Activity.created_at).all()
    return [
        {
            "id": activity.id,
            "app_name": activity.app_name,
            "duration_minutes": activity.duration_minutes,
            "power_watts": activity.power_watts,
            "consumption_level": activity.consumption_level,
            "brightness": activity.brightness,
            "connection_type": activity.connection_type,
            "saving_mode": activity.saving_mode,
            "activity_date": activity.activity_date,
            "energy_wh": round(energy_for(activity), 2),
            "created_at": activity.created_at,
        }
        for activity in activities
    ]


@app.post("/devices/{device_id}/activities", response_model=ActivityOut)
def create_activity(device_id: int, payload: ActivityCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned_device(db, user, device_id)
    power_watts = estimate_power(payload.app_name, payload.brightness, payload.connection_type, payload.saving_mode)
    activity = Activity(
        user_id=user.id,
        device_id=device_id,
        app_name=payload.app_name,
        duration_minutes=payload.duration_minutes,
        activity_date=payload.activity_date,
        power_watts=power_watts,
        consumption_level=consumption_level_for(power_watts),
        brightness=payload.brightness,
        connection_type=payload.connection_type,
        saving_mode=payload.saving_mode,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return {
        "id": activity.id,
        "app_name": activity.app_name,
        "duration_minutes": activity.duration_minutes,
        "power_watts": activity.power_watts,
        "consumption_level": activity.consumption_level,
        "brightness": activity.brightness,
        "connection_type": activity.connection_type,
        "saving_mode": activity.saving_mode,
        "activity_date": activity.activity_date,
        "energy_wh": round(energy_for(activity), 2),
        "created_at": activity.created_at,
    }


@app.delete("/activities/{activity_id}")
def delete_activity(activity_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    activity = db.query(Activity).filter(Activity.id == activity_id, Activity.user_id == user.id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")
    db.delete(activity)
    db.commit()
    return {"ok": True}


@app.post("/devices/{device_id}/analysis", response_model=AnalysisOut)
def create_analysis(
    device_id: int,
    period: str = Query("all", pattern="^(day|week|month|all)$"),
    reference_date: date | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device = owned_device(db, user, device_id)
    _, _, period_label = period_bounds(period, reference_date)
    activities = device_activities_query(db, user, device_id, period, reference_date).all()
    result = build_analysis(device, activities)
    result["period_label"] = period_label
    analysis = AnalysisResult(user_id=user.id, device_id=device_id, **{k: result[k] for k in [
        "total_energy_wh", "battery_used_percent", "battery_remaining_percent", "highest_consumption_app", "critical_period", "recommendation"
    ]})
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis_payload(analysis, result)


@app.get("/devices/{device_id}/analysis/latest", response_model=AnalysisOut)
def latest_analysis(device_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    device = owned_device(db, user, device_id)
    analysis = db.query(AnalysisResult).filter(AnalysisResult.device_id == device_id, AnalysisResult.user_id == user.id).order_by(AnalysisResult.created_at.desc()).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="No hay analisis")
    activities = db.query(Activity).filter(Activity.device_id == device.id, Activity.user_id == user.id).order_by(Activity.activity_date, Activity.created_at).all()
    live = build_analysis(device, activities)
    live["period_label"] = "Todo el historial"
    return analysis_payload(analysis, live)


@app.get("/devices/{device_id}/analysis/history", response_model=list[AnalysisOut])
def analysis_history(device_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    device = owned_device(db, user, device_id)
    activities = db.query(Activity).filter(Activity.device_id == device.id, Activity.user_id == user.id).order_by(Activity.activity_date, Activity.created_at).all()
    live = build_analysis(device, activities)
    live["period_label"] = "Todo el historial"
    analyses = db.query(AnalysisResult).filter(AnalysisResult.device_id == device_id, AnalysisResult.user_id == user.id).order_by(AnalysisResult.created_at.desc()).limit(20).all()
    return [analysis_payload(item, live) for item in analyses]


def analysis_payload(analysis: AnalysisResult, live: dict) -> dict:
    return {
        "id": analysis.id,
        "total_energy_wh": analysis.total_energy_wh,
        "battery_used_percent": analysis.battery_used_percent,
        "battery_remaining_percent": analysis.battery_remaining_percent,
        "highest_consumption_app": analysis.highest_consumption_app,
        "critical_period": analysis.critical_period,
        "recommendation": analysis.recommendation,
        "timeline": live["timeline"],
        "app_energy": live["app_energy"],
        "daily_energy": live["daily_energy"],
        "highest_consumption_day": live["highest_consumption_day"],
        "lowest_consumption_day": live["lowest_consumption_day"],
        "period_label": live.get("period_label", "Todo el historial"),
        "created_at": analysis.created_at,
    }
