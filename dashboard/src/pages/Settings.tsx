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
  const [backups, setBackups] = useState<any>(null);
  const [guardianReview, setGuardianReview] = useState<any>(null);
  const [codexLogin, setCodexLogin] = useState<any>(null);
  const [exportsList, setExportsList] = useState<any[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function reload() {
    const [n, r, s, e, b, g] = await Promise.all([
      api.notificationSettings(),
      api.retentionSettings(),
      api.storage(),
      api.exports(),
      api.backupSettings(),
      api.guardianReviewProviders(),
    ]);
    setNotifications({ ...n, password: "" });
    setRetention(r);
    setStorage(s);
    setExportsList(e);
    setBackups(b);
    setGuardianReview(g);
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

  async function connectCodex() {
    setBusy("connect-codex");
    setErr(null);
    setMsg(null);
    try {
      let login = await api.startCodexLogin();
      setCodexLogin(login);
      while (login.session_id && ["starting", "waiting"].includes(login.status)) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        login = await api.codexLoginStatus(login.session_id);
        setCodexLogin(login);
      }
      await reload();
      if (login.status === "connected") setMsg("GuardianNode is connected to ChatGPT through Codex.");
      else if (login.status !== "cancelled") setErr("ChatGPT connection did not complete. You can try again safely.");
    } catch (e: any) {
      setErr(e.message || String(e));
    } finally {
      setBusy(null);
    }
  }

  if (!notifications || !retention || !storage || !backups || !guardianReview) {
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
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">Guardian Review</h2>
          <span className={`text-xs font-semibold rounded-full px-2 py-1 ${guardianReview.ready ? "bg-green-100 text-green-800" : guardianReview.enabled ? "bg-amber-100 text-amber-800" : "bg-gray-100 text-gray-600"}`}>
            {guardianReview.ready ? "Ready" : guardianReview.enabled ? "Setup required" : "Not enabled"}
          </span>
        </div>
        <p className="text-sm text-gray-600">
          Guardian Review gives a structured second opinion and conversation guidance. You always review the exact minimized data before anything is sent.
        </p>
        <div className="grid gap-2 text-sm md:grid-cols-3">
          <Stat label="Provider" value={guardianReview.selected === "codex" ? "ChatGPT / Codex" : guardianReview.selected} />
          <Stat label="Model" value={guardianReview.model} />
          <Stat label="Connection" value={guardianReview.providers.codex.connected ? "Connected" : guardianReview.providers.codex.installed ? "Sign-in required" : "Codex required"} />
        </div>
        {guardianReview.selected === "codex" && !guardianReview.providers.codex.installed && (
          <div className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            Install the official Codex CLI on this Windows parent device, then return here. GuardianNode never asks you to paste an API key.
          </div>
        )}
        {codexLogin?.verification_url && ["starting", "waiting"].includes(codexLogin.status) && (
          <div className="rounded border border-brand-200 bg-brand-50 p-3 text-sm space-y-2">
            <p>Open the secure sign-in page and enter this temporary code:</p>
            {codexLogin.user_code && <div className="font-mono text-lg font-semibold tracking-wider">{codexLogin.user_code}</div>}
            <a className="inline-block text-brand-700 underline" href={codexLogin.verification_url} target="_blank" rel="noreferrer">Continue with ChatGPT</a>
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <button
            onClick={connectCodex}
            disabled={busy !== null || !guardianReview.enabled || !guardianReview.providers.codex.installed || guardianReview.providers.codex.connected}
            className="bg-brand-500 hover:bg-brand-700 disabled:opacity-50 text-white px-3 py-2 rounded text-sm"
          >
            {guardianReview.providers.codex.connected ? "Connected to ChatGPT" : busy === "connect-codex" ? "Waiting for sign-in…" : "Connect with ChatGPT"}
          </button>
          {codexLogin?.session_id && ["starting", "waiting"].includes(codexLogin.status) && (
            <button
              onClick={async () => {
                await api.cancelCodexLogin(codexLogin.session_id);
                setCodexLogin({ ...codexLogin, status: "cancelled" });
              }}
              className="bg-gray-100 hover:bg-gray-200 text-gray-800 px-3 py-2 rounded text-sm"
            >Cancel</button>
          )}
        </div>
        <p className="text-xs text-gray-500">
          ChatGPT-connected reviews follow your ChatGPT plan or workspace data controls. Direct API mode is an advanced server option and is not shown to families.
        </p>
        <div className="rounded border bg-gray-50 p-3 text-xs text-gray-700 space-y-1">
          <p>{guardianReview.disclosure}</p>
          <p>{guardianReview.retention_notice}</p>
        </div>
      </section>

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
        <h2 className="font-semibold">Complete recovery backups</h2>
        <p className="text-xs text-gray-500">
          Includes the database, evidence, configuration, versions, and recoverable key material. Keep the recovery private key offline.
        </p>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={Boolean(backups.config.enabled)}
            onChange={(e) => setBackups({ ...backups, config: { ...backups.config, enabled: e.target.checked } })}
          />
          Scheduled complete backups enabled
        </label>
        <div className="grid gap-3 md:grid-cols-3">
          <Field label="Destination path" value={backups.config.destination} onChange={(destination) => setBackups({ ...backups, config: { ...backups.config, destination } })} />
          <Field label="Retention count" type="number" value={String(backups.config.retention_count)} onChange={(value) => setBackups({ ...backups, config: { ...backups.config, retention_count: Number(value) } })} />
          <Field label="Interval (seconds)" type="number" value={String(backups.config.interval_seconds)} onChange={(value) => setBackups({ ...backups, config: { ...backups.config, interval_seconds: Number(value) } })} />
        </div>
        <label className="block text-sm">
          <span className="text-xs text-gray-500">Offline X25519 recovery public key (PEM)</span>
          <textarea
            className="mt-1 w-full border rounded px-2 py-1 font-mono text-xs"
            rows={4}
            value={backups.config.recipient_public_key || ""}
            onChange={(e) => setBackups({ ...backups, config: { ...backups.config, recipient_public_key: e.target.value } })}
          />
        </label>
        <div className="grid gap-2 text-sm md:grid-cols-4">
          <Stat label="Recovery key" value={backups.config.recipient_configured ? "Configured" : "Missing"} />
          <Stat label="Last complete" value={backups.runs[0]?.completed_at ? fmtDate(backups.runs[0].completed_at) : "Never"} />
          <Stat label="Last verified" value={backupDate(backups.runs, "verified_at")} />
          <Stat label="Last restore test" value={backupDate(backups.runs, "restore_tested_at")} />
        </div>
        {backups.runs[0]?.status === "failed" && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded p-2 text-sm">
            Last backup failed: {backups.runs[0].error_detail || backups.runs[0].error_code}
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => run("save-backups", () => api.updateBackupSettings(backups.config), "Complete backup settings saved.")}
            disabled={busy !== null}
            className="bg-brand-500 hover:bg-brand-700 disabled:opacity-50 text-white px-3 py-2 rounded text-sm"
          >
            Save backup settings
          </button>
          <button
            onClick={() => run("run-backup", api.runCompleteBackup, "Complete backup created and verified.")}
            disabled={busy !== null || !backups.config.enabled}
            className="bg-gray-100 hover:bg-gray-200 disabled:opacity-50 text-gray-800 px-3 py-2 rounded text-sm"
          >
            Back up now
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
            onClick={() => run("export", api.exportStorage, "Complete encrypted .gna snapshot created.")}
            disabled={busy !== null}
            className="bg-brand-500 hover:bg-brand-700 disabled:opacity-50 text-white px-3 py-2 rounded text-sm"
          >
            Create complete .gna snapshot
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

function backupDate(runs: any[], field: string) {
  const value = runs.find((run) => run[field])?.[field];
  return value ? fmtDate(value) : "Never";
}
