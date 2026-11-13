import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type CaptureQueueInventory, type CaptureQueuePolicy, type CaptureQueueStatus } from "../api";
import { formatDateTime } from "../utils/datetime";

const mib = 1024 * 1024;
type PolicyDraft = { days: string; maxMiB: string; batch: string };
const toDraft = (policy: CaptureQueuePolicy): PolicyDraft => ({ days: String(policy.dead_letter_retention_days), maxMiB: String(policy.dead_letter_max_bytes / mib), batch: String(policy.cleanup_batch_files) });
const buttonClass = "min-h-10 rounded-lg border border-slate-300 px-3 text-sm font-semibold disabled:opacity-50";

export default function CaptureQueue({ onCleanup }: { onCleanup?: () => void | Promise<void> }) {
  const client = useQueryClient();
  const status = useQuery({ queryKey: ["capture-queue"], queryFn: api.captureQueue, refetchInterval: 30_000 });
  // A status refresh never replaces edits. A null draft follows the latest saved policy.
  const [edited, setEdited] = useState<PolicyDraft | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const update = useMutation({
    mutationFn: api.updateCaptureQueuePolicy,
    onMutate: () => client.cancelQueries({ queryKey: ["capture-queue"] }),
    onSuccess: (result) => {
      client.setQueryData(["capture-queue"], result);
      setEdited(null);
      setNotice("Capture queue policy saved. Cleanup uses this policy on its next run.");
    },
  });
  const cleanup = useMutation({
    mutationFn: api.runCaptureQueueCleanup,
    onMutate: () => client.cancelQueries({ queryKey: ["capture-queue"] }),
    onSuccess: async (result) => {
      client.setQueryData(["capture-queue"], result);
      setNotice(`Queue cleanup attempt finished: ${result.cleanup.deleted_files} queued capture files removed. Review the status below for remaining work.`);
      await onCleanup?.();
    },
  });
  const data = status.data;
  const draft = edited ?? (data ? toDraft(data.policy) : null);
  const busy = update.isPending || cleanup.isPending;

  function save(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    const days = Number(draft.days), maxMiB = Number(draft.maxMiB), batch = Number(draft.batch);
    if (!draft.days.trim() || !Number.isInteger(days) || days < 1 || days > 90 || !draft.maxMiB.trim() || !Number.isFinite(maxMiB) || maxMiB < 1 || maxMiB > 4096 || !draft.batch.trim() || !Number.isInteger(batch) || batch < 1 || batch > 1000) {
      setValidationError("Choose 1–90 whole days, 1–4096 MiB of quarantine storage, and 1–1000 whole files per cleanup run.");
      return;
    }
    setValidationError(null);
    setNotice(null);
    cleanup.reset();
    update.mutate({ dead_letter_retention_days: days, dead_letter_max_bytes: Math.round(maxMiB * mib), cleanup_batch_files: batch });
  }

  return <section aria-labelledby="capture-queue-heading" className="space-y-4 rounded-xl border border-slate-200 bg-white p-4">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="capture-queue-heading" className="font-semibold">Capture queue & evidence deletion</h2>
      <button className={buttonClass} disabled={status.isFetching || busy} onClick={() => void status.refetch()}>Refresh queue status</button>
    </header>
    <p className="text-sm text-slate-600">Pending captures wait for processing. Failed captures are quarantined so processing can continue. These counts contain file metadata only.</p>
    <p className="text-xs text-slate-500">Status refreshes every 30 seconds while this page is active. Refreshing leaves policy edits intact.</p>
    {status.isPending && <p role="status" className="text-sm text-slate-500">Loading capture queue…</p>}
    {status.isError && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Capture queue status is unavailable: {status.error.message}. {data && "Previously loaded counts may be out of date. "}<button className="font-semibold underline" onClick={() => void status.refetch()}>Retry queue status</button></p>}
    {data && draft && <>
      {!data.worker.enabled && <p role="status" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Automatic queue housekeeping is disabled. Run cleanup manually, or enable the server worker to resume scheduled attempts.</p>}
      {data.worker.enabled && <p className="text-xs text-slate-500">Automatic housekeeping checks every {data.worker.interval_seconds} seconds while the worker is running.</p>}
      <div className="grid gap-3 sm:grid-cols-2"><Inventory title="Pending captures" value={data.pending} /><Inventory title="Quarantined captures" value={data.dead_letter} /></div>
      <form onSubmit={save} noValidate className="space-y-3 rounded-lg border border-slate-200 p-3">
        <fieldset disabled={update.isPending} className="min-w-0 space-y-3">
          <legend className="text-sm font-semibold">Quarantine cleanup policy</legend>
          <p className="text-xs text-slate-600">Age and storage limits delete quarantined captures only. Pending captures are not removed by these limits. Existing evidence deletion requests are retried separately. Large queues may need several bounded runs to reach the limits.</p>
          <div className="grid gap-3 sm:grid-cols-3">
            <PolicyField label="Quarantine retention (days)" value={draft.days} min={1} max={90} onChange={(days) => setEdited({ ...draft, days })} />
            <PolicyField label="Quarantine storage limit (MiB)" value={draft.maxMiB} min={1} max={4096} step="any" onChange={(maxMiB) => setEdited({ ...draft, maxMiB })} />
            <PolicyField label="Files per cleanup run" value={draft.batch} min={1} max={1000} onChange={(batch) => setEdited({ ...draft, batch })} />
          </div>
          {validationError && <p role="alert" className="text-sm text-red-800">{validationError}</p>}
          <div className="flex flex-wrap gap-2">
            <button disabled={busy} className="min-h-10 rounded-lg bg-brand-700 px-3 text-sm font-semibold text-white disabled:opacity-50">{update.isPending ? "Saving queue policy…" : "Save queue policy"}</button>
            {edited && <button type="button" className={buttonClass} disabled={busy} onClick={() => { setEdited(null); setValidationError(null); }}>Discard queue policy edits</button>}
          </div>
        </fieldset>
      </form>
      {(update.error || cleanup.error) && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{update.error ? "Queue policy was not saved" : "Queue cleanup could not start"}: {(update.error || cleanup.error)?.message}. Your policy edits remain available.</p>}
      {notice && <p role="status" className="rounded-lg bg-slate-50 p-3 text-sm text-slate-700">{notice}</p>}
      <div className="space-y-2 rounded-lg bg-slate-50 p-3 text-sm">
        <h3 className="font-semibold">Last queue cleanup</h3>
        <p>{data.cleanup.last_run_at ? `Attempted ${formatDateTime(data.cleanup.last_run_at)}` : "No cleanup attempt recorded."}</p>
        {data.cleanup.last_run_at && <p>{data.cleanup.deleted_files} queued capture files removed ({formatBytes(data.cleanup.deleted_bytes)}); {data.cleanup.expired_files} quarantined files expired and {data.cleanup.quota_files} were removed for the storage limit.</p>}
        {data.cleanup.failed_files > 0 && <p role="alert" className="text-amber-900">{data.cleanup.failed_files} files could not be removed. They remain for a later attempt.</p>}
        {(data.cleanup.budget_exhausted || data.cleanup.scan_truncated) && <p role="status" className="text-amber-900">This cleanup reached its file or scan limit. More work may remain for the next run.</p>}
      </div>
      <WithdrawalStatus value={data.withdrawal_cleanup} />
      <div className="space-y-2">
        <button className={buttonClass} disabled={busy} onClick={() => { setNotice(null); setValidationError(null); update.reset(); cleanup.mutate(); }}>{cleanup.isPending ? "Running queue cleanup…" : "Run queue cleanup"}</button>
        <p className="text-xs text-slate-600">Uses the saved quarantine policy and resumes any previously requested withdrawal deletion. Save policy edits first. Backups, exports, and downloaded copies are managed separately.</p>
      </div>
    </>}
  </section>;
}

function Inventory({ title, value }: { title: string; value: CaptureQueueInventory }) {
  return <div className="space-y-2 rounded-lg border border-slate-200 p-3 text-sm">
    <h3 className="font-semibold">{title}</h3>
    <p>{value.scan_truncated ? "At least " : ""}{value.frames} captures · {value.files} files · {formatBytes(value.bytes)}</p>
    <p className="text-xs text-slate-500">Oldest observed file: {formatDateTime(value.oldest_at)}</p>
    {value.scan_truncated && <p role="status" className="text-xs text-amber-900">Inventory scan reached its limit. These counts are lower bounds; more files may remain.</p>}
    {(value.orphan_files > 0 || value.unsafe_files > 0) && <p role="status" className="text-xs text-amber-900">{value.orphan_files} files without a matching pair in this scan and {value.unsafe_files} unsafe entries need attention.</p>}
  </div>;
}

function WithdrawalStatus({ value }: { value: CaptureQueueStatus["withdrawal_cleanup"] }) {
  const remains = value.pending || value.inventory_incomplete || value.remaining_files > 0 || value.remaining_events > 0 || value.remaining_blobs > 0;
  return <div className={`space-y-2 rounded-lg border p-3 text-sm ${remains ? "border-amber-200 bg-amber-50 text-amber-950" : "border-slate-200 text-slate-700"}`}>
    <h3 className="font-semibold">Evidence deletion after consent withdrawal</h3>
    {!value.requested_at ? <p>No evidence deletion request recorded.</p> : <>
      <p role="status" className="font-medium">{remains ? "Deletion remains queued for retry." : "The recorded evidence deletion request is complete."}</p>
      <p>Remaining known targets: {value.remaining_files} queued files, {value.remaining_events} event records, and {value.remaining_blobs} retained evidence files.</p>
      <p className="text-xs">Known targets include files awaiting another check; a previous attempt may already have removed them.</p>
      <p className="text-xs">Requested {formatDateTime(value.requested_at)} · {value.attempts} attempts · last attempted {formatDateTime(value.last_attempt_at)}</p>
      {value.last_failed_files > 0 && <p>{value.last_failed_files} file deletions failed on the last attempt. Check server storage permissions if failures continue.</p>}
    </>}
    {value.inventory_incomplete && <p role="alert">The deletion inventory is incomplete. Additional files may remain even when the known counters are zero.</p>}
    <p className="text-xs">Backups, existing exports, and downloaded copies are not included.</p>
  </div>;
}

function PolicyField({ label, value, min, max, step = "1", onChange }: { label: string; value: string; min: number; max: number; step?: string; onChange: (value: string) => void }) {
  return <label className="text-sm"><span className="font-medium">{label}</span><input type="number" min={min} max={max} step={step} value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 min-h-10 w-full rounded-lg border border-slate-300 px-3" /></label>;
}

function formatBytes(value: number) {
  return value >= mib ? `${(value / mib).toFixed(1)} MiB` : value >= 1024 ? `${(value / 1024).toFixed(1)} KiB` : `${value} B`;
}
