// Typed API client. Uses cookie auth (no token to manage in localStorage).

const API_BASE = "/api";
const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

let cachedCsrfToken: string | null = null;

async function getCsrfToken(): Promise<string> {
  if (cachedCsrfToken) return cachedCsrfToken;
  const res = await fetch(`${API_BASE}/auth/csrf`, { credentials: "same-origin" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  const data = await res.json();
  cachedCsrfToken = String(data.csrf_token);
  return cachedCsrfToken;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  const mutating = MUTATING_METHODS.has(method);
  const headers = new Headers(init.headers || undefined);
  headers.set("Content-Type", "application/json");
  if (mutating) {
    headers.set("X-CSRF-Token", await getCsrfToken());
  }

  let res = await fetch(API_BASE + path, {
    ...init,
    credentials: "same-origin",
    headers,
  });
  if (res.status === 403 && mutating) {
    const challenge = await res.clone().json().catch(() => null);
    if (challenge?.detail?.code === "step_up_required") {
      const password = window.prompt(
        challenge.detail.level === "critical"
          ? "Confirm your password for this critical security action."
          : "Confirm your password to continue.",
      );
      if (password === null) throw new Error("Recent authentication required");
      await request<{ ok: boolean }>("/auth/reauth", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
    } else {
      cachedCsrfToken = null;
      headers.set("X-CSRF-Token", await getCsrfToken());
    }
    res = await fetch(API_BASE + path, { ...init, credentials: "same-origin", headers });
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  health: () => request<{ status: string; version: string }>("/health"),
  pipelineHealth: () => request<any>("/health/pipeline"),
  setupStatus: () => request<{ completed: boolean; admin_exists: boolean }>("/setup/status"),
  generateRecovery: (setup_token: string) =>
    request<{ words: string[]; code: string; word_count: number }>("/setup/recovery", {
      method: "POST",
      body: JSON.stringify({ setup_token }),
    }),
  setup: (body: { display_name: string; password: string; recovery_code: string; setup_token: string }) =>
    request<{ ok: boolean }>("/auth/setup", { method: "POST", body: JSON.stringify(body) }),
  login: (password: string) =>
    request<{ display_name: string; role: string }>("/auth/login", { method: "POST", body: JSON.stringify({ password }) }),
  reauth: (password: string) =>
    request<{ ok: boolean }>("/auth/reauth", { method: "POST", body: JSON.stringify({ password }) }),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  me: () => request<{ display_name: string; role: string }>("/auth/me"),
  recoveryReset: (recovery_code: string, new_password: string) =>
    request<{ ok: boolean }>("/auth/recovery-reset", {
      method: "POST",
      body: JSON.stringify({ recovery_code, new_password }),
    }),
  overview: () => request<any>("/dashboard/overview"),
  devices: () => request<any[]>("/devices"),
  startPair: () => request<{ code: string; expires_at: string }>("/devices/pair/start", { method: "POST" }),
  pauseDevice: (device_id: string, duration_seconds: number) =>
    request<any>(`/devices/${device_id}/pause`, { method: "POST", body: JSON.stringify({ duration_seconds }) }),
  resumeDevice: (device_id: string) =>
    request<any>(`/devices/${device_id}/resume`, { method: "POST" }),
  revokeDevice: (device_id: string) =>
    request<any>(`/devices/${device_id}`, { method: "DELETE" }),
  assignDeviceProfile: (device_id: string, profile_id: string | null) =>
    request<any>(`/devices/${device_id}/profile`, { method: "PATCH", body: JSON.stringify({ profile_id }) }),
  alerts: (params: Record<string, string> = {}) => {
    const q = new URLSearchParams(params).toString();
    return request<any[]>(`/alerts${q ? `?${q}` : ""}`);
  },
  alert: (id: string) => request<any>(`/alerts/${id}`),
  reviewAlert: (id: string, status: string, notes?: string) =>
    request<any>(`/alerts/${id}/review`, { method: "POST", body: JSON.stringify({ status, notes }) }),
  feedbackAlert: (id: string, feedback_type: string, notes?: string) =>
    request<any>(`/alerts/${id}/feedback`, { method: "POST", body: JSON.stringify({ feedback_type, notes }) }),
  modelStatus: () => request<any>("/models/status"),
  testModel: (text: string) => request<any>("/models/test", { method: "POST", body: JSON.stringify({ text }) }),
  profiles: () => request<any[]>("/profiles"),
  createProfile: (
    display_name: string,
    age_group: string,
    notes?: string,
    custom_watch_phrases?: string[],
  ) =>
    request<any>("/profiles", {
      method: "POST",
      body: JSON.stringify({ display_name, age_group, notes, custom_watch_phrases }),
    }),
  updateProfile: (
    profile_id: string,
    patch: {
      display_name?: string;
      age_group?: string;
      notes?: string;
      custom_watch_phrases?: string[];
      alert_policy?: any;
      reset_policy_to_age_default?: boolean;
    },
  ) =>
    request<any>(`/profiles/${profile_id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  policyMeta: () => request<any>("/profiles/policy/meta"),
  notificationSettings: () => request<any>("/settings/notifications"),
  updateNotificationSettings: (body: any) =>
    request<any>("/settings/notifications", { method: "PATCH", body: JSON.stringify(body) }),
  testNotificationSettings: () =>
    request<any>("/settings/notifications/test", { method: "POST" }),
  retentionSettings: () => request<any>("/settings/retention"),
  updateRetentionSettings: (body: any) =>
    request<any>("/settings/retention", { method: "PATCH", body: JSON.stringify(body) }),
  runRetentionCleanup: () =>
    request<any>("/settings/retention/run-cleanup", { method: "POST" }),
  backupSettings: () => request<any>("/settings/backups"),
  updateBackupSettings: (body: any) =>
    request<any>("/settings/backups", { method: "PATCH", body: JSON.stringify(body) }),
  runCompleteBackup: () =>
    request<any>("/settings/backups/run", { method: "POST" }),
  storage: () => request<any>("/storage"),
  exports: () => request<any[]>("/storage/exports"),
  exportStorage: () => request<any>("/storage/export", { method: "POST" }),
  deleteExport: (export_id: string) =>
    request<any>(`/storage/exports/${export_id}`, { method: "DELETE" }),
  wipeStorage: (body: any) =>
    request<any>("/storage/wipe", { method: "POST", body: JSON.stringify(body) }),
  audit: (params: Record<string, string> = {}) => {
    const q = new URLSearchParams(params).toString();
    return request<any[]>(`/audit${q ? `?${q}` : ""}`);
  },
  effectivePolicy: (profile_id: string) => request<any>(`/policies/${profile_id}/effective`),
  updateEffectivePolicy: (profile_id: string, config: any) =>
    request<any>(`/policies/${profile_id}/effective`, {
      method: "PATCH",
      body: JSON.stringify({ config }),
    }),
};
