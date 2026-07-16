import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../api";
import SeverityBadge from "../components/SeverityBadge";
import GuardianReviewPanel from "../components/GuardianReviewPanel";
import { formatDateTime } from "../utils/datetime";

export default function AlertDetail() {
  const { id } = useParams();
  const [detail, setDetail] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showFullText, setShowFullText] = useState(false);

  useEffect(() => {
    if (id) api.alert(id).then(setDetail).catch((e) => setError(e.message));
  }, [id]);

  async function review(status: string) {
    if (!id) return;
    setBusy(true);
    setActionMsg(null);
    setError(null);
    try {
      await api.reviewAlert(id, status, notes || undefined);
      const d = await api.alert(id);
      setDetail(d);
      const friendly: Record<string, string> = {
        reviewed: "Marked as reviewed",
        false_positive: "Marked as false positive",
        escalated: "Escalated",
        dismissed: "Dismissed",
      };
      setActionMsg(`✓ ${friendly[status] || status}`);
      setTimeout(() => setActionMsg(null), 3000);
    } catch (e: any) {
      setError(`Action failed: ${e.message || e}`);
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
      await api.feedbackAlert(id, feedback_type, notes || undefined);
      const d = await api.alert(id);
      setDetail(d);
      setActionMsg("✓ Feedback recorded");
      setTimeout(() => setActionMsg(null), 3000);
    } catch (e: any) {
      setError(`Feedback failed: ${e.message || e}`);
    } finally {
      setBusy(false);
    }
  }

  if (error && !detail) return <div className="text-red-700 p-4">{error}</div>;
  if (!detail) return <div className="text-gray-500 p-4">Loading…</div>;

  const eventId = detail.event?.event_id;
  const hasScreenshot = eventId && detail.alert?.severity && ["medium", "high", "critical"].includes(detail.alert.severity);

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

      {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm">{error}</div>}
      {actionMsg && <div className="bg-green-50 border border-green-200 text-green-700 rounded p-3 text-sm">{actionMsg}</div>}

      {/* Summary */}
      <div className="bg-white shadow rounded p-4">
        <h2 className="font-semibold mb-2">Summary</h2>
        <p>{detail.risk.summary || <em>(no summary)</em>}</p>
      </div>

      <div className="bg-white shadow rounded p-4">
        <h2 className="font-semibold mb-2">Next steps</h2>
        <ul className="list-disc pl-5 text-sm space-y-1">
          {playbook(detail.risk.categories || [], detail.alert.severity).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>

      {/* Screenshot */}
      {hasScreenshot && (
        <div className="bg-white shadow rounded p-4">
          <h2 className="font-semibold mb-2 flex items-center gap-2">
            Screenshot
            <span className="text-xs font-normal text-gray-500">(encrypted at rest; viewing logs an audit entry)</span>
          </h2>
          <ScreenshotViewer eventId={eventId} />
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

      <GuardianReviewPanel alertId={id!} detail={detail} />

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
            <Item k="Confidence" v={String(detail.risk.confidence)} />
            <Item k="Categories" v={(detail.risk.categories || []).join(", ") || "—"} />
            <Item k="Rules" v={(detail.risk.rules_triggered || []).join(", ") || "—"} />
            <Item k="Model" v={detail.risk.model || "(rules only)"} />
            <Item k="Recommended" v={detail.risk.recommended_action} />
          </dl>
        </div>
      </div>

      {/* Review actions */}
      <div className="bg-white shadow rounded p-4">
        <h3 className="font-semibold mb-2">Review</h3>
        <textarea
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
  return ["Review the evidence and mark whether this alert was useful.", "Adjust watch phrases or policy if this is noisy."];
}

function ScreenshotViewer({ eventId }: { eventId: string }) {
  const [reveal, setReveal] = useState(false);
  const [imgError, setImgError] = useState<string | null>(null);

  if (!reveal) {
    return (
      <div className="border-2 border-dashed border-gray-300 rounded p-6 text-center bg-gray-50">
        <p className="text-sm text-gray-600 mb-3">
          The captured screenshot is encrypted on disk. Click to decrypt and view.
          Every view is recorded in the audit log.
        </p>
        <button
          onClick={() => setReveal(true)}
          className="bg-brand-500 hover:bg-brand-700 text-white px-4 py-2 rounded text-sm"
        >
          Reveal screenshot
        </button>
      </div>
    );
  }

  return (
    <div>
      {imgError && <div className="text-sm text-red-700 mb-2">{imgError}</div>}
      <img
        src={`/api/events/${eventId}/screenshot`}
        alt="Captured screenshot"
        className="max-w-full border rounded shadow-sm"
        onError={() => setImgError("Failed to load screenshot (decryption error or missing blob).")}
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
          onClick={() => setReveal(false)}
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
