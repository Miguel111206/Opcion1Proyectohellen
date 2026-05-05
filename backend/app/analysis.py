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
        "recommendation": recommend(used_percent, remaining_percent, max_activity, activities),
        "timeline": timeline,
        "app_energy": [
            {"app_name": name, "energy_wh": round(energy, 2)}
            for name, energy in sorted(app_energy.items(), key=lambda item: item[1], reverse=True)
        ],
    }


def recommend(used_percent: float, remaining_percent: float, max_activity: Activity | None, activities: list[Activity]) -> str:
    if not max_activity:
        return "Agrega actividades para generar una recomendacion inteligente."

    app = max_activity.app_name.lower()
    total_minutes = sum(activity.duration_minutes for activity in activities)
    high_brightness_minutes = sum(activity.duration_minutes for activity in activities if activity.brightness.lower() == "alto")
    mobile_data_minutes = sum(activity.duration_minutes for activity in activities if activity.connection_type.lower() == "datos moviles")
    saving_mode_off_minutes = sum(activity.duration_minutes for activity in activities if activity.saving_mode.lower() == "desactivado")

    advice = []

    if remaining_percent < 20:
        advice.append("Bateria critica: activa modo ahorro y evita abrir apps de alto consumo hasta cargar.")
    elif remaining_percent < 35:
        advice.append("Bateria baja: reduce brillo, usa WiFi y prioriza actividades necesarias.")
    elif used_percent > 65:
        advice.append("El area bajo la curva es alta para este periodo: conviene dividir las actividades intensivas.")

    if "juego" in app or "game" in app or "videojuego" in app:
        advice.append("El mayor consumo viene del videojuego: baja graficos, limita FPS, reduce brillo y juega conectado a WiFi.")
    elif "youtube" in app or "video" in app:
        advice.append("El video domina el consumo: baja resolucion, desactiva reproduccion automatica y usa brillo medio.")
    elif "videollamada" in app or "llamada" in app or "meet" in app or "zoom" in app:
        advice.append("La videollamada exige camara, microfono y red: cierra apps en segundo plano y evita datos moviles.")
    elif "redes" in app or "instagram" in app or "tiktok" in app or "facebook" in app:
        advice.append("Las redes sociales pueden consumir mucho por video corto y scroll continuo: baja brillo y limita el tiempo de pantalla.")
    elif "whatsapp" in app:
        advice.append("WhatsApp normalmente consume poco, pero llamadas, notas de voz y datos moviles pueden elevarlo.")
    elif "musica" in app or "spotify" in app:
        advice.append("Musica es eficiente si la pantalla esta apagada: descarga playlists y evita datos moviles.")
    elif "reposo" in app:
        advice.append("El reposo no deberia gastar mucho: revisa notificaciones, ubicacion y apps en segundo plano.")
    else:
        advice.append(f"{max_activity.app_name} fue la actividad critica: revisa brillo, red y tiempo de uso.")

    if max_activity.power_watts >= 7:
        advice.append("La potencia calculada es alta; cualquier minuto extra aumenta bastante el area bajo la curva.")
    elif max_activity.power_watts >= 4.5:
        advice.append("La potencia es media-alta; reducir brillo o cambiar a WiFi puede mejorar el resultado.")

    if total_minutes and high_brightness_minutes / total_minutes >= 0.45:
        advice.append("Gran parte del uso fue con brillo alto; cambiar a brillo medio puede reducir el consumo de forma visible.")
    if total_minutes and mobile_data_minutes / total_minutes >= 0.35:
        advice.append("Usaste muchos minutos con datos moviles; WiFi suele consumir menos energia y estabiliza la conexion.")
    if total_minutes and saving_mode_off_minutes / total_minutes >= 0.7 and used_percent > 30:
        advice.append("Activa modo ahorro durante actividades largas para recortar consumo sin dejar de usar el equipo.")
    if used_percent > 50:
        advice.append("El consumo supero la mitad de la bateria estimada: programa carga o reduce las apps mas intensivas.")

    if not advice:
        advice.append("Consumo estable: conserva brillo medio y revisa apps que permanezcan activas por mucho tiempo.")

    return " ".join(advice[:4])
