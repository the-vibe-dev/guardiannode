import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import SeverityBadge from "../components/SeverityBadge";
import { formatDateTime } from "../utils/datetime";

export default function RiskFeed() {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [devices, setDevices] = useState<any[]>([]);
  const [profiles, setProfiles] = useState<any[]>([]);
  const [severity, setSeverity] = useState<string>("");
  const [status, setStatus] = useState<string>("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    api.devices().then(setDevices).catch(() => {});
    api.profiles().then(setProfiles).catch(() => {});
  }, []);

  useEffect(() => {
    const params: Record<string, string> = {};
    if (severity) params.severity = severity;
    if (status) params.status = status;
    api.alerts(params).then(setAlerts);
  }, [severity, status]);

  const deviceName = useMemo(() => {
    const m = new Map(devices.map((d) => [d.device_id, d.hostname]));
    return (id: string | null) => (id ? m.get(id) || id : "—");
  }, [devices]);

  const childName = useMemo(() => {
    const m = new Map(profiles.map((p) => [p.profile_id, p.display_name]));
    return (id: string | null) => (id ? m.get(id) || null : null);
  }, [profiles]);

  const filtered = alerts.filter((a) => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return [
      a.alert_id, a.device_id, a.profile_id, a.status, a.severity,
      a.summary, a.app_name, deviceName(a.device_id), childName(a.profile_id),
      ...(a.categories || []),
    ]
      .filter(Boolean)
      .some((v) => String(v).toLowerCase().includes(q));
  });

  const openCount = alerts.filter((a) => a.status === "open").length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-2xl font-bold">Risk feed</h1>
          {openCount > 0 && (
            <span className="rounded-full bg-red-100 text-red-800 text-xs font-semibold px-2 py-0.5">
              {openCount} open
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-2 text-sm">
          {["", "critical", "high", "medium", "low"].map((s) => (
            <button key={s || "all"}
                    onClick={() => setSeverity(s)}
                    className={`px-2 py-1 rounded ${severity === s ? "bg-brand-700 text-white" : "bg-white border"}`}>
              {s || "All"}
            </button>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap gap-2 text-sm">
        {["", "open", "reviewed", "false_positive", "escalated", "dismissed"].map((s) => (
          <button
            key={s || "any"}
            onClick={() => setStatus(s)}
            className={`px-2 py-1 rounded ${status === s ? "bg-brand-700 text-white" : "bg-white border"}`}
          >
            {s ? s.replace("_", " ") : "Any status"}
          </button>
        ))}
        <input
          className="min-w-[220px] flex-1 border rounded px-2 py-1"
          placeholder="Search what happened, app, device, child…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      <div className="overflow-x-auto bg-white shadow rounded">
      <table className="min-w-[860px] w-full">
        <thead className="bg-gray-100 text-left text-xs uppercase text-gray-500">
          <tr>
            <th className="p-3">Severity</th>
            <th className="p-3">What happened</th>
            <th className="p-3">Where</th>
            <th className="p-3">Status</th>
            <th className="p-3">When</th>
            <th className="p-3"></th>
          </tr>
        </thead>
        <tbody>
          {filtered.length === 0 && (
            <tr><td colSpan={6} className="p-6 text-center text-gray-500">
              {alerts.length === 0 && !severity && !status
                ? "No alerts yet. When GuardianNode flags something on a monitored device, it appears here."
                : "No alerts in this view."}
            </td></tr>
          )}
          {filtered.map((a) => (
            <tr key={a.alert_id} className="border-t hover:bg-gray-50 align-top">
              <td className="p-3"><SeverityBadge severity={a.severity} /></td>
              <td className="p-3 text-sm max-w-md">
                <div className="line-clamp-2">
                  {(a.repeat_count || 1) > 1 && (
                    <span
                      className="mr-1.5 inline-block rounded-full bg-orange-100 text-orange-800 text-xs font-semibold px-1.5 py-0.5 align-middle"
                      title={`Seen ${a.repeat_count} times — identical findings are folded into this alert`}
                    >
                      ×{a.repeat_count}
                    </span>
                  )}
                  {a.summary || <em className="text-gray-400">(no summary)</em>}
                </div>
                {(a.categories || []).length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {a.categories.slice(0, 3).map((c: string) => (
                      <span key={c} className="rounded bg-gray-100 text-gray-600 text-xs px-1.5 py-0.5">
                        {c.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                )}
              </td>
              <td className="p-3 text-sm">
                <div className="font-medium">{a.app_name || "—"}</div>
                <div className="text-xs text-gray-500">
                  {deviceName(a.device_id)}
                  {childName(a.profile_id) ? ` · ${childName(a.profile_id)}` : ""}
                </div>
              </td>
              <td className="p-3 text-sm whitespace-nowrap">{a.status.replace("_", " ")}</td>
              <td className="p-3 text-sm text-gray-500 whitespace-nowrap">
                {formatDateTime(a.created_at)}
                {(a.repeat_count || 1) > 1 && a.last_seen_at && (
                  <div className="text-xs text-gray-400">last {formatDateTime(a.last_seen_at)}</div>
                )}
              </td>
              <td className="p-3 text-right">
                <Link to={`/alerts/${a.alert_id}`} className="text-brand-700 underline text-sm">Review</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
}
