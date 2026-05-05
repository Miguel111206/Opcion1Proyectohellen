import React from "react";
import ReactDOM from "react-dom/client";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { motion } from "framer-motion";
import { BatteryCharging, Cpu, LogOut, Play, Plus, Smartphone, Trash2, Zap } from "lucide-react";
import "./styles.css";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

type User = { id: number; name: string; email: string };
type Device = { id: number; name: string; type: string; battery_capacity_wh: number };
type Activity = {
  id: number;
  app_name: string;
  duration_minutes: number;
  power_watts: number;
  consumption_level: string;
  brightness: string;
  connection_type: string;
  saving_mode: string;
  energy_wh: number;
};
type Analysis = {
  id: number;
  total_energy_wh: number;
  battery_used_percent: number;
  battery_remaining_percent: number;
  highest_consumption_app: string;
  critical_period: string;
  recommendation: string;
  timeline: { time_label: string; hour: number; power_watts: number; battery_remaining: number; app_name: string }[];
  app_energy: { app_name: string; energy_wh: number }[];
};

function readableError(error: unknown): string {
  if (Array.isArray(error)) {
    return error.map((item) => `${item.loc?.slice(1).join(".") || "campo"}: ${item.msg}`).join(" | ");
  }
  if (typeof error === "string") return error;
  if (error && typeof error === "object" && "detail" in error) {
    return readableError((error as { detail: unknown }).detail);
  }
  return "Error inesperado";
}

const presets: Record<string, number> = {
  Reposo: 1,
  WhatsApp: 2,
  Musica: 2.5,
  "Redes sociales": 3,
  YouTube: 4,
  Videollamada: 5,
  Videojuego: 6,
};

function App() {
  const [token, setToken] = React.useState(localStorage.getItem("token") || "");
  const [user, setUser] = React.useState<User | null>(null);
  const [devices, setDevices] = React.useState<Device[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = React.useState<number | null>(null);
  const [activities, setActivities] = React.useState<Activity[]>([]);
  const [analysis, setAnalysis] = React.useState<Analysis | null>(null);
  const [message, setMessage] = React.useState("");

  const authFetch = React.useCallback(
    async (path: string, options: RequestInit = {}) => {
      const response = await fetch(`${API_URL}${path}`, {
        ...options,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
          ...(options.headers || {}),
        },
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Error de conexion" }));
        throw new Error(readableError(error));
      }
      return response.json();
    },
    [token],
  );

  const loadDevices = React.useCallback(async () => {
    if (!token) return;
    const data = await authFetch("/devices");
    setDevices(data);
    if (!selectedDeviceId && data.length) setSelectedDeviceId(data[0].id);
  }, [authFetch, selectedDeviceId, token]);

  const loadActivities = React.useCallback(async () => {
    if (!selectedDeviceId) return;
    const data = await authFetch(`/devices/${selectedDeviceId}/activities`);
    setActivities(data);
  }, [authFetch, selectedDeviceId]);

  React.useEffect(() => {
    if (!token) return;
    authFetch("/auth/me").then(setUser).then(loadDevices).catch(() => logout());
  }, [token]);

  React.useEffect(() => {
    loadActivities().catch((error) => setMessage(error.message));
    setAnalysis(null);
  }, [loadActivities]);

  function logout() {
    localStorage.removeItem("token");
    setToken("");
    setUser(null);
    setDevices([]);
    setActivities([]);
    setAnalysis(null);
  }

  async function handleAuth(payload: { name?: string; email: string; password: string }, mode: "login" | "register") {
    setMessage("");
    const response = await fetch(`${API_URL}/auth/${mode}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      setMessage(readableError(data));
      return;
    }
    localStorage.setItem("token", data.access_token);
    setToken(data.access_token);
    setUser(data.user);
  }

  async function createDevice(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    const form = new FormData(event.currentTarget);
    try {
      const device = await authFetch("/devices", {
        method: "POST",
        body: JSON.stringify({
          name: String(form.get("name") || "").trim(),
          type: String(form.get("type") || "").trim(),
          battery_capacity_wh: Number(form.get("battery_capacity_wh")),
        }),
      });
      setSelectedDeviceId(device.id);
      await loadDevices();
      event.currentTarget.reset();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo crear el dispositivo");
    }
  }

  async function createActivity(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDeviceId) return;
    setMessage("");
    const form = new FormData(event.currentTarget);
    try {
      await authFetch(`/devices/${selectedDeviceId}/activities`, {
        method: "POST",
        body: JSON.stringify({
          app_name: String(form.get("app_name") || "").trim(),
          duration_minutes: Number(form.get("duration_minutes")),
          power_watts: Number(form.get("power_watts")),
          consumption_level: String(form.get("consumption_level") || "Medio"),
          brightness: String(form.get("brightness") || "Medio"),
          connection_type: String(form.get("connection_type") || "WiFi"),
          saving_mode: String(form.get("saving_mode") || "Desactivado"),
        }),
      });
      await loadActivities();
      setAnalysis(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo crear la actividad");
    }
  }

  async function runAnalysis() {
    if (!selectedDeviceId) return;
    setMessage("");
    try {
      const data = await authFetch(`/devices/${selectedDeviceId}/analysis`, { method: "POST", body: "{}" });
      setAnalysis(data);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo ejecutar el analisis");
    }
  }

  async function deleteActivity(id: number) {
    setMessage("");
    try {
      await authFetch(`/activities/${id}`, { method: "DELETE" });
      await loadActivities();
      setAnalysis(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo eliminar la actividad");
    }
  }

  if (!token || !user) return <AuthScreen onSubmit={handleAuth} message={message} />;

  const selectedDevice = devices.find((device) => device.id === selectedDeviceId) || null;

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Analisis inteligente de bateria</p>
          <h1>BatteryCurve AI</h1>
        </div>
        <div className="user-pill">
          <span>{user.name}</span>
          <button onClick={logout} title="Cerrar sesion"><LogOut size={18} /></button>
        </div>
      </header>
      {message && <div className="notice">{message}</div>}

      <section className="grid">
        <motion.aside className="panel side" initial={{ opacity: 0, x: -24 }} animate={{ opacity: 1, x: 0 }}>
          <h2><Smartphone size={20} /> Dispositivos</h2>
          <form onSubmit={createDevice} className="stack">
            <input name="name" placeholder="Nombre del dispositivo" required />
            <select name="type" defaultValue="Celular">
              <option>Celular</option>
              <option>Portatil</option>
              <option>Tablet</option>
            </select>
            <input name="battery_capacity_wh" type="number" step="0.1" min="1" placeholder="Capacidad Wh" required />
            <button className="primary"><Plus size={18} /> Crear</button>
          </form>
          <div className="device-list">
            {devices.map((device) => (
              <button key={device.id} className={device.id === selectedDeviceId ? "device active" : "device"} onClick={() => setSelectedDeviceId(device.id)}>
                <strong>{device.name}</strong>
                <span>{device.type} · {device.battery_capacity_wh} Wh</span>
              </button>
            ))}
          </div>
        </motion.aside>

        <section className="workspace">
          <Summary analysis={analysis} device={selectedDevice} activities={activities} />

          <div className="two">
            <motion.div className="panel" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }}>
              <h2><Cpu size={20} /> Agregar actividad</h2>
              <ActivityForm onSubmit={createActivity} disabled={!selectedDevice} />
            </motion.div>
            <motion.div className="panel" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }}>
              <div className="panel-title">
                <h2><Zap size={20} /> Actividades</h2>
                <button className="primary" onClick={runAnalysis} disabled={!selectedDevice || activities.length === 0}><Play size={18} /> Analizar</button>
              </div>
              <div className="activity-list">
                {activities.map((activity) => (
                  <div className="activity" key={activity.id}>
                    <div>
                      <strong>{activity.app_name}</strong>
                      <span>{activity.duration_minutes} min · {activity.power_watts} W · {activity.energy_wh} Wh</span>
                    </div>
                    <button onClick={() => deleteActivity(activity.id)} title="Eliminar"><Trash2 size={17} /></button>
                  </div>
                ))}
                {!activities.length && <p className="muted">Agrega actividades para construir la curva de potencia.</p>}
              </div>
            </motion.div>
          </div>

          <Charts analysis={analysis} />
        </section>
      </section>
    </main>
  );
}

function AuthScreen({ onSubmit, message }: { onSubmit: (payload: { name?: string; email: string; password: string }, mode: "login" | "register") => void; message: string }) {
  const [mode, setMode] = React.useState<"login" | "register">("register");
  return (
    <main className="auth">
      <motion.section className="auth-card" initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}>
        <BatteryCharging size={42} />
        <h1>BatteryCurve AI</h1>
        <p>Analiza el consumo de bateria con area bajo la curva, graficas y recomendaciones.</p>
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            onSubmit({ name: String(form.get("name") || ""), email: String(form.get("email")), password: String(form.get("password")) }, mode);
          }}
        >
          {mode === "register" && <input name="name" placeholder="Nombre" required />}
          <input name="email" type="email" placeholder="Correo" required />
          <input name="password" type="password" placeholder="Contrasena" minLength={6} required />
          {message && <p className="error">{message}</p>}
          <button className="primary">{mode === "register" ? "Crear cuenta" : "Entrar"}</button>
        </form>
        <button className="link" onClick={() => setMode(mode === "register" ? "login" : "register")}>
          {mode === "register" ? "Ya tengo cuenta" : "Crear cuenta nueva"}
        </button>
      </motion.section>
    </main>
  );
}

function ActivityForm({ onSubmit, disabled }: { onSubmit: (event: React.FormEvent<HTMLFormElement>) => void; disabled: boolean }) {
  const [app, setApp] = React.useState("YouTube");
  return (
    <form className="stack" onSubmit={onSubmit}>
      <select name="app_name" value={app} onChange={(event) => setApp(event.target.value)} disabled={disabled}>
        {Object.keys(presets).map((name) => <option key={name}>{name}</option>)}
      </select>
      <div className="inline">
        <input name="duration_minutes" type="number" min="1" step="1" defaultValue="60" disabled={disabled} />
        <input name="power_watts" type="number" min="0.1" step="0.1" value={presets[app]} onChange={() => null} disabled={disabled} />
      </div>
      <div className="inline">
        <select name="consumption_level" defaultValue="Medio" disabled={disabled}><option>Muy bajo</option><option>Bajo</option><option>Medio</option><option>Alto</option></select>
        <select name="brightness" defaultValue="Medio" disabled={disabled}><option>Bajo</option><option>Medio</option><option>Alto</option></select>
      </div>
      <div className="inline">
        <select name="connection_type" defaultValue="WiFi" disabled={disabled}><option>WiFi</option><option>Datos moviles</option><option>Sin conexion</option></select>
        <select name="saving_mode" defaultValue="Desactivado" disabled={disabled}><option>Activado</option><option>Desactivado</option></select>
      </div>
      <button className="primary" disabled={disabled}><Plus size={18} /> Agregar actividad</button>
    </form>
  );
}

function Summary({ analysis, device, activities }: { analysis: Analysis | null; device: Device | null; activities: Activity[] }) {
  const used = analysis?.battery_used_percent || 0;
  const remaining = analysis?.battery_remaining_percent ?? 100;
  return (
    <section className="summary">
      <motion.div className="metric battery-card" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
        <span>Bateria restante</span>
        <div className="battery"><motion.div animate={{ width: `${Math.min(100, remaining)}%` }} /></div>
        <strong>{remaining.toFixed(1)}%</strong>
      </motion.div>
      <Metric label="Energia consumida" value={`${(analysis?.total_energy_wh || 0).toFixed(2)} Wh`} />
      <Metric label="Bateria consumida" value={`${used.toFixed(1)}%`} />
      <Metric label="Mayor consumo" value={analysis?.highest_consumption_app || (device ? "Pendiente" : "Sin dispositivo")} />
      <Metric label="Actividades" value={String(activities.length)} />
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <motion.div className="metric" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}><span>{label}</span><strong>{value}</strong></motion.div>;
}

function Charts({ analysis }: { analysis: Analysis | null }) {
  if (!analysis) {
    return <section className="panel empty"><BatteryCharging size={36} /><p>Ejecuta un analisis para ver la curva, el area sombreada y la bateria restante.</p></section>;
  }
  return (
    <section className="charts">
      <motion.div className="panel chart" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }}>
        <h2>Potencia vs tiempo y area bajo la curva</h2>
        <ResponsiveContainer width="100%" height={270}>
          <AreaChart data={analysis.timeline}>
            <defs><linearGradient id="power" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#13b981" stopOpacity={0.55} /><stop offset="95%" stopColor="#13b981" stopOpacity={0.02} /></linearGradient></defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#d8e1de" />
            <XAxis dataKey="time_label" />
            <YAxis />
            <Tooltip />
            <Area type="stepAfter" dataKey="power_watts" stroke="#0f8f6f" strokeWidth={3} fill="url(#power)" />
          </AreaChart>
        </ResponsiveContainer>
      </motion.div>
      <motion.div className="panel chart" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }}>
        <h2>Bateria restante</h2>
        <ResponsiveContainer width="100%" height={270}>
          <AreaChart data={analysis.timeline}>
            <CartesianGrid strokeDasharray="3 3" stroke="#d8e1de" />
            <XAxis dataKey="time_label" />
            <YAxis domain={[0, 100]} />
            <Tooltip />
            <Area type="monotone" dataKey="battery_remaining" stroke="#2563eb" strokeWidth={3} fill="#dbeafe" />
          </AreaChart>
        </ResponsiveContainer>
      </motion.div>
      <motion.div className="panel chart" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 }}>
        <h2>Consumo por aplicacion</h2>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={analysis.app_energy}>
            <CartesianGrid strokeDasharray="3 3" stroke="#d8e1de" />
            <XAxis dataKey="app_name" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="energy_wh" fill="#f97316" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </motion.div>
      <motion.div className="panel recommendation" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.16 }}>
        <h2>Recomendacion inteligente</h2>
        <p>{analysis.recommendation}</p>
        <span>Periodo critico: {analysis.critical_period}</span>
      </motion.div>
    </section>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<App />);
