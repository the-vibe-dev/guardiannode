import { useEffect, useState } from "react";
import { api } from "../api";

const retentionKeys = ["critical", "high", "medium", "low", "none", "screenshots_flagged", "audit_logs"];

// One-click SMTP presets so a parent doesn't have to look up server settings.
const MAIL_PROVIDERS: Record<string, { host?: string; port?: number; tls_mode?: string; note?: string }> = {
  gmail: {
    host: "smtp.gmail.com", port: 587, tls_mode: "starttls",
    note: "Gmail blocks your normal password. Turn on 2-Step Verification, then create an App Password (Google Account → Security → App passwords) and paste that as the password.",
  },
  outlook: {
    host: "smtp-mail.outlook.com", port: 587, tls_mode: "starttls",
    note: "Use your full Outlook/Hotmail address as the username. If you have 2-step verification on, create an app password.",
  },
  yahoo: {
    host: "smtp.mail.yahoo.com", port: 465, tls_mode: "ssl",
    note: "Yahoo requires an App Password (Account Security → Generate app password).",
  },
  icloud: {
    host: "smtp.mail.me.com", port: 587, tls_mode: "starttls",
    note: "iCloud Mail requires an app-specific password (appleid.apple.com → Sign-In and Security → App-Specific Passwords).",
  },
  custom: { note: "Enter your provider's SMTP host, port, and TLS mode below." },
};

function applyMailProvider(provider: string, current: any, set: (n: any) => void) {
  const p = MAIL_PROVIDERS[provider];
  if (!p) { set({ ...current, _provider: provider }); return; }
  set({
    ...current,
    _provider: provider,
    enabled: true,
    ...(p.host !== undefined ? { host: p.host } : {}),
    ...(p.port !== undefined ? { port: p.port } : {}),
    ...(p.tls_mode !== undefined ? { tls_mode: p.tls_mode } : {}),
  });
}

export default function Settings() {
  const [notifications, setNotifications] = useState<any>(null);
  const [retention, setRetention] = useState<any>(null);
  const [storage, setStorage] = useState<any>(null);
  const [exportsList, setExportsList] = useState<any[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function reload() {
    const [n, r, s, e] = await Promise.all([
      api.notificationSettings(),
      api.retentionSettings(),
      api.storage(),
      api.exports(),
    ]);
    setNotifications({ ...n, password: "" });
    setRetention(r);
    setStorage(s);
    setExportsList(e);
  }

  useEffect(() => {
    reload().catch((e) => setErr(e.message));
  }, []);

  async function run(label: string, fn: () => Promise<any>, done: string | ((result: any) => string)) {
    setBusy(label);
    setErr(null);
    setMsg(null);
    try {
      const result = await fn();
      await reload();
      setMsg(typeof done === "function" ? done(result) : done);
    } catch (e: any) {
      setErr(e.message || String(e));
    } finally {
      setBusy(null);
    }
  }

  function notificationPayload(clearPassword = false) {
    const { _provider, password, ...n } = notifications;
    const payload: any = { ...n };
    if (clearPassword) {
      payload.clear_password = true;
    } else if (password && password.trim()) {
      payload.password = password;
    }
    return payload;
  }

  if (!notifications || !retention || !storage) {
    return <div className="text-gray-500">Loading settings…</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Settings</h1>
        <div className="text-xs text-gray-500">v0.1.0-alpha.1 alpha</div>
      </div>

      {err && <div className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm">{err}</div>}
      {msg && <div className="bg-green-50 border border-green-200 text-green-700 rounded p-3 text-sm">{msg}</div>}

      <section className="bg-white shadow rounded p-4 space-y-3">
        <h2 className="font-semibold">Email alerts</h2>
        <div className="rounded bg-brand-50 border border-brand-100 p-3 text-sm">
          <label className="block">
            <span className="text-xs text-gray-600 font-medium">Quick setup — pick your email provider</span>
            <select
              className="mt-1 w-full border rounded px-2 py-1"
              value={notifications._provider || ""}
              onChange={(e) => applyMailProvider(e.target.value, notifications, setNotifications)}
            >
              <option value="">Choose a provider…</option>
              <option value="gmail">Gmail</option>
              <option value="outlook">Outlook / Hotmail</option>
              <option value="yahoo">Yahoo Mail</option>
              <option value="icloud">iCloud Mail</option>
              <option value="custom">Other / custom SMTP</option>
            </select>
          </label>
          {MAIL_PROVIDERS[notifications._provider]?.note && (
            <p className="mt-2 text-xs text-gray-600">{MAIL_PROVIDERS[notifications._provider].note}</p>
          )}
        </div>
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
              Optional. A JSON POST is sent for immediate-severity alerts.
            </p>
            <label className="mt-2 flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={Boolean(notifications.webhook_allow_private)}
                onChange={(e) => setNotifications({ ...notifications, webhook_allow_private: e.target.checked })}
              />
              Allow private/internal webhook URL
            </label>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => run("save-notifications", () => api.updateNotificationSettings(notificationPayload()), "Notification settings saved.")}
            disabled={busy !== null}
            className="bg-brand-500 hover:bg-brand-700 disabled:opacity-50 text-white px-3 py-2 rounded text-sm"
          >
            Save notifications
          </button>
          {notifications.password_configured && (
            <button
              onClick={() => {
                if (!window.confirm("Remove the saved SMTP password?")) return;
                run("clear-password", () => api.updateNotificationSettings(notificationPayload(true)), "Saved SMTP password removed.");
              }}
              disabled={busy !== null}
              className="bg-red-50 hover:bg-red-100 disabled:opacity-50 text-red-700 border border-red-200 px-3 py-2 rounded text-sm"
            >
              Remove saved password
            </button>
          )}
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
            onClick={() => run("export", api.exportStorage, "Encrypted .gnexport created.")}
            disabled={busy !== null}
            className="bg-brand-500 hover:bg-brand-700 disabled:opacity-50 text-white px-3 py-2 rounded text-sm"
          >
            Export encrypted .gnexport
          </button>
          <button
            onClick={() => {
              if (!window.confirm("Wipe retained screenshots? This cannot be undone.")) return;
              run("wipe-screenshots", () => api.wipeStorage({ screenshots: true }), "Screenshots wiped.");
            }}
            disabled={busy !== null}
            className="bg-red-50 hover:bg-red-100 disabled:opacity-50 text-red-700 border border-red-200 px-3 py-2 rounded text-sm"
          >
            Wipe screenshots
          </button>
        </div>
        {exportsList.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-[640px] w-full text-sm">
              <thead className="text-left text-xs uppercase text-gray-500">
                <tr>
                  <th className="py-2 pr-3">Export</th>
                  <th className="py-2 pr-3">Created</th>
                  <th className="py-2 pr-3">Size</th>
                  <th className="py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {exportsList.map((item) => (
                  <tr key={item.export_id} className="border-t">
                    <td className="py-2 pr-3 font-mono text-xs">{item.filename}</td>
                    <td className="py-2 pr-3">{fmtDate(item.created_at)}</td>
                    <td className="py-2 pr-3">{fmtBytes(item.size_bytes)}</td>
                    <td className="py-2">
                      <div className="flex flex-wrap gap-2">
                        <a
                          href={item.download_url}
                          download={item.filename}
                          className="bg-gray-100 hover:bg-gray-200 text-gray-800 px-2 py-1 rounded text-xs"
                        >
                          Download
                        </a>
                        <button
                          onClick={() => {
                            if (!window.confirm("Delete this export?")) return;
                            run("delete-export", () => api.deleteExport(item.export_id), "Export deleted.");
                          }}
                          disabled={busy !== null}
                          className="bg-red-50 hover:bg-red-100 disabled:opacity-50 text-red-700 border border-red-200 px-2 py-1 rounded text-xs"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
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

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString();
}
