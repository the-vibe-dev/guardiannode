// Typed API client. Uses cookie auth (no token to manage in localStorage).
import type { components } from "./api-schema";
import { requestStepUp } from "./stepUp";

export type Alert = components["schemas"]["AlertDTO"];
export type AlertPage = components["schemas"]["AlertPage"];
export type Device = components["schemas"]["DeviceDTO"];
export type Overview = components["schemas"]["Overview"];
export type Profile = components["schemas"]["ProfileDTO"];
export type PairStart = components["schemas"]["PairStartResponse"];
export type CaptureStatus = components["schemas"]["CaptureStatus"];
export type CaptureDeviceStatus = components["schemas"]["CaptureDeviceStatus"];
export type AuditEntry = components["schemas"]["AuditDTO"];
export type AuditPage = components["schemas"]["AuditPageDTO"];
export type DeviceAction = components["schemas"]["ActionDTO"];
export type ActionExecution = components["schemas"]["ActionExecutionDTO"];

export interface OnboardingStatus {
  complete: boolean;
  current_step: string | null;
  steps: Array<{ id: string; complete: boolean }>;
  checked_at: string;
}

export interface ConsentStatus {
  notice_version: string;
  active: boolean;
  record: null | { consent_id: string; notice_version: string; status: string; choices: Record<string, unknown>; created_at: string };
}

export interface ConsentWithdrawalResult extends ConsentStatus {
  deletion: null | {
    events?: number;
    risk_results?: number;
    alerts?: number;
    blobs?: number;
    guardian_reviews?: number;
    remaining_events?: number;
    remaining_blobs?: number;
    pending_captures?: { deleted: number; failed: number };
  };
}

export interface NotificationStatus {
  enabled: boolean;
  consent_allowed: boolean;
  worker_enabled: boolean;
  routing?: { immediate_min_severity: string; protected_safety_floor: "high"; rechecks_current_policy: boolean; historical_backfill: boolean };
  channels: Record<"email" | "webhook", { configured: boolean; last_success_at: string | null }>;
  counts: Record<"queued" | "retry" | "processing" | "sent" | "dead" | "skipped", number>;
  recent_jobs: Array<{ id: string | number; alert_id: string; severity: string; status: string; attempts: number; next_attempt_at: string | null; created_at: string; updated_at: string; delivered_channels: string[]; skip_reason?: "current_policy" | null }>;
  recent_attempts: Array<{ id: string | number; alert_id: string; channel: string; severity: string; result: string; created_at: string }>;
  last_digest: { local_date: string; timezone: string; status: string; total_alerts: number; completed_at: string | null } | null;
}

export interface NotificationTestResult {
  ok: boolean;
  detail: string;
  results: Array<{ channel: string; ok: boolean; detail: string }>;
}

export type CaptureQueuePolicy = components["schemas"]["CaptureQueuePolicy"];
export type CaptureQueueInventory = components["schemas"]["CaptureQueueInventory"];
export type CaptureQueueStatus = components["schemas"]["CaptureQueueStatus"];

const API_BASE = "/api";
const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

let cachedCsrfToken: string | null = null;

export class ApiError extends Error {
  constructor(message: string, public status: number, public body: any) {
    super(message);
    this.name = "ApiError";
  }
}

async function getCsrfToken(): Promise<string> {
  if (cachedCsrfToken) return cachedCsrfToken;
  const res = await fetch(`${API_BASE}/auth/csrf`, { credentials: "same-origin" });
  if (!res.ok) {
    const body = await res.clone().json().catch(() => null);
    const message = body?.error?.message || body?.detail?.message || body?.detail || `Request failed (${res.status})`;
    throw new Error(String(message));
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
      await requestStepUp(challenge.detail.level);
    } else {
      cachedCsrfToken = null;
      headers.set("X-CSRF-Token", await getCsrfToken());
    }
    res = await fetch(API_BASE + path, { ...init, credentials: "same-origin", headers });
  }
  if (!res.ok) {
    const body = await res.clone().json().catch(() => null);
    const message = body?.error?.message || body?.detail?.message ||
      (typeof body?.detail === "string" ? body.detail : null) || `Request failed (${res.status})`;
    throw new ApiError(String(message), res.status, body);
  }
  if (res.status === 204) return undefined as T;
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
  demoStatus: () => request<any>("/demo/status"),
  demoScenarios: () => request<any[]>("/demo/scenarios"),
  triggerDemoScenario: (scenario_id: string) =>
    request<any>(`/demo/scenarios/${encodeURIComponent(scenario_id)}/trigger`, { method: "POST" }),
  resetDemo: () => request<any>("/demo/reset", { method: "POST" }),
  recoveryReset: (recovery_code: string, new_password: string) =>
    request<{ ok: boolean }>("/auth/recovery-reset", {
      method: "POST",
      body: JSON.stringify({ recovery_code, new_password }),
    }),
  overview: () => request<Overview>("/dashboard/overview"),
  captureStatus: () => request<CaptureStatus>("/dashboard/capture-status"),
  devices: () => request<Device[]>("/devices"),
  startPair: () => request<PairStart>("/devices/pair/start", { method: "POST" }),
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
    return request<AlertPage>(`/alerts${q ? `?${q}` : ""}`);
  },
  alert: (id: string) => request<any>(`/alerts/${id}`),
  guardianReviewProviders: () => request<any>("/guardian-review/providers"),
  startCodexLogin: () => request<any>("/guardian-review/providers/codex/device-login", { method: "POST" }),
  codexLoginStatus: (session_id: string) => request<any>(`/guardian-review/providers/codex/device-login/${session_id}`),
  cancelCodexLogin: (session_id: string) => request<any>(`/guardian-review/providers/codex/device-login/${session_id}`, { method: "DELETE" }),
  guardianReviewPreview: (id: string, body: any) =>
    request<any>(`/alerts/${id}/guardian-review/preview`, { method: "POST", body: JSON.stringify(body) }),
  cancelGuardianReviewPreview: (preview_id: string) =>
    request<void>(`/guardian-review/previews/${preview_id}`, { method: "DELETE" }),
  submitGuardianReview: (id: string, preview_id: string, preview_digest: string) =>
    request<any>(`/alerts/${id}/guardian-review`, {
      method: "POST",
      body: JSON.stringify({ preview_id, preview_digest, consent: true }),
    }),
  guardianReview: (review_id: string) => request<any>(`/guardian-reviews/${review_id}`),
  guardianReviewHistory: (params: Record<string, string> = {}) => {
    const q = new URLSearchParams(params).toString();
    return request<any[]>(`/guardian-reviews${q ? `?${q}` : ""}`);
  },
  deleteGuardianReview: (review_id: string) =>
    request<any>(`/guardian-reviews/${review_id}`, { method: "DELETE" }),
  guardianReviewFeedback: (review_id: string) =>
    request<any | null>(`/guardian-reviews/${review_id}/feedback`),
  saveGuardianReviewFeedback: (review_id: string, labels: string[]) =>
    request<any>(`/guardian-reviews/${review_id}/feedback`, {
      method: "PUT",
      body: JSON.stringify({ labels }),
    }),
  reviewAlert: (id: string, status: string, notes?: string) =>
    request<any>(`/alerts/${id}/review`, { method: "POST", body: JSON.stringify({ status, notes }) }),
  feedbackAlert: (id: string, feedback_type: string, notes?: string) =>
    request<any>(`/alerts/${id}/feedback`, { method: "POST", body: JSON.stringify({ feedback_type, notes }) }),
  confirmedAlertAction: (id: string, body: { action: "delete_evidence"; confirmed_preview?: string | null }) =>
    request<DeviceAction>(`/alerts/${id}/actions`, { method: "POST", body: JSON.stringify(body) }),
  alertActions: (id: string) => request<DeviceAction[]>(`/alerts/${encodeURIComponent(id)}/actions?limit=50`),
  undoAction: (action_id: string) => request<DeviceAction>(`/actions/${encodeURIComponent(action_id)}/undo`, { method: "POST" }),
  modelStatus: () => request<any>("/models/status"),
  testModel: (text: string) => request<any>("/models/test", { method: "POST", body: JSON.stringify({ text }) }),
  profiles: () => request<Profile[]>("/profiles"),
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
  notificationStatus: () => request<NotificationStatus>("/settings/notifications/status"),
  updateNotificationSettings: (body: any) =>
    request<any>("/settings/notifications", { method: "PATCH", body: JSON.stringify(body) }),
  testNotificationSettings: () =>
    request<NotificationTestResult>("/settings/notifications/test", { method: "POST" }),
  familyLocale: () => request<{ timezone: string }>("/settings/family-locale"),
  updateFamilyLocale: (timezone: string) =>
    request<{ timezone: string }>("/settings/family-locale", { method: "PATCH", body: JSON.stringify({ timezone }) }),
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
  captureQueue: () => request<CaptureQueueStatus>("/storage/capture-queue"),
  updateCaptureQueuePolicy: (body: Partial<CaptureQueuePolicy>) =>
    request<CaptureQueueStatus>("/storage/capture-queue", { method: "PATCH", body: JSON.stringify(body) }),
  runCaptureQueueCleanup: () => request<CaptureQueueStatus>("/storage/capture-queue/cleanup", { method: "POST" }),
  exports: () => request<any[]>("/storage/exports"),
  exportStorage: () => request<any>("/storage/export", { method: "POST" }),
  deleteExport: (export_id: string) =>
    request<any>(`/storage/exports/${export_id}`, { method: "DELETE" }),
  wipeStorage: (body: any) =>
    request<any>("/storage/wipe", { method: "POST", body: JSON.stringify(body) }),
  audit: (params: Record<string, string> = {}) => {
    const q = new URLSearchParams(params).toString();
    return request<AuditEntry[]>(`/audit${q ? `?${q}` : ""}`);
  },
  auditPage: (params: Record<string, string> = {}) => {
    const q = new URLSearchParams(params).toString();
    return request<AuditPage>(`/audit/page${q ? `?${q}` : ""}`);
  },
  effectivePolicy: (profile_id: string) => request<any>(`/policies/${profile_id}/effective`),
  updateEffectivePolicy: (profile_id: string, config: any) =>
    request<any>(`/policies/${profile_id}/effective`, {
      method: "PATCH",
      body: JSON.stringify({ config }),
    }),
  onboardingStatus: () => request<OnboardingStatus>("/onboarding/status"),
  consentStatus: () => request<ConsentStatus>("/consent"),
  grantConsent: (notice_version: string, choices: components["schemas"]["ConsentChoices"]) =>
    request<ConsentStatus>("/consent", { method: "POST", body: JSON.stringify({ notice_version, choices }) }),
  withdrawConsent: (evidence_disposition: "retain" | "delete") =>
    request<ConsentWithdrawalResult>("/consent/withdraw", { method: "POST", body: JSON.stringify({ evidence_disposition }) }),

};
