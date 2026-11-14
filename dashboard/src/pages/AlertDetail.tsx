import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, api, type DeviceAction } from "../api";
import SeverityBadge from "../components/SeverityBadge";
import GuardianReviewPanel from "../components/GuardianReviewPanel";
import ActionHistory from "../components/ActionHistory";
import { formatDateTime } from "../utils/datetime";

export default function AlertDetail() {
  const { id } = useParams();
  // Route changes must discard all incident-specific state, including notes,
  // evidence-deletion confirmation and any response for the previous alert.
  return <AlertIncident key={id} id={id} />;
}

function AlertIncident({ id }: { id: string | undefined }) {
  const queryClient = useQueryClient();
  const [detail, setDetail] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [deletionReceipt, setDeletionReceipt] = useState<DeviceAction | null>(null);
  const [loadVersion, setLoadVersion] = useState(0);
  const [evidenceChanged, setEvidenceChanged] = useState(false);

  useEffect(() => {
    let disposed = false;
    if (id) {
      api.alert(id)
        .then((response) => { if (!disposed) setDetail(response); })
        .catch((reason: Error) => { if (!disposed) setError(reason.message); });
    }
    return () => { disposed = true; };
  }, [id, loadVersion]);

  function invalidateIncidentQueries() {
    for (const queryKey of [["alerts"], ["overview"], ["capture-status"]]) {
      void queryClient.invalidateQueries({ queryKey });
    }
  }

  async function refreshChangedEvidence() {
    // Unmount all old evidence, screenshot reveal, outbound preview and results.
    // Draft notes stay local, but no mutation is replayed against the new risk.
    setDetail(null);
    setError(null);
    setActionMsg(null);
    setEvidenceChanged(true);
    invalidateIncidentQueries();
    setLoadVersion((current) => current + 1);
  }

  async function handleActionFailure(reason: unknown, prefix: string) {
    if (reason instanceof ApiError && reason.status === 409 && (reason.body?.detail?.code || reason.body?.error?.code) === "evidence_changed") {
      await refreshChangedEvidence();
    } else setError(`${prefix}: ${reason instanceof Error ? reason.message : String(reason)}`);
  }

  async function review(status: string) {
    if (!id) return;
    setBusy(true);
    setActionMsg(null);
    setError(null);
    try {
      await api.reviewAlert(id, status, notes || undefined, detail.alert.risk_id);
      setEvidenceChanged(false);
      invalidateIncidentQueries();
      const d = await api.alert(id);
      setDetail(d);
      const friendly: Record<string, string> = {
        reviewed: "Marked as reviewed",
        false_positive: "Marked as false positive",
        escalated: "Escalated",
        dismissed: "Dismissed",
      };
      setActionMsg(`✓ ${friendly[status] || status}`);
    } catch (e: any) {
      await handleActionFailure(e, "Action failed");
    } finally {
      setBusy(false);
    }
  }

  async function feedback(feedback_type: string) {
    if (!id) return;
    setBusy(true);
    setActionMsg(null);
    setError(null);
    try {
      await api.feedbackAlert(id, feedback_type, notes || undefined, detail.alert.risk_id);
      setEvidenceChanged(false);
      invalidateIncidentQueries();
      const d = await api.alert(id);
      setDetail(d);
      setActionMsg("✓ Feedback recorded");
    } catch (e: any) {
      await handleActionFailure(e, "Feedback failed");
    } finally {
      setBusy(false);
    }
  }

  async function deleteEvidence() {
    if (!id) return;
    setBusy(true);
    setError(null);
    setActionMsg(null);
    const body = { action: "delete_evidence" as const, expected_risk_id: detail.alert.risk_id };
    try {
      const result = await api.confirmedAlertAction(id, body);
      recordDeletion(result);
    } catch (error) {
      const preview = error instanceof ApiError ? error.body?.detail?.preview : null;
      if (!preview) {
        await handleActionFailure(error, "Action failed");
        setBusy(false);
        return;
      }
      if (!window.confirm(`${preview}\n\nThis removes the retained evidence for this alert. This cannot be undone. Continue?`)) {
        setBusy(false);
        return;
      }
      try {
        const result = await api.confirmedAlertAction(id, { ...body, confirmed_preview: preview });
        recordDeletion(result);
      } catch (secondError) {
        await handleActionFailure(secondError, "Action failed");
      }
    } finally {
      setBusy(false);
    }
  }

  function recordDeletion(result: DeviceAction) {
    setDeletionReceipt(result);
    setDetail(null);
    for (const queryKey of [["alert-actions", id], ["alerts"], ["overview"], ["capture-status"]]) {
      void queryClient.invalidateQueries({ queryKey });
    }
  }

  if (deletionReceipt) return <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-5">
    <h1 className="font-display text-2xl font-bold text-[#18313a]">Evidence deletion</h1>
    <p role="status" className="text-sm text-slate-700">{deletionReceipt.status === "completed" ? "The retained evidence for this alert has been deleted." : "Evidence deletion is pending. Background cleanup will retry removal; this incident is excluded from active review."}</p>
    <p className="text-xs text-slate-500">Deletion receipt: {deletionReceipt.action_id} · {deletionReceipt.status}. Audit metadata records the request.</p>
    <Link to="/risks" className="inline-flex min-h-11 items-center font-semibold text-[#275e3d] underline">Return to alerts</Link>
  </section>;

  if (error && !detail) return <div role="alert" className="text-red-700 p-4">{error} <button className="font-semibold underline" onClick={() => { setError(null); setLoadVersion((current) => current + 1); }}>Retry alert</button></div>;
  if (!detail) return <div role="status" className="text-gray-500 p-4">Loading…</div>;

  const eventId = detail.event?.event_id;
  const hasScreenshot = Boolean(eventId && detail.event?.has_screenshot);

  return (
    <div className="space-y-4">
      <Link to="/risks" className="text-sm text-brand-700 underline">&larr; Back to feed</Link>
      <div className="flex items-baseline gap-3 flex-wrap">
        <h1 className="text-2xl font-bold">Alert</h1>
        <SeverityBadge severity={detail.alert.severity} />
        <StatusBadge status={detail.alert.status} />
        {detail.alert.reviewed_at && (
          <span className="text-xs text-gray-500">reviewed {formatDateTime(detail.alert.reviewed_at)}</span>
        )}
      </div>

      {detail.synthetic && (
        <div className="rounded border border-blue-300 bg-blue-50 p-3 text-sm text-blue-950">
          <strong>Synthetic demo incident.</strong> This manufactured scenario contains no real child or family data. Review the local reasoning below, then continue through the exact outbound preview.
          <Link to="/demo" className="ml-2 underline">Demo guide</Link>
        </div>
      )}

      {evidenceChanged && <div role="alert" className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">This alert has newer evidence. Your previous action was not applied. Review the updated screenshot and findings before trying again. Any draft notes are still below.</div>}
      {error && <div role="alert" className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm">{error}</div>}
      {actionMsg && <div role="status" className="bg-green-50 border border-green-200 text-green-700 rounded p-3 text-sm">{actionMsg}</div>}

      {/* Summary */}
      <div className="bg-white shadow rounded p-4">
        <h2 className="font-semibold mb-2">Summary</h2>
        <p>{detail.risk.summary || <em>(no summary)</em>}</p>
      </div>

      {/* Screenshot */}
      {eventId && (
        <div className="bg-white shadow rounded p-4">
          <h2 className="font-semibold mb-2 flex items-center gap-2">
            Screenshot
            <span className="text-xs font-normal text-gray-500">(encrypted at rest; viewing logs an audit entry)</span>
          </h2>
          {hasScreenshot ? <ScreenshotViewer key={eventId} eventId={eventId} /> : <p role={detail.event.screenshot_status === "missing" ? "alert" : "status"} className="text-sm text-slate-600">{detail.event.screenshot_status === "missing" ? "The screenshot record exists, but its image is unavailable. Check storage diagnostics." : detail.event.screenshot_status === "pending_delete" ? "This screenshot is pending deletion and cannot be displayed." : detail.event.screenshot_status === "not_retained" ? "No screenshot is retained for this alert." : "Screenshot availability has not been reported."}</p>}
        </div>
      )}

      {/* Evidence */}
      <div className="bg-white shadow rounded p-4">
        <h2 className="font-semibold mb-2">Evidence</h2>
        {detail.risk.evidence && detail.risk.evidence.length > 0 ? (
          <ul className="list-disc pl-5 text-sm space-y-1">
            {detail.risk.evidence.map((e: string, i: number) => (
              <li key={i} className={e.startsWith("[image]") ? "text-blue-700" : ""}>
                {e}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-gray-500"><em>(no evidence quoted)</em></p>
        )}
        {detail.redacted_text && (
          <details className="mt-3">
            <summary className="cursor-pointer text-sm text-brand-700">
              Show full extracted text ({detail.redacted_text.length} chars)
            </summary>
            <pre className="mt-2 bg-gray-50 border rounded p-3 whitespace-pre-wrap text-sm font-mono">{detail.redacted_text}</pre>
          </details>
        )}
      </div>

      <GuardianReviewPanel key={detail.alert.risk_id} alertId={id!} detail={detail} onEvidenceChanged={refreshChangedEvidence} />

      <div className="bg-white shadow rounded p-4">
        <h2 className="font-semibold mb-2">Conversation & next steps</h2>
        <ul className="list-disc pl-5 text-sm space-y-1">
          {playbook(detail.risk.categories || [], detail.alert.severity).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>

      <section aria-labelledby="evidence-controls-heading" className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
        <h2 id="evidence-controls-heading" className="font-display font-semibold text-[#18313a]">Evidence controls</h2>
        <p className="mt-1 text-sm text-slate-600">Delete the retained evidence for this alert after reviewing it. You will confirm the exact deletion first.</p>
        <button onClick={deleteEvidence} disabled={busy} className="mt-4 min-h-11 rounded-lg bg-red-700 px-4 py-2 text-sm font-semibold text-white hover:bg-red-800 disabled:opacity-50">Preview evidence deletion…</button>
      </section>

      <ActionHistory alertId={id!} />

      {/* Event + Classification */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="bg-white shadow rounded p-4">
          <h3 className="font-semibold mb-2">Event</h3>
          <dl className="text-sm space-y-1">
            <Item k="App" v={detail.event.app_name || "—"} />
            <Item k="Window" v={detail.event.window_title || "—"} />
            <Item k="URL" v={detail.event.url || "—"} />
            <Item k="Source" v={detail.event.source_type} />
            <Item k="Time" v={formatDateTime(detail.event.timestamp)} />
          </dl>
        </div>
        <div className="bg-white shadow rounded p-4">
          <h3 className="font-semibold mb-2">Classification</h3>
          <dl className="text-sm space-y-1">
            <Item k="Score" v={String(detail.risk.score)} />
            <Item k="Model confidence" v={String(detail.risk.confidence)} />
            <Item k="Categories" v={(detail.risk.categories || []).join(", ") || "—"} />
            <Item k="Rules" v={(detail.risk.rules_triggered || []).join(", ") || "—"} />
            <Item k="Review method" v={detail.risk.model || "Not reported"} />
            <Item k="Classifier status" v={detail.risk.classifier_status?.replaceAll("_", " ") || "Not reported"} />
            <Item k="Suggested review" v={detail.risk.recommended_action} />
          </dl>
          <p className="mt-3 text-xs text-slate-500">Scores and model confidence are review signals, not a verified probability of harm. Read the screenshot and surrounding context.</p>
        </div>
      </div>

      {/* Review actions */}
      <div className="bg-white shadow rounded p-4">
        <h3 className="font-semibold mb-2">Review</h3>
        <textarea
          aria-label="Review notes"
          placeholder="Optional notes…"
          className="w-full border rounded p-2 text-sm"
          rows={3}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            onClick={() => review("reviewed")}
            disabled={busy}
            className="bg-brand-500 hover:bg-brand-700 disabled:bg-brand-500/50 text-white px-3 py-1.5 rounded text-sm"
          >
            Mark reviewed
          </button>
          <button
            onClick={() => review("false_positive")}
            disabled={busy}
            className="bg-gray-200 hover:bg-gray-300 disabled:opacity-50 text-gray-800 px-3 py-1.5 rounded text-sm"
          >
            False positive
          </button>
          <button
            onClick={() => review("escalated")}
            disabled={busy}
            className="bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white px-3 py-1.5 rounded text-sm"
          >
            Escalate
          </button>
          <button
            onClick={() => review("dismissed")}
            disabled={busy}
            className="bg-gray-100 hover:bg-gray-200 disabled:opacity-50 text-gray-600 px-3 py-1.5 rounded text-sm"
          >
            Dismiss
          </button>
          <button
            onClick={() => feedback("confirmed")}
            disabled={busy}
            className="bg-green-50 hover:bg-green-100 disabled:opacity-50 text-green-700 border border-green-200 px-3 py-1.5 rounded text-sm"
          >
            Confirm useful
          </button>
          <button
            onClick={() => feedback("too_high")}
            disabled={busy}
            className="bg-yellow-50 hover:bg-yellow-100 disabled:opacity-50 text-yellow-700 border border-yellow-200 px-3 py-1.5 rounded text-sm"
          >
            Too severe
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-2">
          All actions are logged to the audit log. Current status: <strong>{detail.alert.status}</strong>
        </p>
      </div>
    </div>
  );
}

function playbook(categories: string[], severity: string): string[] {
  const cats = new Set(categories);
  if (cats.has("self_harm")) {
    return [
      "Check on the child directly and calmly.",
      "If there is immediate danger, contact local emergency services or a crisis line.",
      "Preserve the alert and add review notes after you have responded.",
    ];
  }
  if (cats.has("sexual_content") || cats.has("secrecy_request") || cats.has("grooming")) {
    return [
      "Do not reply from the child's account.",
      "Review the surrounding context and identify the platform/account involved.",
      "Consider blocking the contact and reporting the account through the platform.",
    ];
  }
  if (cats.has("bullying") || cats.has("threat")) {
    return [
      "Talk with the child before escalating unless there is immediate danger.",
      "Save evidence and identify the platform, group, or school context.",
      "For credible threats, contact the school or local authorities.",
    ];
  }
  if (cats.has("scam") || cats.has("phishing")) {
    return [
      "Do not click links or send codes, gift cards, money, or account details.",
      "Change passwords if any credentials may have been shared.",
      "Block/report the sender and review account security settings.",
    ];
  }
  if (severity === "critical") {
    return ["Review immediately.", "Use the evidence and source details below to decide the safest next action."];
  }
  return ["Review the evidence and mark whether this alert was useful.", "Adjust watch phrases or alert settings if this is noisy."];
}

function ScreenshotViewer({ eventId }: { eventId: string }) {
  const [reveal, setReveal] = useState(false);
  const [imgError, setImgError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (!reveal) {
    return (
      <div className="border-2 border-dashed border-gray-300 rounded p-6 text-center bg-gray-50">
        <p className="text-sm text-gray-600 mb-3">
          The captured screenshot is encrypted on disk. Click to decrypt and view.
          Every view is recorded in the audit log.
        </p>
        <button
          onClick={() => { setImgError(null); setLoading(true); setReveal(true); }}
          className="bg-brand-500 hover:bg-brand-700 text-white px-4 py-2 rounded text-sm"
        >
          Reveal screenshot
        </button>
      </div>
    );
  }

  return (
    <div>
      {loading && <p role="status" className="mb-2 text-sm text-slate-600">Loading retained screenshot…</p>}
      {imgError && <div role="alert" className="text-sm text-red-700 mb-2">{imgError} Hide and reveal it again to retry.</div>}
      <img
        src={`/api/events/${eventId}/screenshot`}
        alt="Captured screenshot"
        className="max-w-full border rounded shadow-sm"
        onLoad={() => { setLoading(false); setImgError(null); }}
        onError={() => { setLoading(false); setImgError("The screenshot could not be loaded. It may have expired, been removed, or become unavailable."); }}
      />
      <div className="mt-2 flex gap-2">
        <a
          href={`/api/events/${eventId}/screenshot`}
          download={`guardiannode-${eventId}.jpg`}
          className="text-xs text-brand-700 underline"
        >
          Download
        </a>
        <button
          onClick={() => { setLoading(false); setImgError(null); setReveal(false); }}
          className="text-xs text-gray-500 underline"
        >
          Hide
        </button>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    open: "bg-red-100 text-red-800",
    reviewed: "bg-green-100 text-green-800",
    false_positive: "bg-gray-200 text-gray-700",
    escalated: "bg-orange-100 text-orange-800",
    dismissed: "bg-gray-100 text-gray-500",
  };
  return (
    <span className={`text-xs uppercase font-semibold px-2 py-0.5 rounded ${colors[status] || colors.open}`}>
      {status.replace("_", " ")}
    </span>
  );
}

function Item({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-gray-500">{k}</dt>
      <dd className="text-right max-w-[60%] break-words">{v}</dd>
    </div>
  );
}
