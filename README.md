# BatteryCurve AI

Software inteligente para analizar consumo de bateria mediante area bajo la curva.

## Ejecutar

Requisitos:

- Docker Desktop

Comando:

```bash
docker compose up --build
```

Servicios:

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- Docs API: http://localhost:8000/docs
- MySQL local: localhost:3308
- DB: proyectobateria
- Usuario DB: root
- Password DB: 123456789

## Usuario de prueba sugerido

Puedes registrar cualquier usuario desde la pantalla inicial.

## Flujo de prueba

1. Registrate o inicia sesion.
2. Crea un dispositivo con capacidad `20 Wh`.
3. Agrega actividades:
   - WhatsApp, 30 min, 2 W.
   - YouTube, 60 min, 4 W.
   - Videojuego, 60 min, 6 W.
4. Ejecuta el analisis.
5. Revisa energia consumida, porcentaje de bateria, graficas y recomendacion.
