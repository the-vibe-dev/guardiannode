import { useEffect, useState } from "react";
import { api } from "../api";
import PipelineHealth from "../components/PipelineHealth";

export default function Dashboard() {
  const [overview, setOverview] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.overview().then(setOverview).catch((e) => setError(e.message));
    const t = setInterval(() => api.overview().then(setOverview).catch(() => {}), 15000);
    return () => clearInterval(t);
  }, []);

  if (error) return <div className="text-red-700">{error}</div>;
  if (!overview) return <div className="text-gray-500">Loading…</div>;

  const c24 = overview.counts_24h;
  const c7d = overview.counts_7d;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Overview</h1>

      {/* Live pipeline status — polls every 2s */}
      <PipelineHealth />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card label="Critical (24h)" value={c24.critical} severity="critical" />
        <Card label="High (24h)" value={c24.high} severity="high" />
        <Card label="Medium (24h)" value={c24.medium} severity="medium" />
        <Card label="Open alerts" value={overview.open_alert_count} />
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card label="Devices total" value={overview.devices_total} />
        <Card label="Online" value={overview.devices_online} positive />
        <Card label="Paused" value={overview.devices_paused} />
      </div>

      <div className="bg-white shadow rounded p-4">
        <h2 className="font-semibold mb-2">Last 7 days</h2>
        <div className="flex flex-wrap gap-4 text-sm">
          <span>Critical: <strong>{c7d.critical}</strong></span>
          <span>High: <strong>{c7d.high}</strong></span>
          <span>Medium: <strong>{c7d.medium}</strong></span>
          <span>Low: <strong>{c7d.low}</strong></span>
        </div>
      </div>
    </div>
  );
}

// Static class names — Tailwind's JIT can't generate dynamically-built ones.
const severityCardClasses: Record<string, string> = {
  critical: "bg-severity-critical/10 border-severity-critical",
  high: "bg-severity-high/10 border-severity-high",
  medium: "bg-severity-medium/10 border-severity-medium",
  low: "bg-severity-low/10 border-severity-low",
};

function Card({ label, value, severity, positive }: { label: string; value: number; severity?: string; positive?: boolean }) {
  const bg = (severity && severityCardClasses[severity]) || (positive ? "bg-green-50 border-green-200" : "bg-white");
  return (
    <div className={`shadow rounded p-4 border ${bg}`}>
      <div className="text-xs uppercase text-gray-500">{label}</div>
      <div className="text-3xl font-bold mt-1">{value}</div>
    </div>
  );
}
