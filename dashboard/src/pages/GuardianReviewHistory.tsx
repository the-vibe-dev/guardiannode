import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { AssessmentResult } from "../components/GuardianReviewPanel";
import { formatDateTime } from "../utils/datetime";

export default function GuardianReviewHistory() {
  const [rows, setRows] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    const params: Record<string, string> = { limit: "200" };
    if (status) params.status = status;
    setRows(await api.guardianReviewHistory(params));
  }

  useEffect(() => { load().catch((e) => setError(e.message)); }, [status]);

  async function view(reviewId: string) {
    setError(null);
    try { setSelected(await api.guardianReview(reviewId)); }
    catch (e: any) { setError(e.message || String(e)); }
  }

  async function remove(reviewId: string) {
    if (!window.confirm("Delete the local Guardian Review preview and assessment? Minimal audit metadata will remain.")) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteGuardianReview(reviewId);
      if (selected?.review_id === reviewId) setSelected(await api.guardianReview(reviewId));
      await load();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-2xl font-bold">Guardian Review history</h1><p className="text-sm text-gray-600">Local assessment history and privacy metadata across incidents.</p></div>
        <label className="text-sm"><span className="text-xs text-gray-500">Status</span><select className="block border rounded px-2 py-1 mt-1" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option><option value="completed">Completed</option><option value="failed">Failed</option><option value="queued">Queued</option><option value="running">Running</option><option value="deleted">Deleted</option></select></label>
      </div>
      {error && <div role="alert" className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm">{error}</div>}
      <div className="overflow-x-auto bg-white shadow rounded">
        <table className="min-w-[850px] w-full text-sm">
          <thead className="bg-gray-100 text-left text-xs uppercase text-gray-500"><tr><th className="p-3">Created</th><th className="p-3">Incident</th><th className="p-3">Status</th><th className="p-3">Model</th><th className="p-3">Privacy contract</th><th className="p-3">Actions</th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={6} className="p-6 text-center text-gray-500">No Guardian Reviews found.</td></tr>}
            {rows.map((row) => <tr key={row.review_id} className="border-t align-top"><td className="p-3">{formatDateTime(row.created_at)}</td><td className="p-3"><Link className="text-brand-700 underline" to={`/alerts/${row.alert_id}`}>View alert</Link></td><td className="p-3 capitalize">{row.status.replace("_", " ")}</td><td className="p-3"><code className="text-xs">{row.model_returned || row.model_requested}</code></td><td className="p-3 text-xs">schema {row.schema_version}<br />prompt {row.prompt_version}<br />{row.redaction_version}</td><td className="p-3"><div className="flex gap-3"><button className="text-brand-700 underline" onClick={() => view(row.review_id)}>View</button>{!["queued", "running", "deleted"].includes(row.status) && <button className="text-red-700 underline" disabled={busy} onClick={() => remove(row.review_id)}>Delete local assessment</button>}</div></td></tr>)}
          </tbody>
        </table>
      </div>
      {selected && <AssessmentResult result={selected} />}
    </div>
  );
}
