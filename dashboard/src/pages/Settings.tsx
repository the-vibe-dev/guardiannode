import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, type NotificationTestResult } from "../api";
import NotificationDelivery from "../components/NotificationDelivery";
import CaptureQueue from "../components/CaptureQueue";

type SettingsSection = "notifications" | "retention" | "storage" | "exports" | "backups" | "guardianReview" | "familyLocale";
const settingsSections: SettingsSection[] = ["notifications", "retention", "storage", "exports", "backups", "guardianReview", "familyLocale"];
const sectionTitles: Record<SettingsSection, string> = {
  notifications: "Email alerts", retention: "Retention", storage: "Storage", exports: "Exports",
  backups: "Complete recovery backups", guardianReview: "Guardian Review", familyLocale: "Family time",
};

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
  const queryClient = useQueryClient();
  const [notifications, setNotifications] = useState<any>(null);
  const [retention, setRetention] = useState<any>(null);
  const [storage, setStorage] = useState<any>(null);
  const [backups, setBackups] = useState<any>(null);
  const [backupEnabled, setBackupEnabled] = useState(false);
  const [guardianReview, setGuardianReview] = useState<any>(null);
  const [familyLocale, setFamilyLocale] = useState<{ timezone: string } | null>(null);
  const [exportsList, setExportsList] = useState<any[] | null>(null);
  const [loadErrors, setLoadErrors] = useState<Partial<Record<SettingsSection, string>>>({});
  const [loading, setLoading] = useState<Partial<Record<SettingsSection, boolean>>>({});
  const loadSequence = useRef<Partial<Record<SettingsSection, number>>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<NotificationTestResult | null>(null);

  async function loadSection(section: SettingsSection, isActive = () => true, preserveDraft = false) {
    const sequence = (loadSequence.current[section] ?? 0) + 1;
    loadSequence.current[section] = sequence;
    setLoading((current) => ({ ...current, [section]: true }));
    setLoadErrors((current) => ({ ...current, [section]: undefined }));
    const loaders = {
      notifications: api.notificationSettings, retention: api.retentionSettings, storage: api.storage,
      exports: api.exports, backups: api.backupSettings, guardianReview: api.guardianReviewProviders,
      familyLocale: api.familyLocale,
    };
    try {
      const result = await loaders[section]();
      if (!isActive() || loadSequence.current[section] !== sequence) return;
      switch (section) {
        case "notifications": setNotifications({ ...result, password: "" }); break;
        case "retention": setRetention(result); break;
        case "storage": setStorage(result); break;
        case "exports": setExportsList(result as any[]); break;
        case "backups": setBackupEnabled(Boolean(result.config.enabled)); setBackups((current: any) => preserveDraft && current ? { ...result, config: current.config } : result); break;
        case "guardianReview": setGuardianReview(result); break;
        case "familyLocale": setFamilyLocale(result as { timezone: string }); break;
      }
    } catch (error) {
      if (isActive() && loadSequence.current[section] === sequence) setLoadErrors((current) => ({ ...current, [section]: error instanceof Error ? error.message : "Request failed" }));
    } finally {
      if (isActive() && loadSequence.current[section] === sequence) setLoading((current) => ({ ...current, [section]: false }));
    }
  }

  useEffect(() => {
    let active = true;
    for (const section of settingsSections) void loadSection(section, () => active);
    return () => { active = false; };
  }, []);

  async function run(label: string, fn: () => Promise<any>, done: string | ((result: any) => string), onSuccess?: (result: any) => void | Promise<void>) {
    setBusy(label);
    setErr(null);
    setMsg(null);
    try {
      const result = await fn();
      if (onSuccess) await onSuccess(result);
      if (["save-notifications", "clear-password"].includes(label)) void queryClient.invalidateQueries({ queryKey: ["notification-status"] });
      setMsg(typeof done === "function" ? done(result) : done);
    } catch (e: any) {
      setErr(e.message || String(e));
    } finally {
      setBusy(null);
    }
  }

  async function refreshStorage() {
    await Promise.all([loadSection("storage"), loadSection("exports")]);
  }

  function loadState(section: SettingsSection) {
    return <SettingsLoadState title={sectionTitles[section]} error={loadErrors[section]} loading={Boolean(loading[section])} onRetry={() => void loadSection(section)} />;
  }

  async function sendTest() {
    setBusy("test-notifications");
    setErr(null);
    setTestResult(null);
    try {
      setTestResult(await api.testNotificationSettings());
      void queryClient.invalidateQueries({ queryKey: ["notification-status"] });
    } catch (error) {
      setErr(error instanceof Error ? error.message : "Could not send the notification test");
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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Settings</h1>
        <div className="text-xs text-gray-500">v0.1.0-alpha.3 alpha</div>
      </div>

      {err && <div role="alert" className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm">{err}</div>}
      {msg && <div role="status" className="bg-green-50 border border-green-200 text-green-700 rounded p-3 text-sm">{msg}</div>}

      {familyLocale ? (
      <section className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
        <fieldset disabled={busy === "save-timezone"} className="min-w-0 space-y-3">
        <h2 className="font-display font-semibold">Family time</h2>
        <p className="text-sm text-slate-600">Daily summaries use this IANA timezone, including across daylight-saving changes.</p>
        <div className="flex flex-wrap items-end gap-3"><Field label="Timezone (for example America/New_York)" value={familyLocale.timezone} onChange={(timezone) => setFamilyLocale({ timezone })} /><button onClick={() => run("save-timezone", () => api.updateFamilyLocale(familyLocale.timezone), "Family timezone saved.", setFamilyLocale)} disabled={busy !== null} className="min-h-10 rounded bg-brand-500 px-3 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50">Save timezone</button></div>

        </fieldset>
      </section>
      ) : loadState("familyLocale")}

      {guardianReview ? (
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
          <Stat label="Connection" value={guardianReview.selected === "codex" && guardianReview.providers.codex.security_hold ? "Temporarily unavailable" : guardianReview.ready ? "Ready" : "Setup required"} />
        </div>
        {guardianReview.selected === "codex" && guardianReview.providers.codex.security_hold && (
          <div role="status" className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950 space-y-1">
            <p className="font-medium">ChatGPT/Codex sign-in is temporarily unavailable for incident review.</p>
            <p>
              Codex is a coding agent with local tools. GuardianNode will not send family incident evidence through it until a zero-tool privacy boundary can be enforced. Mock demo mode remains available; the direct OpenAI Responses API is an advanced server configuration.
            </p>
          </div>
        )}
        <p className="text-xs text-gray-500">
          Live direct-API reviews use server-side credentials and the configured account's data controls. GuardianNode does not claim zero retention unless the operator has verified the applicable controls.
        </p>
        <div className="rounded border bg-gray-50 p-3 text-xs text-gray-700 space-y-1">
          <p>{guardianReview.disclosure}</p>
          <p>{guardianReview.retention_notice}</p>
        </div>
      </section>
      ) : loadState("guardianReview")}

      {notifications ? (
      <section className="bg-white shadow rounded p-4 space-y-3">
        <fieldset disabled={busy === "save-notifications" || busy === "clear-password"} className="min-w-0 space-y-3">
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
            Notifications enabled (email & webhook)
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
              label="Generic webhook URL"
              value={notifications.webhook_url}
              onChange={(webhook_url) => setNotifications({ ...notifications, webhook_url })}
            />
            <p className="mt-1 text-xs text-gray-400">
              Optional. GuardianNode sends its own JSON payload. Use a receiver that accepts this format; dedicated ntfy and Gotify adapters are not included.
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
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={Boolean(notifications.daily_digest_enabled)} onChange={(e) => setNotifications({ ...notifications, daily_digest_enabled: e.target.checked })} />
            Send a metadata-only daily digest
          </label>
          <Field label="Daily digest time" type="time" value={notifications.daily_digest_time || "08:00"} onChange={(daily_digest_time) => setNotifications({ ...notifications, daily_digest_time })} />
        </div>
        <div className="space-y-2 rounded-lg border border-slate-200 p-3">
          <label className="block text-sm"><span className="font-medium">Immediate alert threshold</span>
            <select className="mt-1 min-h-10 w-full rounded border border-slate-300 px-2 sm:max-w-xs" value={notifications.immediate_min_severity || "high"} onChange={(event) => setNotifications({ ...notifications, immediate_min_severity: event.target.value })}>
              {["low", "medium", "high", "critical"].map((severity) => <option key={severity} value={severity}>{severity[0].toUpperCase() + severity.slice(1)}{severity !== "critical" ? " and above" : ""}</option>)}
            </select>
          </label>
          <p className="text-xs text-slate-600">This threshold controls new immediate email and webhook jobs. Queued jobs are checked again against the current profile policy and threshold before delivery. Lowering it does not resend historical alerts.</p>
          <p className="text-xs text-slate-600">Categories set to Monitor or Allow remain quiet. Protected safety categories at High or Critical still qualify when this threshold is Critical. The notification switch and Privacy & consent choices still apply.</p>
          <p className="text-xs text-slate-500">The daily digest schedule is separate from the immediate alert threshold.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => run("save-notifications", () => api.updateNotificationSettings(notificationPayload()), "Notification settings saved.", (saved) => { setNotifications({ ...saved, password: "" }); setTestResult(null); })}
            disabled={busy !== null}
            className="bg-brand-500 hover:bg-brand-700 disabled:opacity-50 text-white px-3 py-2 rounded text-sm"
          >
            Save notifications
          </button>
          {notifications.password_configured && (
            <button
              onClick={() => {
                if (!window.confirm("Remove the saved SMTP password?")) return;
                run("clear-password", () => api.updateNotificationSettings(notificationPayload(true)), "Saved SMTP password removed.", (saved) => { setNotifications({ ...saved, password: "" }); setTestResult(null); });
              }}
              disabled={busy !== null}
              className="bg-red-50 hover:bg-red-100 disabled:opacity-50 text-red-700 border border-red-200 px-3 py-2 rounded text-sm"
            >
              Remove saved password
            </button>
          )}
          <button
            onClick={sendTest}
            disabled={busy !== null}
            className="bg-gray-100 hover:bg-gray-200 disabled:opacity-50 text-gray-800 px-3 py-2 rounded text-sm"
          >
            {busy === "test-notifications" ? "Sending test…" : "Send test"}
          </button>
        </div>
        <p className="text-xs text-slate-500">Save notification settings before sending a test. The test uses the saved configuration.</p>
        {testResult && <div role={testResult.ok ? "status" : "alert"} className={`rounded-lg border p-3 text-sm ${testResult.ok ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-red-200 bg-red-50 text-red-900"}`}><p className="font-semibold">{testResult.ok ? "Test accepted by the configured channels" : "A notification test failed"}</p>{testResult.results?.length ? <ul className="mt-2 space-y-1">{testResult.results.map((result) => <li key={result.channel}><strong className="capitalize">{result.channel}: {result.ok ? "accepted" : "failed"}</strong> — {result.detail}</li>)}</ul> : <p>{testResult.detail}</p>}<p className="mt-2 text-xs">Check your inbox or receiving app to confirm arrival.</p></div>}

        </fieldset>
      </section>
      ) : loadState("notifications")}

      <NotificationDelivery />

      <CaptureQueue onCleanup={refreshStorage} />

      {retention ? (
      <section className="bg-white shadow rounded p-4 space-y-3">
        <fieldset disabled={busy === "save-retention"} className="min-w-0 space-y-3">
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
            onClick={() => run("save-retention", () => api.updateRetentionSettings(retention), "Retention settings saved.", setRetention)}
            disabled={busy !== null}
            className="bg-brand-500 hover:bg-brand-700 disabled:opacity-50 text-white px-3 py-2 rounded text-sm"
          >
            Save retention
          </button>
          <button
            onClick={() => run("cleanup", api.runRetentionCleanup, "Cleanup completed.", refreshStorage)}
            disabled={busy !== null}
            className="bg-gray-100 hover:bg-gray-200 disabled:opacity-50 text-gray-800 px-3 py-2 rounded text-sm"
          >
            Run cleanup
          </button>
        </div>

        </fieldset>
      </section>
      ) : loadState("retention")}

      {backups ? (
      <section className="bg-white shadow rounded p-4 space-y-3">
        <fieldset disabled={busy === "save-backups"} className="min-w-0 space-y-3">
        <h2 className="font-semibold">Complete recovery backups</h2>
        {loadErrors.backups && <p role="alert" className="text-sm text-amber-900">Backup history could not refresh: {loadErrors.backups}. Previously loaded history may be out of date. <button className="font-semibold underline" onClick={() => void loadSection("backups", () => true, true)}>Retry backup history</button></p>}
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
            onClick={() => run("save-backups", () => api.updateBackupSettings(backups.config), "Complete backup settings saved.", (config) => { setBackupEnabled(Boolean(config.enabled)); setBackups((current: any) => ({ ...current, config })); })}
            disabled={busy !== null}
            className="bg-brand-500 hover:bg-brand-700 disabled:opacity-50 text-white px-3 py-2 rounded text-sm"
          >
            Save backup settings
          </button>
          <button
            onClick={() => run("run-backup", api.runCompleteBackup, "Complete backup created and verified.", () => loadSection("backups", () => true, true))}
            disabled={busy !== null || !backupEnabled}
            className="bg-gray-100 hover:bg-gray-200 disabled:opacity-50 text-gray-800 px-3 py-2 rounded text-sm"
          >
            Back up now
          </button>
        </div>
        <p className="text-xs text-slate-500">Save backup settings before running a backup. Back up now uses the saved configuration.</p>

        </fieldset>
      </section>
      ) : loadState("backups")}

      {storage ? (
      <section className="bg-white shadow rounded p-4 space-y-3">
        <h2 className="font-semibold">Storage</h2>
        {loadErrors.storage && <p role="alert" className="text-sm text-amber-900">Storage totals could not refresh: {loadErrors.storage}. Previously loaded totals may be out of date. <button className="font-semibold underline" onClick={() => void loadSection("storage")}>Retry Storage</button></p>}
        <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
          <Stat label="Alerts" value={storage.alerts} />
          <Stat label="Events" value={storage.events} />
          <Stat label="Evidence" value={fmtBytes(storage.evidence_bytes)} />
          <Stat label="Exports" value={fmtBytes(storage.export_bytes)} />
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => run("export", api.exportStorage, "Complete encrypted .gna snapshot created.", refreshStorage)}
            disabled={busy !== null}
            className="bg-brand-500 hover:bg-brand-700 disabled:opacity-50 text-white px-3 py-2 rounded text-sm"
          >
            Create complete .gna snapshot
          </button>
          <button
            onClick={() => {
              if (!window.confirm("Attempt to delete retained screenshots? Backups, exports and downloaded copies are not included. Deleted files cannot be recovered by this action.")) return;
              run("wipe-screenshots", () => api.wipeStorage({ screenshots: true }), (result) => `Screenshot deletion attempt finished: ${result.deleted?.blobs ?? 0} retained files removed. Files that could not be removed remain queued for retry. Backups, exports and downloaded copies are not included.`, refreshStorage);
            }}
            disabled={busy !== null}
            className="bg-red-50 hover:bg-red-100 disabled:opacity-50 text-red-700 border border-red-200 px-3 py-2 rounded text-sm"
          >
            Wipe screenshots
          </button>
        </div>
      </section>
      ) : loadState("storage")}

      {exportsList ? (
      <section className="bg-white shadow rounded p-4 space-y-3">
        <h2 className="font-semibold">Exports</h2>
        {loadErrors.exports && <p role="alert" className="text-sm text-amber-900">Export list could not refresh: {loadErrors.exports}. Previously loaded exports may be out of date. <button className="font-semibold underline" onClick={() => void loadSection("exports")}>Retry Exports</button></p>}
        {exportsList.length > 0 ? (
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
                            run("delete-export", () => api.deleteExport(item.export_id), "Export deleted.", refreshStorage);
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
        ) : <p className="text-sm text-slate-500">No saved exports.</p>}
      </section>
      ) : loadState("exports")}
    </div>
  );
}

function SettingsLoadState({ title, error, loading, onRetry }: { title: string; error?: string; loading: boolean; onRetry: () => void }) {
  return <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
    <h2 className="font-semibold">{title}</h2>
    {error ? <p role="alert" className="text-sm text-red-800">Could not load {title.toLowerCase()}: {error}. <button disabled={loading} className="font-semibold underline disabled:opacity-50" onClick={onRetry}>Retry {title}</button></p> : <p role="status" className="text-sm text-slate-500">Loading {title.toLowerCase()}…</p>}
  </section>;
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
