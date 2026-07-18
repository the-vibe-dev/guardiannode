import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { formatDateTime } from "../utils/datetime";

type Props = { alertId: string; detail: any };
type EvidenceOption = { id: string; label: string; text: string; defaultIncluded: boolean };

export default function GuardianReviewPanel({ alertId, detail }: Props) {
  const [provider, setProvider] = useState<any>(null);
  const [relationship, setRelationship] = useState("unknown");
  const [repeated, setRepeated] = useState("unknown");
  const [immediateDanger, setImmediateDanger] = useState(false);
  const [goal, setGoal] = useState("understand_context");
  const [goalDetails, setGoalDetails] = useState("");
  const [parentContext, setParentContext] = useState("");
  const [includeAge, setIncludeAge] = useState(true);
  const [includeEvidence, setIncludeEvidence] = useState(true);
  const [selectedEvidence, setSelectedEvidence] = useState<Set<string>>(
    () => new Set((detail.risk.evidence || []).map((_item: unknown, index: number) => `risk:${index}`)),
  );
  const [preview, setPreview] = useState<any>(null);
  const [consent, setConsent] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollTimer = useRef<number | null>(null);

  const evidenceOptions = useMemo<EvidenceOption[]>(() => {
    const riskItems = (detail.risk.evidence || []).map((text: string, index: number) => ({
      id: `risk:${index}`,
      label: `Detector evidence ${index + 1}`,
      text,
      defaultIncluded: true,
    }));
    if (detail.redacted_text) {
      riskItems.push({
        id: "event:text",
        label: "Additional extracted screen text",
        text: detail.redacted_text,
        defaultIncluded: false,
      });
    }
    return riskItems;
  }, [detail]);

  async function loadHistory() {
    setHistory(await api.guardianReviewHistory({ alert_id: alertId, limit: "25" }));
  }

  useEffect(() => {
    Promise.all([api.guardianReviewProviders(), api.guardianReviewHistory({ alert_id: alertId, limit: "25" })])
      .then(([status, rows]) => {
        setProvider(status);
        setHistory(rows);
        const active = rows.find((row: any) => ["queued", "running"].includes(row.status));
        if (active) pollReview(active.review_id).catch((e) => setError(e.message));
      })
      .catch((e) => setError(e.message));
    return () => {
      if (pollTimer.current !== null) window.clearTimeout(pollTimer.current);
    };
  }, [alertId]);

  async function makePreview() {
    setBusy("preview");
    setError(null);
    setResult(null);
    try {
      const next = await api.guardianReviewPreview(alertId, {
        relationship_context: relationship,
        repeated_behavior: repeated,
        parent_believes_immediate_danger: immediateDanger,
        parent_goal: goal,
        parent_goal_details: goalDetails.trim() || null,
        parent_context: parentContext.trim() || null,
        include_age_group: includeAge,
        include_evidence: includeEvidence,
        selected_evidence_ids: includeEvidence ? Array.from(selectedEvidence) : [],
      });
      setPreview(next);
      setConsent(false);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(null);
    }
  }

  async function cancelPreview() {
    if (!preview) return;
    setBusy("cancel");
    setError(null);
    try {
      await api.cancelGuardianReviewPreview(preview.preview_id);
      setPreview(null);
      setConsent(false);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(null);
    }
  }

  async function submit() {
    if (!preview || !consent) return;
    setBusy("submit");
    setError(null);
    try {
      const accepted = await api.submitGuardianReview(alertId, preview.preview_id, preview.preview_digest);
      setPreview(null);
      setConsent(false);
      await pollReview(accepted.review_id);
      await loadHistory();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(null);
    }
  }

  async function pollReview(reviewId: string) {
    const next = await api.guardianReview(reviewId);
    setResult(next);
    if (["queued", "running"].includes(next.status)) {
      pollTimer.current = window.setTimeout(() => {
        pollReview(reviewId).catch((e) => setError(e.message));
      }, 1500);
    }
  }

  async function deleteReview(reviewId: string) {
    if (!window.confirm("Delete the local Guardian Review preview and assessment? Minimal audit metadata will remain.")) return;
    setBusy(`delete:${reviewId}`);
    setError(null);
    try {
      await api.deleteGuardianReview(reviewId);
      if (result?.review_id === reviewId) setResult(await api.guardianReview(reviewId));
      await loadHistory();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(null);
    }
  }

  function toggleEvidence(id: string) {
    setSelectedEvidence((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  return (
    <section className="bg-white shadow rounded p-4 space-y-4" aria-labelledby="guardian-review-heading">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 id="guardian-review-heading" className="font-semibold">Guardian Review</h2>
          <p className="text-sm text-gray-600">A parent-controlled second opinion with conversation guidance.</p>
        </div>
        <span className={`text-xs font-semibold rounded-full px-2 py-1 ${provider?.ready ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-700"}`}>
          {provider?.ready ? `${provider.model} ready` : "Not configured"}
        </span>
      </div>

      {error && <div role="alert" className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm">{error}</div>}
      {!provider && <p className="text-sm text-gray-500">Checking Guardian Review status…</p>}
      {provider && !provider.ready && (
        <div className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          Guardian Review stays disabled until the selected provider is enabled and connected. Open <Link to="/settings" className="underline">Settings</Link> to finish setup.
        </div>
      )}

      {!preview && provider?.ready && (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Select label="Who is involved?" value={relationship} onChange={setRelationship} options={relationshipOptions} />
            <Select label="Has this happened repeatedly?" value={repeated} onChange={setRepeated} options={repeatOptions} />
            <Select label="What do you want help with?" value={goal} onChange={setGoal} options={goalOptions} />
            <label className="flex items-center gap-2 rounded border p-3 text-sm">
              <input type="checkbox" checked={immediateDanger} onChange={(e) => setImmediateDanger(e.target.checked)} />
              I believe there may be immediate danger
            </label>
          </div>
          <label className="block text-sm">
            <span className="font-medium">Goal details <span className="font-normal text-gray-500">(optional)</span></span>
            <input className="mt-1 w-full border rounded px-2 py-1" maxLength={300} value={goalDetails} onChange={(e) => setGoalDetails(e.target.value)} />
          </label>
          <label className="block text-sm">
            <span className="font-medium">Context you want the review to consider <span className="font-normal text-gray-500">(optional)</span></span>
            <textarea className="mt-1 w-full border rounded p-2" rows={3} maxLength={1500} value={parentContext} onChange={(e) => setParentContext(e.target.value)} />
          </label>

          <fieldset className="rounded border p-3 space-y-2">
            <legend className="px-1 text-sm font-medium">Optional information</legend>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={includeAge} onChange={(e) => setIncludeAge(e.target.checked)} />
              Include approximate age group
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={includeEvidence} onChange={(e) => setIncludeEvidence(e.target.checked)} />
              Include selected minimized evidence
            </label>
            {includeEvidence && evidenceOptions.map((item) => (
              <label key={item.id} className="ml-5 block rounded bg-gray-50 p-2 text-sm">
                <span className="flex items-start gap-2">
                  <input type="checkbox" className="mt-1" checked={selectedEvidence.has(item.id)} onChange={() => toggleEvidence(item.id)} />
                  <span><strong>{item.label}</strong>{!item.defaultIncluded && <span className="ml-1 text-xs text-amber-700">excluded by default</span>}<span className="block mt-1 text-xs text-gray-600 line-clamp-2">{item.text}</span></span>
                </span>
              </label>
            ))}
          </fieldset>
          <button onClick={makePreview} disabled={busy !== null} className="bg-brand-500 hover:bg-brand-700 disabled:opacity-50 text-white px-4 py-2 rounded text-sm">
            {busy === "preview" ? "Preparing locally…" : "Preview what would be sent"}
          </button>
        </div>
      )}

      {preview && (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded border border-green-200 bg-green-50 p-3">
              <h3 className="font-medium text-green-900">Stored locally — not transmitted</h3>
              <ul className="mt-2 list-disc pl-5 text-sm text-green-900 space-y-1">
                <li>The original screenshot, full extracted text, and device details</li>
                <li>Unselected evidence and optional fields you removed</li>
                <li>The complete encrypted alert record</li>
              </ul>
            </div>
            <div className="rounded border border-blue-200 bg-blue-50 p-3">
              <h3 className="font-medium text-blue-900">Sent to OpenAI if you continue</h3>
              <p className="mt-2 text-sm text-blue-900">{preview.disclosure}</p>
              <p className="mt-2 text-xs text-blue-800">{preview.retention_notice}</p>
            </div>
          </div>
          <div>
            <div className="flex flex-wrap justify-between gap-2 text-xs text-gray-600">
              <span>Exact minimized content · {preview.character_count} characters</span>
              <span>{preview.model_requested} · {preview.redaction_version}</span>
            </div>
            <pre data-testid="guardian-review-outbound" className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-words rounded border bg-gray-950 p-3 text-xs text-gray-100">{JSON.stringify(preview.outbound_payload, null, 2)}</pre>
            <p className="mt-2 text-xs text-gray-500">Information categories: {preview.information_categories.join(", ") || "none"}</p>
          </div>
          <label className="flex items-start gap-2 rounded border p-3 text-sm">
            <input type="checkbox" className="mt-1" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            <span>I reviewed the exact content above and choose to send it to the external model for this Guardian Review.</span>
          </label>
          <div className="flex flex-wrap gap-2">
            <button onClick={submit} disabled={!consent || busy !== null} className="bg-brand-500 hover:bg-brand-700 disabled:opacity-50 text-white px-4 py-2 rounded text-sm">
              {busy === "submit" ? "Sending…" : "Send for Guardian Review"}
            </button>
            <button onClick={cancelPreview} disabled={busy !== null} className="bg-gray-100 hover:bg-gray-200 disabled:opacity-50 text-gray-900 px-4 py-2 rounded text-sm">
              {busy === "cancel" ? "Cancelling…" : "Cancel — send nothing"}
            </button>
          </div>
        </div>
      )}

      {result && <AssessmentResult result={result} />}

      <div className="border-t pt-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-medium">Review history for this alert</h3>
          <Link className="text-sm text-brand-700 underline" to="/guardian-reviews">View all Guardian Reviews</Link>
        </div>
        {history.length === 0 ? <p className="mt-2 text-sm text-gray-500">No Guardian Reviews yet.</p> : (
          <ul className="mt-2 divide-y rounded border">
            {history.map((item) => (
              <li key={item.review_id} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
                <button className="text-left" onClick={() => pollReview(item.review_id)}>
                  <span className="font-medium capitalize">{item.status.replace("_", " ")}</span>
                  <span className="block text-xs text-gray-500">{formatDateTime(item.created_at)} · {item.model_requested} · {item.redaction_version}</span>
                </button>
                {!["queued", "running", "deleted"].includes(item.status) && (
                  <button onClick={() => deleteReview(item.review_id)} disabled={busy !== null} className="text-xs text-red-700 underline">Delete local assessment</button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

export function AssessmentResult({ result }: { result: any }) {
  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const [feedback, setFeedback] = useState<Set<string>>(new Set());
  const [feedbackStatus, setFeedbackStatus] = useState<string | null>(null);
  const [savingFeedback, setSavingFeedback] = useState(false);

  useEffect(() => {
    if (result.status === "completed") {
      headingRef.current?.focus();
      api.guardianReviewFeedback(result.review_id)
        .then((row) => { if (row?.labels) setFeedback(new Set(row.labels)); })
        .catch(() => undefined);
    }
  }, [result.review_id, result.status]);

  async function saveFeedback() {
    if (feedback.size === 0) return;
    setSavingFeedback(true);
    setFeedbackStatus(null);
    try {
      await api.saveGuardianReviewFeedback(result.review_id, Array.from(feedback));
      setFeedbackStatus("Feedback saved locally. It will not automatically train or change Guardian Review.");
    } catch (error: any) {
      setFeedbackStatus(error.message || "Feedback could not be saved.");
    } finally {
      setSavingFeedback(false);
    }
  }

  function toggleFeedback(label: string) {
    setFeedback((current) => {
      const next = new Set(current);
      if (next.has(label)) next.delete(label); else next.add(label);
      return next;
    });
  }

  if (["queued", "running"].includes(result.status)) return <div role="status" aria-live="polite" className="rounded border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900"><span className="font-medium">Guardian Review is {result.status}.</span><span className="block mt-1">You can leave or refresh this page. The durable local history will resume this review.</span></div>;
  if (result.status === "deleted") return <div className="rounded border bg-gray-50 p-3 text-sm text-gray-700">This local assessment and its outbound preview were deleted. Minimal audit metadata remains.</div>;
  if (result.status === "failed") return <div role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{result.error?.message || "Guardian Review failed safely."}</div>;
  const a = result.assessment;
  if (!a) return null;
  return (
    <div className="rounded border border-brand-200 bg-brand-50 p-4 space-y-5" aria-live="polite">
      <div className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
        <strong>A second opinion, not a finding of fact.</strong> Do not punish or accuse a child based only on an AI assessment. Review the local evidence, begin with curiosity when facts are incomplete, and keep the final decision with the parent.
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 ref={headingRef} tabIndex={-1} className="font-semibold text-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500">Guardian Review communication plan</h3>
        <span className="text-xs uppercase font-semibold rounded-full bg-white px-3 py-1 border">{a.assessment.replace("_", " ")} · {a.severity}</span>
      </div>
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
        <Metric label="Assessment" value={a.assessment.replace("_", " ")} />
        <Metric label="Severity" value={a.severity} />
        <Metric label="Confidence" value={`${Math.round(Number(a.confidence || 0) * 100)}%`} />
        <Metric label="Category" value={String(a.category || "unknown").replaceAll("_", " ")} />
      </dl>
      <div><h4 className="font-medium">Assessment summary</h4><p className="mt-1 text-sm">{a.plain_language_summary}</p></div>
      <ResultList title="What was observed" items={a.observed_facts} />
      <ResultList title="Why this may be concerning" items={a.inferences} />
      <EvidenceList items={a.supporting_evidence} />
      <ResultList title="Possible benign explanations" items={a.possible_benign_explanations} />
      <ResultList title="What is still unknown" items={a.missing_context} />
      <ResultList title="Questions to consider first" items={a.questions_parent_should_answer} />

      <section className="rounded border bg-white p-4 space-y-3" aria-labelledby={`conversation-${result.review_id}`}>
        <h4 id={`conversation-${result.review_id}`} className="font-semibold">How to approach your child</h4>
        <div><h5 className="font-medium text-sm">Recommended tone</h5><p className="text-sm mt-1 capitalize">{String(a.recommended_parent_tone?.tone || "calm and curious").replaceAll("_", " ")}</p><p className="text-xs text-gray-600 mt-1">{a.recommended_parent_tone?.rationale}</p></div>
        <div><h5 className="font-medium text-sm">Suggested opening words</h5><blockquote className="mt-1 border-l-4 border-brand-300 pl-3 text-sm">{a.suggested_opening_language}</blockquote></div>
        <ResultList title="Questions to ask" items={a.questions_to_ask_child} />
        <ResultList title="Approaches or phrases to avoid" items={a.phrases_or_approaches_to_avoid} />
        <p className="text-xs text-gray-600">Separate immediate safety from later discipline. Preserve trust where possible, and seek qualified professional assistance when the situation exceeds this product's role.</p>
      </section>

      <ActionList title="Immediate actions" items={a.immediate_actions} timingKey="priority" />
      <ActionList title="Follow-up actions" items={a.follow_up_actions} timingKey="timeframe" />
      <ResultList title="Escalation indicators" items={a.escalation_indicators} />
      <ResultList title="Model limitations" items={a.limitations} />

      <fieldset className="rounded border bg-white p-4">
        <legend className="px-1 font-medium">Was this Guardian Review useful?</legend>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {feedbackOptions.map(([key, label]) => <label key={key} className="flex items-center gap-2 rounded border p-2 text-sm focus-within:ring-2 focus-within:ring-brand-500"><input type="checkbox" checked={feedback.has(key)} onChange={() => toggleFeedback(key)} />{label}</label>)}
        </div>
        <button type="button" onClick={saveFeedback} disabled={savingFeedback || feedback.size === 0} className="mt-3 rounded bg-brand-500 px-4 py-2 text-sm text-white disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-700 focus-visible:ring-offset-2">{savingFeedback ? "Saving locally…" : "Save feedback"}</button>
        {feedbackStatus && <p role="status" className="mt-2 text-xs text-gray-700">{feedbackStatus}</p>}
      </fieldset>

      <p className="text-xs text-gray-500">Model {result.model_returned || result.model_requested} · schema {result.schema_version} · prompt {result.prompt_version} · redaction {result.redaction_version}{result.usage?.total_tokens != null ? ` · ${result.usage.total_tokens} tokens` : ""}</p>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="rounded bg-white p-2 border"><dt className="text-xs text-gray-500">{label}</dt><dd className="font-medium capitalize">{value}</dd></div>;
}

function EvidenceList({ items }: { items: any[] }) {
  if (!items?.length) return null;
  return <div><h4 className="font-medium">Supporting evidence</h4><ul className="mt-1 space-y-2 text-sm">{items.map((item, index) => <li key={`${item.evidence_id}-${index}`} className="rounded border bg-white p-2"><span className="font-mono text-xs text-gray-500">{item.evidence_id}</span><span className="block">{item.observation}</span><span className="block text-xs text-gray-600">Why it matters: {item.relevance}</span></li>)}</ul></div>;
}

function ActionList({ title, items, timingKey }: { title: string; items: any[]; timingKey: "priority" | "timeframe" }) {
  if (!items?.length) return null;
  return <div><h4 className="font-medium">{title}</h4><ul className="mt-1 space-y-2 text-sm">{items.map((item, index) => <li key={`${title}-${index}`} className="rounded border bg-white p-2"><span className="text-xs font-semibold uppercase text-brand-700">{String(item[timingKey] || "").replaceAll("_", " ")}</span><span className="block font-medium">{item.action}</span><span className="block text-xs text-gray-600">{item.rationale}</span></li>)}</ul></div>;
}

function ResultList({ title, items }: { title: string; items: string[] }) {
  if (!items?.length) return null;
  return <div><h4 className="font-medium">{title}</h4><ul className="mt-1 list-disc pl-5 text-sm space-y-1">{items.map((item, index) => <li key={`${title}-${index}`}>{item}</li>)}</ul></div>;
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: Array<[string, string]> }) {
  return <label className="text-sm"><span className="font-medium">{label}</span><select className="mt-1 block w-full border rounded px-2 py-2" value={value} onChange={(e) => onChange(e.target.value)}>{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select></label>;
}

const relationshipOptions: Array<[string, string]> = [["unknown", "Not sure"], ["unknown_person", "Unknown person"], ["known_peer", "Known peer"], ["known_adult", "Known adult"], ["family_member", "Family member"], ["school_or_activity_contact", "School or activity contact"], ["other", "Other"]];
const repeatOptions: Array<[string, string]> = [["unknown", "Not sure"], ["yes", "Yes"], ["no", "No"]];
const goalOptions: Array<[string, string]> = [["understand_context", "Understand the context"], ["assess_urgency", "Assess urgency"], ["prepare_conversation", "Prepare a conversation"], ["plan_follow_up", "Plan follow-up"], ["other", "Other"]];
const feedbackOptions: Array<[string, string]> = [["helpful", "Helpful"], ["inaccurate", "Inaccurate"], ["too_alarmist", "Too alarmist"], ["too_dismissive", "Too dismissive"], ["missing_context", "Missing context"], ["needs_follow_up", "Needs follow-up"]];
