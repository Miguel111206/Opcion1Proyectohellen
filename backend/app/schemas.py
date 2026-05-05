from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6)


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr

    model_config = {"from_attributes": True}


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class DeviceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    type: str = Field(min_length=2, max_length=60)
    battery_capacity_wh: float = Field(gt=0, le=300)


class DeviceOut(DeviceCreate):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ActivityCreate(BaseModel):
    app_name: str = Field(min_length=2, max_length=120)
    duration_minutes: float = Field(gt=0, le=1440)
    brightness: str = "Medio"
    connection_type: str = "WiFi"
    saving_mode: str = "Desactivado"


class ActivityOut(ActivityCreate):
    id: int
    power_watts: float
    consumption_level: str
    energy_wh: float
    created_at: datetime

    model_config = {"from_attributes": True}


class TimelinePoint(BaseModel):
    time_label: str
    hour: float
    power_watts: float
    battery_remaining: float
    app_name: str


class AppEnergy(BaseModel):
    app_name: str
    energy_wh: float


class AnalysisOut(BaseModel):
    id: int
    total_energy_wh: float
    battery_used_percent: float
    battery_remaining_percent: float
    highest_consumption_app: str
    critical_period: str
    recommendation: str
    timeline: list[TimelinePoint]
    app_energy: list[AppEnergy]
    created_at: datetime

    model_config = {"from_attributes": True}
