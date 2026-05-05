from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .analysis import build_analysis, consumption_level_for, energy_for, estimate_power
from .auth import create_access_token, get_current_user, hash_password, verify_password
from .database import Base, engine, get_db
from .models import Activity, AnalysisResult, Device, User
from .schemas import ActivityCreate, ActivityOut, AnalysisOut, DeviceCreate, DeviceOut, LoginIn, TokenOut, UserCreate, UserOut


Base.metadata.create_all(bind=engine)

app = FastAPI(title="BatteryCurve AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def owned_device(db: Session, user: User, device_id: int) -> Device:
    device = db.query(Device).filter(Device.id == device_id, Device.user_id == user.id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    return device


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
    activities = db.query(Activity).filter(Activity.device_id == device_id, Activity.user_id == user.id).order_by(Activity.created_at).all()
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
def create_analysis(device_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    device = owned_device(db, user, device_id)
    activities = db.query(Activity).filter(Activity.device_id == device_id, Activity.user_id == user.id).order_by(Activity.created_at).all()
    result = build_analysis(device, activities)
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
    activities = db.query(Activity).filter(Activity.device_id == device.id, Activity.user_id == user.id).order_by(Activity.created_at).all()
    live = build_analysis(device, activities)
    return analysis_payload(analysis, live)


@app.get("/devices/{device_id}/analysis/history", response_model=list[AnalysisOut])
def analysis_history(device_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    device = owned_device(db, user, device_id)
    activities = db.query(Activity).filter(Activity.device_id == device.id, Activity.user_id == user.id).order_by(Activity.created_at).all()
    live = build_analysis(device, activities)
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
        "created_at": analysis.created_at,
    }
