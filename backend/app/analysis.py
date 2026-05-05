from collections import defaultdict

from .models import Activity, Device


BASE_POWER_WATTS = {
    "reposo": 0.6,
    "whatsapp": 2.0,
    "musica": 1.6,
    "redes sociales": 3.0,
    "youtube": 4.8,
    "videollamada": 6.2,
    "videojuego": 8.5,
}


def estimate_power(app_name: str, brightness: str, connection_type: str, saving_mode: str) -> float:
    app_key = app_name.strip().lower()
    base = BASE_POWER_WATTS.get(app_key, 3.2)
    brightness_factor = {"bajo": 0.85, "medio": 1.0, "alto": 1.22}.get(brightness.lower(), 1.0)
    connection_factor = {"wifi": 1.0, "datos moviles": 1.18, "sin conexion": 0.9}.get(connection_type.lower(), 1.0)
    saving_factor = 0.82 if saving_mode.lower() == "activado" else 1.0
    return round(base * brightness_factor * connection_factor * saving_factor, 2)


def consumption_level_for(power_watts: float) -> str:
    if power_watts < 2.2:
        return "Bajo"
    if power_watts < 5.2:
        return "Medio"
    return "Alto"


def energy_for(activity: Activity) -> float:
    return activity.power_watts * activity.duration_minutes / 60


def build_analysis(device: Device, activities: list[Activity]) -> dict:
    total_energy = sum(energy_for(activity) for activity in activities)
    used_percent = (total_energy / device.battery_capacity_wh) * 100
    remaining_percent = max(0, 100 - used_percent)

    app_energy = defaultdict(float)
    timeline = []
    elapsed_minutes = 0.0
    remaining = 100.0
    max_activity = None
    max_energy = -1.0

    for activity in activities:
        energy = energy_for(activity)
        app_energy[activity.app_name] += energy
        if energy > max_energy:
            max_energy = energy
            max_activity = activity

        start_hour = elapsed_minutes / 60
        elapsed_minutes += activity.duration_minutes
        remaining = max(0, remaining - (energy / device.battery_capacity_wh) * 100)
        timeline.append(
            {
                "time_label": f"{start_hour:.2f}h - {elapsed_minutes / 60:.2f}h",
                "hour": round(elapsed_minutes / 60, 2),
                "power_watts": round(activity.power_watts, 2),
                "battery_remaining": round(remaining, 2),
                "app_name": activity.app_name,
            }
        )

    highest_app = max_activity.app_name if max_activity else "Sin datos"
    critical_period = timeline[activities.index(max_activity)]["time_label"] if max_activity else "Sin datos"

    return {
        "total_energy_wh": round(total_energy, 2),
        "battery_used_percent": round(used_percent, 2),
        "battery_remaining_percent": round(remaining_percent, 2),
        "highest_consumption_app": highest_app,
        "critical_period": critical_period,
        "recommendation": recommend(used_percent, remaining_percent, max_activity),
        "timeline": timeline,
        "app_energy": [
            {"app_name": name, "energy_wh": round(energy, 2)}
            for name, energy in sorted(app_energy.items(), key=lambda item: item[1], reverse=True)
        ],
    }


def recommend(used_percent: float, remaining_percent: float, max_activity: Activity | None) -> str:
    if not max_activity:
        return "Agrega actividades para generar una recomendacion inteligente."

    app = max_activity.app_name.lower()
    level = max_activity.consumption_level.lower()

    if remaining_percent < 20:
        return "Bateria critica: activa modo ahorro, baja el brillo y limita apps de alto consumo."
    if "juego" in app or "game" in app or level == "alto":
        return "El mayor consumo viene de una app exigente: reduce graficos, brillo o tiempo de uso."
    if "youtube" in app or "video" in app:
        return "El video aumento el area bajo la curva: baja resolucion, brillo o usa WiFi estable."
    if "llamada" in app or "meet" in app or "zoom" in app:
        return "La videollamada consume bastante: cierra apps en segundo plano y evita datos moviles."
    if used_percent > 50:
        return "El area total es alta: activa modo ahorro y distribuye mejor las actividades intensivas."
    return "Consumo estable: conserva brillo medio y revisa apps que permanezcan activas por mucho tiempo."
