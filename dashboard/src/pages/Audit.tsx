import { useMemo, useState, type FormEvent } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { api, type AuditEntry } from "../api";
import { formatDateTime } from "../utils/datetime";

type Filters = { action: string; actor: string; q: string; since: string; until: string };
const emptyFilters: Filters = { action: "", actor: "", q: "", since: "", until: "" };
const inputClass = "mt-1 min-h-11 w-full rounded-lg border border-slate-300 px-3";

function dateBoundary(day: string, nextDay = false) {
  const date = new Date(`${day}T00:00:00`);
  if (nextDay) date.setDate(date.getDate() + 1);
  return date.toISOString();
}

export default function Audit() {
  const [draft, setDraft] = useState<Filters>(emptyFilters);
  const [applied, setApplied] = useState<Filters>(emptyFilters);
  const [validationError, setValidationError] = useState<string | null>(null);
  const params: Record<string, string> = { limit: "50" };
  if (applied.action) params.action = applied.action;
  if (applied.actor) params.actor = applied.actor;
  if (applied.q) params.q = applied.q;
  if (applied.since) params.since = dateBoundary(applied.since);
  if (applied.until) params.until = dateBoundary(applied.until, true);

  const history = useInfiniteQuery({
    queryKey: ["audit", "history", params],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => api.auditPage({ ...params, ...(pageParam ? { cursor: pageParam } : {}) }),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
  const rows = useMemo(() => {
    const unique = new Map<number, AuditEntry>();
    for (const page of history.data?.pages ?? []) for (const row of page.items) unique.set(row.id, row);
    return [...unique.values()];
  }, [history.data]);
  const changed = (Object.keys(draft) as Array<keyof Filters>).some((key) => draft[key].trim() !== applied[key]);
  const hasFilters = Object.values(draft).some(Boolean) || Object.values(applied).some(Boolean);

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    if (draft.since && draft.until && draft.since > draft.until) {
      setValidationError("Choose a through date on or after the from date.");
      return;
    }
    try {
      if (draft.since) dateBoundary(draft.since);
      if (draft.until) dateBoundary(draft.until, true);
    } catch {
      setValidationError("Choose valid dates before applying filters.");
      return;
    }
    setValidationError(null);
    setApplied({ ...draft, actor: draft.actor.trim(), action: draft.action.trim(), q: draft.q.trim() });
  }

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-bold text-[#18313a] sm:text-3xl">Audit</h1>
          <p className="mt-2 text-sm text-slate-600">Review parent and system activity across the complete retained audit history.</p>
        </div>
        <button onClick={() => void history.refetch()} disabled={history.isFetching} className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm font-semibold disabled:opacity-50">Refresh audit history</button>
      </header>

      <form aria-label="Filter audit history" onSubmit={applyFilters} className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label className="text-sm sm:col-span-2 lg:col-span-3"><span className="font-medium text-slate-700">Search audit metadata</span><input type="search" className={inputClass} maxLength={200} value={draft.q} onChange={(event) => setDraft({ ...draft, q: event.target.value })} placeholder="Actor, action, target, or source IP…" /></label>
          <label className="text-sm"><span className="font-medium text-slate-700">Action (exact)</span><input className={inputClass} maxLength={128} value={draft.action} onChange={(event) => setDraft({ ...draft, action: event.target.value })} placeholder="alert.view" /></label>
          <label className="text-sm"><span className="font-medium text-slate-700">Actor (exact)</span><input className={inputClass} maxLength={255} value={draft.actor} onChange={(event) => setDraft({ ...draft, actor: event.target.value })} placeholder="admin or system" /></label>
          <label className="text-sm"><span className="font-medium text-slate-700">From date</span><input type="date" className={inputClass} value={draft.since} onChange={(event) => setDraft({ ...draft, since: event.target.value })} /></label>
          <label className="text-sm"><span className="font-medium text-slate-700">Through date</span><input type="date" className={inputClass} value={draft.until} onChange={(event) => setDraft({ ...draft, until: event.target.value })} /></label>
          <div className="flex flex-wrap items-end gap-2 sm:col-span-2">
            <button className="min-h-11 rounded-lg bg-brand-700 px-4 text-sm font-semibold text-white">Apply filters</button>
            {hasFilters && <button type="button" className="min-h-11 rounded-lg border border-slate-300 px-3 text-sm font-semibold" onClick={() => { setDraft(emptyFilters); setApplied(emptyFilters); setValidationError(null); }}>Clear filters</button>}
          </div>
        </div>
        <p className="text-xs text-slate-500">Dates include the whole selected day in this browser’s local timezone. Search covers retained metadata; it does not search the Details field.</p>
        {changed && <p role="status" className="text-xs text-slate-600">Filters changed. Apply filters to update these results.</p>}
        {validationError && <p role="alert" className="text-sm text-red-800">{validationError}</p>}
      </form>

      {history.isError && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">Could not load {history.isFetchNextPageError ? "older " : ""}audit entries: {history.error.message}. <button className="font-semibold underline" onClick={() => void (history.isFetchNextPageError ? history.fetchNextPage() : history.refetch())}>Retry audit history</button>{history.data && <p className="mt-1">Previously loaded results remain visible. They may be out of date.</p>}</div>}
      {history.isPending && <p role="status" className="text-sm text-slate-500">Loading audit history…</p>}
      {history.data && <>
        <div aria-live="polite" className="flex flex-wrap justify-between gap-2 text-xs text-slate-600"><span>{rows.length} of {history.data.pages[0].total} retained audit entries loaded{history.hasNextPage ? " · more available" : " · end of results"}</span><span>{history.isFetching ? "Updating…" : `Updated ${formatDateTime(history.dataUpdatedAt)}`}</span></div>
        <div role="region" aria-label="Audit results" tabIndex={0} className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="min-w-[900px] w-full text-left">
            <caption className="sr-only">Retained audit entries, newest first</caption>
            <thead className="bg-slate-50 text-xs uppercase text-slate-600"><tr>{["Time", "Actor", "Action", "Target", "Source IP", "Details"].map((label) => <th key={label} scope="col" className="p-3">{label}</th>)}</tr></thead>
            <tbody>
              {rows.length === 0 && <tr><td colSpan={6} className="p-6 text-center text-sm text-slate-500">No retained audit entries match these filters.</td></tr>}
              {rows.map((row) => <tr key={row.id} className="border-t border-slate-100 align-top">
                <td className="p-3 text-sm text-slate-600">{formatDateTime(row.created_at)}</td>
                <td className="p-3 text-sm break-words">{row.actor}</td>
                <td className="p-3 text-sm font-medium">{row.action}</td>
                <td className="p-3 text-sm break-words">{row.target || "—"}</td>
                <td className="p-3 text-xs">{row.source_ip || "—"}</td>
                <td className="max-w-sm p-3 font-mono text-xs break-words">{JSON.stringify(row.details || {})}</td>
              </tr>)}
            </tbody>
          </table>
        </div>
        {history.hasNextPage && <button className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-4 text-sm font-semibold disabled:opacity-50" disabled={history.isFetching} onClick={() => void history.fetchNextPage()}>{history.isFetchingNextPage ? "Loading older audit entries…" : "Load older audit entries"}</button>}
      </>}
    </div>
  );
}
