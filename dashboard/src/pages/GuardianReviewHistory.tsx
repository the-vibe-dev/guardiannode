import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { AssessmentResult } from "../components/GuardianReviewPanel";
import { useGuardianReviewSelection } from "../hooks/useGuardianReviewSelection";
import { formatDateTime } from "../utils/datetime";

export default function GuardianReviewHistory() {
  const [rows, setRows] = useState<any[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const historyVersion = useRef(0);
  const deletedIds = useRef(new Set<string>());
  const selection = useGuardianReviewSelection();

  const load = useCallback(async () => {
    const current = ++historyVersion.current;
    setLoading(true);
    setError(null);
    const params: Record<string, string> = { limit: "200" };
    if (status) params.status = status;
    try {
      const next = await api.guardianReviewHistory(params);
      if (current !== historyVersion.current) return;
      setRows(next.map((row) => deletedIds.current.has(row.review_id) ? { ...row, status: "deleted" } : row));
    } catch (reason) {
      if (current === historyVersion.current) setError(`Could not refresh review history: ${reason instanceof Error ? reason.message : "History is unavailable."}`);
    } finally {
      if (current === historyVersion.current) setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    setRows([]);
    void load();
    return () => { historyVersion.current += 1; };
  }, [load]);

  async function remove(reviewId: string) {
    if (!window.confirm("Delete the local Guardian Review preview and assessment? Minimal audit metadata will remain.")) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteGuardianReview(reviewId);
      deletedIds.current.add(reviewId);
      selection.recordDeletion(reviewId);
      setRows((current) => current.map((row) => row.review_id === reviewId ? { ...row, status: "deleted" } : row));
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not delete this assessment.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-2xl font-bold">Guardian Review history</h1><p className="text-sm text-gray-600">Local assessment history and privacy metadata across incidents. Showing up to 200 recent reviews.</p></div>
        <div className="flex items-end gap-3"><label className="text-sm"><span className="text-xs text-gray-500">Status</span><select className="block border rounded px-2 py-1 mt-1" value={status} disabled={busy} onChange={(e) => setStatus(e.target.value)}><option value="">All</option><option value="completed">Completed</option><option value="failed">Failed</option><option value="queued">Queued</option><option value="running">Running</option><option value="deleted">Deleted</option></select></label><button className="min-h-11 text-sm font-semibold text-brand-700 underline disabled:opacity-50" onClick={() => void load()} disabled={loading || busy}>Refresh history</button></div>
      </div>
      {error && <div role="alert" className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm">{error} <button className="font-semibold underline" onClick={() => void load()} disabled={loading || busy}>Retry history</button></div>}
      {loading && <p role="status" className="text-sm text-slate-600">Loading review history…</p>}
      <div role="region" aria-label="Guardian Review history" tabIndex={0} className="overflow-x-auto bg-white shadow rounded">
        <table className="min-w-[850px] w-full text-sm">
          <caption className="sr-only">Guardian Reviews, newest first</caption>
          <thead className="bg-gray-100 text-left text-xs uppercase text-gray-500"><tr><th scope="col" className="p-3">Created</th><th scope="col" className="p-3">Incident</th><th scope="col" className="p-3">Status</th><th scope="col" className="p-3">Model</th><th scope="col" className="p-3">Privacy contract</th><th scope="col" className="p-3">Actions</th></tr></thead>
          <tbody>
            {!loading && !error && rows.length === 0 && <tr><td colSpan={6} className="p-6 text-center text-gray-500">No Guardian Reviews found.</td></tr>}
            {rows.map((row) => <tr key={row.review_id} className="border-t align-top"><td className="p-3">{formatDateTime(row.created_at)}</td><td className="p-3"><Link className="text-brand-700 underline" to={`/alerts/${row.alert_id}`}>View alert</Link></td><td className="p-3 capitalize">{row.status.replaceAll("_", " ")}</td><td className="p-3"><code className="text-xs">{row.model_returned || row.model_requested}</code></td><td className="p-3 text-xs">schema {row.schema_version}<br />prompt {row.prompt_version}<br />{row.redaction_version}</td><td className="p-3"><div className="flex gap-3"><button className="text-brand-700 underline disabled:opacity-50" disabled={busy} aria-label={`View review ${row.review_id}`} onClick={() => void selection.view(row.review_id)}>View</button>{!["queued", "running", "deleted"].includes(row.status) && <button className="text-red-700 underline disabled:opacity-50" disabled={busy} aria-label={`Delete local assessment ${row.review_id}`} onClick={() => void remove(row.review_id)}>Delete local assessment</button>}</div></td></tr>)}
          </tbody>
        </table>
      </div>
      {selection.loading && <p role="status" className="text-sm text-slate-600">Loading selected assessment…</p>}
      {selection.error && <div role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">Could not load selected assessment: {selection.error} <button className="font-semibold underline" onClick={selection.retry}>Retry assessment</button></div>}
      {selection.result && <AssessmentResult key={selection.result.review_id} result={selection.result} />}
    </div>
  );
}
