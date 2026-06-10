import { useEffect, useState } from "react";
import { api } from "../api";

const retentionKeys = ["critical", "high", "medium", "low", "none", "screenshots_flagged", "audit_logs"];

export default function Settings() {
  const [notifications, setNotifications] = useState<any>(null);
  const [retention, setRetention] = useState<any>(null);
  const [storage, setStorage] = useState<any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function reload() {
    const [n, r, s] = await Promise.all([
      api.notificationSettings(),
      api.retentionSettings(),
      api.storage(),
    ]);
    setNotifications({ ...n, password: "" });
    setRetention(r);
    setStorage(s);
  }

  useEffect(() => {
    reload().catch((e) => setErr(e.message));
  }, []);

  async function run(label: string, fn: () => Promise<any>, done: string) {
    setBusy(label);
    setErr(null);
    setMsg(null);
    try {
      await fn();
      await reload();
      setMsg(done);
    } catch (e: any) {
      setErr(e.message || String(e));
    } finally {
      setBusy(null);
    }
  }

  if (!notifications || !retention || !storage) {
    return <div className="text-gray-500">Loading settings…</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Settings</h1>
        <div className="text-xs text-gray-500">v0.1.0 beta</div>
      </div>

      {err && <div className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm">{err}</div>}
      {msg && <div className="bg-green-50 border border-green-200 text-green-700 rounded p-3 text-sm">{msg}</div>}

      <section className="bg-white shadow rounded p-4 space-y-3">
        <h2 className="font-semibold">Notifications</h2>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={notifications.enabled}
              onChange={(e) => setNotifications({ ...notifications, enabled: e.target.checked })}
            />
            Email alerts enabled
          </label>
          <Field label="SMTP host" value={notifications.host} onChange={(host) => setNotifications({ ...notifications, host })} />
          <Field label="Port" type="number" value={String(notifications.port)} onChange={(port) => setNotifications({ ...notifications, port: Number(port) })} />
          <label className="text-sm">
            <span className="text-xs text-gray-500">TLS mode</span>
            <select
              className="mt-1 w-full border rounded px-2 py-1"
              value={notifications.tls_mode}
              onChange={(e) => setNotifications({ ...notifications, tls_mode: e.target.value })}
            >
              <option value="starttls">STARTTLS</option>
              <option value="ssl">SSL</option>
              <option value="none">None</option>
            </select>
          </label>
          <Field label="Username" value={notifications.username} onChange={(username) => setNotifications({ ...notifications, username })} />
          <Field label={notifications.password_configured ? "New password (optional)" : "Password"} type="password" value={notifications.password || ""} onChange={(password) => setNotifications({ ...notifications, password })} />
          <Field label="From address" value={notifications.from_address} onChange={(from_address) => setNotifications({ ...notifications, from_address })} />
          <Field label="To address" value={notifications.to_address} onChange={(to_address) => setNotifications({ ...notifications, to_address })} />
          <div className="md:col-span-2">
            <Field
              label="Webhook URL (ntfy / Gotify / generic)"
              value={notifications.webhook_url}
              onChange={(webhook_url) => setNotifications({ ...notifications, webhook_url })}
            />
            <p className="mt-1 text-xs text-gray-400">
              Optional. A JSON POST is sent to this local/self-hosted URL for immediate-severity alerts.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => run("save-notifications", () => api.updateNotificationSettings(notifications), "Notification settings saved.")}
            disabled={busy !== null}
            className="bg-brand-500 hover:bg-brand-700 disabled:opacity-50 text-white px-3 py-2 rounded text-sm"
          >
            Save notifications
          </button>
          <button
            onClick={() => run("test-notifications", api.testNotificationSettings, "Test notification attempted; see audit for result.")}
            disabled={busy !== null}
            className="bg-gray-100 hover:bg-gray-200 disabled:opacity-50 text-gray-800 px-3 py-2 rounded text-sm"
          >
            Send test
          </button>
        </div>
      </section>

      <section className="bg-white shadow rounded p-4 space-y-3">
        <h2 className="font-semibold">Retention</h2>
        <p className="text-xs text-gray-500">
          How many days to keep each kind of data before automatic cleanup. 0 means delete as soon as the cleanup runs.
        </p>
        <div className="grid gap-3 md:grid-cols-4">
          {retentionKeys.map((key) => (
            <Field
              key={key}
              label={`${key.replace(/_/g, " ")} (days)`}
              type="number"
              value={String(retention[key] ?? 0)}
              onChange={(value) => setRetention({ ...retention, [key]: Number(value) })}
            />
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => run("save-retention", () => api.updateRetentionSettings(retention), "Retention settings saved.")}
            disabled={busy !== null}
            className="bg-brand-500 hover:bg-brand-700 disabled:opacity-50 text-white px-3 py-2 rounded text-sm"
          >
            Save retention
          </button>
          <button
            onClick={() => run("cleanup", api.runRetentionCleanup, "Cleanup completed.")}
            disabled={busy !== null}
            className="bg-gray-100 hover:bg-gray-200 disabled:opacity-50 text-gray-800 px-3 py-2 rounded text-sm"
          >
            Run cleanup
          </button>
        </div>
      </section>

      <section className="bg-white shadow rounded p-4 space-y-3">
        <h2 className="font-semibold">Storage</h2>
        <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
          <Stat label="Alerts" value={storage.alerts} />
          <Stat label="Events" value={storage.events} />
          <Stat label="Evidence" value={fmtBytes(storage.evidence_bytes)} />
          <Stat label="Exports" value={fmtBytes(storage.export_bytes)} />
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => run("export", api.exportStorage, "Encrypted export created.")}
            disabled={busy !== null}
            className="bg-brand-500 hover:bg-brand-700 disabled:opacity-50 text-white px-3 py-2 rounded text-sm"
          >
            Export encrypted ZIP
          </button>
          <button
            onClick={() => run("wipe-screenshots", () => api.wipeStorage({ screenshots: true }), "Screenshots wiped.")}
            disabled={busy !== null}
            className="bg-red-50 hover:bg-red-100 disabled:opacity-50 text-red-700 border border-red-200 px-3 py-2 rounded text-sm"
          >
            Wipe screenshots
          </button>
        </div>
      </section>
    </div>
  );
}

function Field({ label, value, onChange, type = "text" }: { label: string; value: string; onChange: (value: string) => void; type?: string }) {
  return (
    <label className="text-sm">
      <span className="text-xs capitalize text-gray-500">{label}</span>
      <input
        type={type}
        className="mt-1 w-full border rounded px-2 py-1"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-gray-50 rounded p-3">
      <div className="text-xs uppercase text-gray-500">{label}</div>
      <div className="font-semibold">{value}</div>
    </div>
  );
}

function fmtBytes(n: number) {
  if (!n) return "0 B";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
