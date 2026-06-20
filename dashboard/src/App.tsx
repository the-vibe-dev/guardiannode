import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "./api";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Setup from "./pages/Setup";
import Dashboard from "./pages/Dashboard";
import Devices from "./pages/Devices";
import Profiles from "./pages/Profiles";
import RiskFeed from "./pages/RiskFeed";
import AlertDetail from "./pages/AlertDetail";
import ModelStatus from "./pages/ModelStatus";
import Settings from "./pages/Settings";
import Audit from "./pages/Audit";

type AuthState = "unknown" | "needs_setup" | "logged_out" | "logged_in";

export default function App() {
  const [auth, setAuth] = useState<AuthState>("unknown");
  const [me, setMe] = useState<{ display_name: string; role: string } | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    (async () => {
      try {
        const status = await api.setupStatus();
        if (!status.completed) {
          setAuth("needs_setup");
          return;
        }
        try {
          const m = await api.me();
          setMe(m);
          setAuth("logged_in");
        } catch {
          setAuth("logged_out");
        }
      } catch {
        setAuth("logged_out");
      }
    })();
  }, []);

  async function onLogout() {
    await api.logout();
    setMe(null);
    setAuth("logged_out");
    navigate("/login");
  }

  if (auth === "unknown") {
    return (
      <div className="flex h-screen items-center justify-center text-gray-500">
        Loading…
      </div>
    );
  }

  if (auth === "needs_setup") {
    return (
      <Routes>
        <Route path="/setup" element={<Setup onComplete={() => setAuth("logged_in")} />} />
        <Route path="*" element={<Navigate to="/setup" replace />} />
      </Routes>
    );
  }

  if (auth === "logged_out") {
    return (
      <Routes>
        <Route path="/login" element={<Login onLogin={(u) => { setMe(u); setAuth("logged_in"); navigate("/"); }} />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <Layout user={me!} onLogout={onLogout}>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/devices" element={<Devices />} />
        <Route path="/profiles" element={<Profiles />} />
        <Route path="/risks" element={<RiskFeed />} />
        <Route path="/alerts/:id" element={<AlertDetail />} />
        <Route path="/models" element={<ModelStatus />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/audit" element={<Audit />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
