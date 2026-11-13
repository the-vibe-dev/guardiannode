import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";
import type { DeviceAction } from "../src/api";

const now = "2026-08-17T13:30:00Z";
const queueInventory = { files: 0, frames: 0, bytes: 0, oldest_at: null, orphan_files: 0, unsafe_files: 0, scan_truncated: false };
const queueStatus = {
  policy: { dead_letter_retention_days: 7, dead_letter_max_bytes: 268435456, cleanup_batch_files: 256 },
  worker: { enabled: true, interval_seconds: 60 },
  pending: queueInventory, dead_letter: queueInventory,
  cleanup: { last_run_at: null, deleted_files: 0, deleted_bytes: 0, expired_files: 0, quota_files: 0, failed_files: 0, budget_exhausted: false, scan_truncated: false },
  withdrawal_cleanup: { pending: false, requested_at: null, last_attempt_at: null, attempts: 0, remaining_files: 0, remaining_events: 0, remaining_blobs: 0, inventory_incomplete: false, last_deleted_files: 0, last_failed_files: 0 },
};
const profile = {
  profile_id: "profile-1",
  display_name: "Alex",
  age_group: "10_13",
  created_at: now,
  notes: null,
  custom_watch_phrases: ["Example Middle School"],
  alert_policy: { min_severity: "medium", capture: { level: "balanced" }, categories: {} },
};
const device = {
  device_id: "device-1",
  hostname: "Alex-Laptop",
  platform: "windows",
  agent_version: "0.1.0-alpha.3",
  paired: true,
  status: "online",
  created_at: now,
  last_seen: now,
  paused_until: null,
  profile_id: profile.profile_id,
};
const alert = {
  alert_id: "alert-1",
  risk_id: "risk-1",
  device_id: device.device_id,
  profile_id: profile.profile_id,
  severity: "high",
  status: "open",
  created_at: now,
  reviewed_by: null,
  reviewed_at: null,
  action_taken: null,
  notes: null,
  categories: ["scam", "secrecy_request"],
  summary: "A stranger asked to move the conversation and share a code.",
  app_name: "ExampleChat.exe",
  repeat_count: 1,
  last_seen_at: now,
};

function providerStatus() {
  return {
    enabled: false,
    configured: false,
    ready: false,
    blocking_reason: "not_enabled",
    selected: "mock",
    model: "local-mock",
    external_processing: false,
    disclosure: "Guardian Review is disabled. Local detection continues to work.",
    retention_notice: "Nothing is sent to an external provider.",
    providers: {
      mock: { available: false },
      codex: { available: false, security_hold: true },
      openai: { available: false, api_key_configured: false, zdr_confirmed: false },
    },
  };
}

async function fulfill(route: Route, json: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(json) });
}

async function mockFamilyApi(page: Page) {
  const pauseAction: DeviceAction = { action_id: "pause-1", alert_id: "alert-1", device_id: device.device_id, action: "pause_app", status: "failed", preview: "Pause C:\\Apps\\Chat.exe for 15 minutes", created_at: now, completed_at: now, expires_at: "2026-08-18T13:30:00Z", undo_of: null, execution: { has_error: true, partial_failure: true, lease_status: "active", lease_expires_at: "2026-08-17T13:45:00Z", failed_processes: 1, suspended_processes: 1 } };
  let actionHistory = [pauseAction];
  await page.route(/^https?:\/\/[^/]+\/api(?:\/|$)/, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (request.method() === "PATCH" && ["/api/settings/retention", "/api/settings/notifications", "/api/settings/family-locale"].includes(path)) return fulfill(route, request.postDataJSON());
    if (path === "/api/storage/capture-queue") return fulfill(route, request.method() === "PATCH" ? { ...queueStatus, policy: { ...queueStatus.policy, ...request.postDataJSON() } } : queueStatus);
    if (path === "/api/alerts/alert-1/actions") return fulfill(route, actionHistory);
    if (path === "/api/actions/pause-1/undo") {
      const queued: DeviceAction = { ...pauseAction, action_id: "undo-1", action: "undo_action", status: "queued", preview: `Undo: ${pauseAction.preview}`, completed_at: null, execution: null, undo_of: pauseAction.action_id };
      actionHistory = [queued, ...actionHistory];
      return fulfill(route, queued);
    }
    if (path === "/api/audit/page") {
      const filtered = url.searchParams.get("actor");
      const offset = Number(url.searchParams.get("cursor") || "0");
      const total = filtered ? 1 : 205;
      const count = Math.min(50, total - offset);
      return fulfill(route, { items: Array.from({ length: count }, (_, index) => ({ id: offset + index + 1, actor: filtered || "admin", action: "alert.view", target: filtered ? "Filtered audit record" : `Audit target ${offset + index + 1}`, source_ip: "127.0.0.1", details: {}, created_at: now })), total, next_cursor: offset + count < total ? String(offset + count) : null });
    }
    if (path === "/api/setup/status") return fulfill(route, { completed: true, admin_exists: true });
    if (path === "/api/auth/me") return fulfill(route, { display_name: "Jordan", role: "admin" });
    if (path === "/api/auth/csrf") return fulfill(route, { csrf_token: "browser-qa-token" });
    if (path === "/api/dashboard/overview") return fulfill(route, {
      counts_24h: { critical: 0, high: 1, medium: 1, low: 0 },
      counts_7d: { critical: 0, high: 2, medium: 3, low: 1 },
      open_alert_count: 1,
      devices_total: 1,
      devices_online: 1,
      devices_paused: 0,
      recent_severity_counts: { "2026-08-17": 2 },
    });
    if (path === "/api/dashboard/capture-status") return fulfill(route, {
      latest_capture_at: now,
      latest_capture_device_id: device.device_id,
      latest_capture_hostname: device.hostname,
      pending_review_count: 7,
      reviewing_count: 1,
      waiting_upload_count: 0,
      estimated_wait_seconds: 98,
      last_reviewed_at: now,
    });
    if (path === "/api/alerts") return fulfill(route, { items: [alert], next_cursor: null, open_count: 1 });
    if (path === "/api/alerts/alert-1") return fulfill(route, {
      alert,
      event: { event_id: "event-1", source_type: "text", app_name: alert.app_name, window_title: "Example chat", url: null, timestamp: now },
      risk: { ...alert, risk_level: "high", score: 82, confidence: 0.87, evidence: ["Request to share an account code"], rules_triggered: ["scam_code"], model: "local-rules", recommended_action: "review" },
      redacted_text: "Please send me the code and keep this between us.",
      synthetic: true,
    });
    if (path === "/api/devices") return fulfill(route, [device]);
    if (path === "/api/devices/pair/start") return fulfill(route, {
      pairing_id: "pair-1",
      code: "482193",
      expires_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
      server_url: "https://guardiannode.local:8787",
      ca_sha256: "a".repeat(64),
      ca_words: ["cedar", "harbor", "maple", "river"],
      bundle_url: "/api/devices/pair/pair-1/bundle",
    });
    if (path === "/api/profiles") return fulfill(route, [profile]);
    if (path === "/api/profiles/policy/meta") return fulfill(route, {
      severities: ["low", "medium", "high", "critical"],
      capture_levels: ["tight", "balanced", "leeway"],
      modes: ["alert", "monitor", "allow"],
      tunable_categories: [{ key: "scam", label: "Scams" }],
      protected_categories: ["self_harm", "grooming", "threat"],
    });
    if (path === "/api/child-requests") return fulfill(route, {
      items: [{ request_id: "request-1", device_id: device.device_id, profile_id: profile.profile_id, request_type: "more_time", target: "ExampleChat", reason: "I am finishing homework with my group.", status: "open", response_note: null, created_at: now, reviewed_by: null, reviewed_at: null, expires_at: "2026-08-24T13:30:00Z" }],
      next_cursor: null,
      open_count: 1,
    });
    if (path === "/api/onboarding/status") return fulfill(route, {
      complete: true,
      current_step: null,
      steps: ["account", "timezone", "child", "notice", "privacy_choices", "pairing", "self_test", "recovery"].map((id) => ({ id, complete: true })),
      checked_at: now,
    });
    if (path === "/api/consent") return fulfill(route, {
      notice_version: "privacy-notice-2026-08-v1",
      active: true,
      record: { consent_id: "consent-1", notice_version: "privacy-notice-2026-08-v1", status: "granted", choices: { screenshots: true, apps_and_urls: true, retention: true, notifications: true, external_ai: false, child_notice_acknowledged: true }, created_at: now },
    });
    if (path === "/api/guardian-review/providers") return fulfill(route, providerStatus());
    if (path === "/api/guardian-reviews") return fulfill(route, []);
    if (path === "/api/settings/notifications") return fulfill(route, { enabled: false, host: "", port: 587, tls_mode: "starttls", username: "", password: null, password_configured: false, from_address: "", to_address: "", webhook_url: "", webhook_allow_private: false, immediate_min_severity: "high", daily_digest_enabled: true, daily_digest_time: "08:00" });
    if (path === "/api/settings/notifications/status") return fulfill(route, { enabled: false, consent_allowed: true, worker_enabled: true, channels: { email: { configured: false, last_success_at: null }, webhook: { configured: false, last_success_at: null } }, counts: { queued: 0, retry: 0, processing: 0, sent: 0, dead: 0, skipped: 0 }, recent_jobs: [], recent_attempts: [], last_digest: null });
    if (path === "/api/settings/family-locale") return fulfill(route, { timezone: "America/New_York" });
    if (path === "/api/settings/retention") return fulfill(route, { critical: 90, high: 90, medium: 30, low: 1, none: 0, screenshots_flagged: 30, audit_logs: 180 });
    if (path === "/api/settings/backups") return fulfill(route, { config: { enabled: false, destination: "/var/lib/guardiannode/backups", retention_count: 7, interval_seconds: 86400, recipient_public_key: "", recipient_configured: false, incremental_evidence: false }, runs: [] });
    if (path === "/api/storage") return fulfill(route, { alerts: 1, events: 2, risk_results: 2, evidence_blobs: 1, evidence_bytes: 4096, export_bytes: 0 });
    if (path === "/api/storage/exports") return fulfill(route, []);
    return fulfill(route, { detail: `Unhandled browser QA API: ${request.method()} ${path}` }, 404);
  });
}

function collectBrowserErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

test.beforeEach(async ({ page }) => {
  await mockFamilyApi(page);
});

test("family home is responsive, keyboard reachable, and accessible", async ({ page }, testInfo) => {
  const errors = collectBrowserErrors(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Good .*Jordan/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Needs your attention" })).toBeVisible();
  await expect(page.getByText("Alex-Laptop", { exact: true })).toBeVisible();
  await expect(page.getByText(/Captured from Alex-Laptop/)).toBeVisible();
  await expect(page.getByText("7 captured screens in review queue")).toBeVisible();

  if (testInfo.project.name === "mobile") {
    const menu = page.getByRole("button", { name: "Open navigation" });
    await menu.focus();
    await expect(menu).toBeFocused();
    await menu.press("Enter");
    await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
    await page.getByRole("button", { name: "Close navigation", exact: true }).click();
  } else {
    await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
  }

  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(results.violations.filter((item) => ["serious", "critical"].includes(item.impact || ""))).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-home.png`), fullPage: false });
  expect(errors).toEqual([]);
});

test("core parent journeys render without runtime errors", async ({ page }) => {
  const errors = collectBrowserErrors(page);
  const journeys = [
    ["/risks", "Risk feed"],
    ["/profiles", "Child profiles"],
    ["/devices", "Devices"],
    ["/requests", "Requests"],
    ["/privacy", "Privacy & consent"],
    ["/settings", "Settings"],
    ["/audit", "Audit"],
    ["/alerts/alert-1", "Alert"],
  ] as const;
  for (const [path, heading] of journeys) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: heading, exact: true }).first()).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test("secure pairing instructions expose the exact trust handoff", async ({ page }) => {
  await page.goto("/devices");
  await page.getByRole("button", { name: "Add device" }).click();
  await expect(page.getByRole("heading", { name: "Pair a child device securely" })).toBeVisible();
  await expect(page.getByText("https://guardiannode.local:8787")).toBeVisible();
  await expect(page.getByText("cedar · harbor · maple · river")).toBeVisible();
  await expect(page.getByRole("link", { name: "Download .gnpair bundle" })).toHaveAttribute("download", "");
});

test("audit history pages past 200 and isolates applied filters", async ({ page }, testInfo) => {
  const errors = collectBrowserErrors(page);
  await page.goto("/audit");
  await expect(page.getByRole("heading", { name: "Audit", exact: true })).toBeVisible();
  await expect(page.getByText("50 of 205 retained audit entries loaded · more available")).toBeVisible();
  for (const count of [100, 150, 200, 205]) {
    await page.getByRole("button", { name: "Load older audit entries", exact: true }).click();
    await expect(page.getByText(`${count} of 205 retained audit entries loaded · ${count < 205 ? "more available" : "end of results"}`)).toBeVisible();
  }
  await expect(page.getByText("Audit target 205", { exact: true })).toBeVisible();
  await page.getByLabel("Actor (exact)").fill("system");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.getByText("Filtered audit record", { exact: true })).toBeVisible();
  await expect(page.getByText("Audit target 205", { exact: true })).toHaveCount(0);
  await expect(page.getByText("1 of 1 retained audit entries loaded · end of results")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-audit.png`), fullPage: false });
  const accessibility = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(accessibility.violations.filter((item) => ["serious", "critical"].includes(item.impact || ""))).toEqual([]);
  expect(errors).toEqual([]);
});

test("saving Settings preserves unrelated drafts and queue controls stay independent", async ({ page }, testInfo) => {
  const errors = collectBrowserErrors(page);
  await page.goto("/settings");
  await page.getByLabel("SMTP host").fill("draft.smtp.example.test");
  await page.getByLabel("Destination path").fill("/draft-backups");
  await page.getByLabel("high (days)", { exact: true }).fill("45");
  await page.getByRole("button", { name: "Save retention", exact: true }).click();
  await expect(page.getByText("Retention settings saved.")).toBeVisible();
  await expect(page.getByLabel("SMTP host")).toHaveValue("draft.smtp.example.test");
  await expect(page.getByLabel("Destination path")).toHaveValue("/draft-backups");
  await expect(page.getByLabel("high (days)", { exact: true })).toHaveValue("45");
  await page.getByLabel("Quarantine retention (days)").fill("14");
  await page.getByRole("button", { name: "Refresh queue status" }).click();
  await expect(page.getByRole("button", { name: "Refresh queue status" })).toBeEnabled();
  await expect(page.getByLabel("Quarantine retention (days)")).toHaveValue("14");
  await page.getByRole("button", { name: "Save queue policy" }).click();
  await expect(page.getByText("Capture queue policy saved. Cleanup uses this policy on its next run.")).toBeVisible();
  await expect(page.getByLabel("SMTP host")).toHaveValue("draft.smtp.example.test");
  await page.getByRole("heading", { name: "Capture queue & evidence deletion" }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-queue.png`), fullPage: false });
  const accessibility = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(accessibility.violations.filter((item) => ["serious", "critical"].includes(item.impact || ""))).toEqual([]);
  expect(errors).toEqual([]);
});

test("partial app pause reports keep undo available and do not claim immediate recovery", async ({ page }, testInfo) => {
  const errors = collectBrowserErrors(page);
  await page.goto("/alerts/alert-1");
  await expect(page.getByRole("heading", { name: "Action history", exact: true })).toBeVisible();
  await expect(page.getByText(/Last report: some processes may remain paused until/)).toBeVisible();
  await page.getByRole("button", { name: /^Queue undo:/ }).click();
  await expect(page.getByText("Undo is queued. It is not applied until the endpoint reports its result. Check the undo entry below.")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Queue undo:/ })).toHaveCount(0);
  await expect(page.getByText("Queued", { exact: true })).toBeVisible();
  await page.getByRole("heading", { name: "Action history", exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath(`${testInfo.project.name}-action-history.png`), fullPage: false });
  expect(errors).toEqual([]);
});
