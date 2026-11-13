import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ActionExecution, type DeviceAction } from "../api";
import { formatDateTime, toUtcDate } from "../utils/datetime";

const actionLabels: Record<string, string> = { pause_app: "Legacy app pause", block_domain: "Legacy domain block", show_child_prompt: "Legacy child notice", delete_evidence: "Delete evidence", undo_action: "Undo action" };
const statusLabels: Record<string, string> = { queued: "Queued", claimed: "Claimed by device", succeeded: "Succeeded", failed: "Failed", rejected: "Rejected", expired: "Expired", completed: "Completed", pending_delete: "Deletion pending" };
const waiting = (status: string) => ["queued", "claimed"].includes(status);
const buttonClass = "min-h-10 rounded-lg border border-slate-300 px-3 text-sm font-semibold disabled:opacity-50";
const counters: Array<[keyof ActionExecution, string]> = [
  ["matched_processes", "Matched processes"], ["suspended_processes", "Suspended processes"],
  ["newly_suspended_processes", "Newly suspended"], ["resumed_processes", "Resumed processes"],
  ["failed_processes", "Failed processes"], ["skipped_protected_processes", "Protected processes skipped"],
  ["already_suspended_elsewhere", "Already suspended elsewhere"], ["uninspectable_processes", "Could not inspect"],
  ["stale_process_records", "Stale process records"], ["pending_resume_processes", "Waiting to resume"],
  ["pending_recovery_processes", "Waiting for recovery"], ["legacy_unverified_processes", "Legacy records unverified"],
  ["active_pause_leases", "Active pause leases"], ["undone", "Actions undone"],
  ["removed_domain_entries", "Legacy domain entries removed"], ["pending_domain_blocks", "Legacy domain blocks awaiting removal"],
];

export default function ActionHistory({ alertId }: { alertId: string }) {
  return <IncidentActionHistory key={alertId} alertId={alertId} />;
}

function IncidentActionHistory({ alertId }: { alertId: string }) {
  const client = useQueryClient();
  const queryKey = ["alert-actions", alertId];
  const history = useQuery({
    queryKey,
    queryFn: () => api.alertActions(alertId),
    refetchInterval: (query) => query.state.data?.some((action) => waiting(action.status)) ? 15_000 : false,
  });
  const undo = useMutation({
    mutationFn: api.undoAction,
    onMutate: () => client.cancelQueries({ queryKey }),
    onSuccess: (result) => {
      client.setQueryData<DeviceAction[]>(queryKey, (current = []) => [result, ...current.filter((action) => action.action_id !== result.action_id)].slice(0, 50));
      void client.invalidateQueries({ queryKey });
    },
    onError: () => { void client.invalidateQueries({ queryKey }); },
  });
  const rows = history.data ?? [];
  const latestUndo = rows.find((action) => action.action_id === undo.data?.action_id) ?? undo.data;
  const retryableUndo = (action: DeviceAction) => ["failed", "rejected", "expired"].includes(action.status) || (waiting(action.status) && toUtcDate(action.expires_at).getTime() <= Date.now());
  const knownUndos = undo.data && !rows.some((row) => row.action_id === undo.data.action_id) ? [...rows, undo.data] : rows;
  const hasUndo = new Set(knownUndos.flatMap((action) => action.undo_of && !retryableUndo(action) ? [action.undo_of] : []));

  return <section aria-labelledby="action-history-heading" className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
    <header className="flex flex-wrap items-center justify-between gap-3"><h2 id="action-history-heading" className="font-display font-semibold text-[#18313a]">Action history</h2><button className={buttonClass} disabled={history.isFetching || undo.isPending} onClick={() => void history.refetch()}>Refresh action history</button></header>
    <p className="text-sm text-slate-600">Latest 50 actions for this alert. Status reflects the latest received command result. A completed command’s result is not refreshed as device conditions change.</p>
    <p className="text-xs text-slate-500">Queued and claimed actions refresh every 15 seconds. Earlier restriction records remain available only for recovery; new restrictions cannot be created. Failed, rejected, or expired release attempts can be retried.</p>
    {history.isPending && <p role="status" className="text-sm text-slate-500">Loading action history…</p>}
    {history.isError && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Action history is unavailable: {history.error.message}. {history.data && "Previously loaded reports may be out of date. "}<button className="font-semibold underline" onClick={() => void history.refetch()}>Retry action history</button></p>}
    {undo.isPending && <p role="status" className="text-sm text-slate-600">Requesting undo…</p>}
    {undo.isSuccess && latestUndo && <p role="status" className="rounded-lg bg-sky-50 p-3 text-sm text-sky-950">{waiting(latestUndo.status) ? "Undo is queued. It is not applied until the endpoint reports its result. Check the undo entry below." : `Latest undo report: ${statusLabels[latestUndo.status] || latestUndo.status}. Review the report and any remaining pause warnings below.`}</p>}
    {undo.isError && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">Could not queue undo: {undo.error.message}. Refresh history to check whether a request was recorded before retrying.</p>}
    {history.data && rows.length === 0 && <p className="text-sm text-slate-500">No actions have been recorded for this alert.</p>}
    {rows.length > 0 && <ol className="space-y-3">
      {rows.map((action) => {
        const execution = action.execution;
        const reversible = !action.undo_of && ["pause_app", "block_domain"].includes(action.action);
        const partialPause = action.action === "pause_app" && execution?.lease_status === "active" && (execution.partial_failure || action.status === "failed" || (execution.failed_processes ?? 0) > 0);
        return <li key={action.action_id} className="space-y-2 rounded-lg border border-slate-200 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold">{actionLabels[action.action] || action.action}</h3><span className={`rounded-full px-2 py-1 text-xs font-semibold ${["failed", "rejected"].includes(action.status) ? "bg-red-50 text-red-800" : waiting(action.status) ? "bg-amber-50 text-amber-900" : "bg-slate-100 text-slate-700"}`}>{statusLabels[action.status] || action.status}</span></div>
          <p className="break-words text-sm text-slate-700">{action.preview}</p>
          <p className="text-xs text-slate-500">Created {formatDateTime(action.created_at)} · Last report: {action.completed_at ? formatDateTime(action.completed_at) : "awaiting a completion report"}</p>
          {waiting(action.status) && <p className="text-xs text-slate-600">{action.status === "queued" ? "Waiting for the device to receive this command." : "The device claimed this command; completion has not been reported."}</p>}
          {action.status === "expired" && <p className="text-xs text-amber-900">The command delivery deadline expired. This status does not establish whether a previously applied pause has ended.</p>}
          {partialPause && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-950">Last report: some processes may remain paused{execution.lease_expires_at ? ` until ${formatDateTime(execution.lease_expires_at)} or until undo is applied` : ". Queue undo to request their release"}. Check the device if access has not returned.</p>}
          {execution && <ExecutionDetails execution={execution} isUndo={action.action === "undo_action"} />}
          <p className="text-xs text-slate-500">Command delivery deadline: {formatDateTime(action.expires_at)}</p>
          {reversible && (hasUndo.has(action.action_id)
            ? <p className="text-xs text-slate-600">An active or successful undo is already recorded for this action. Its result appears in this history.</p>
            : <button className={buttonClass} disabled={undo.isPending || history.isFetching} onClick={() => undo.mutate(action.action_id)} aria-label={`Queue undo: ${action.preview}`}>Queue undo</button>)}
        </li>;
      })}
    </ol>}
    {rows.length === 50 && <p className="text-xs text-slate-500">Showing the latest 50 actions. Older actions may exist.</p>}
  </section>;
}

function ExecutionDetails({ execution, isUndo }: { execution: ActionExecution; isUndo: boolean }) {
  const resume = execution.pending_resume_processes;
  const recovery = execution.pending_recovery_processes;
  const observed = counters.filter(([key]) => typeof execution[key] === "number");
  return <>
    {((resume ?? 0) > 0 || (recovery ?? 0) > 0) && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-950">Last report: processes waiting to resume: {resume ?? "not reported"}; processes waiting for recovery: {recovery ?? "not reported"}. Later background recovery may not update this receipt. Check the child device if access has not returned.</p>}
    {(execution.pending_domain_blocks ?? 0) > 0 && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-950">Last report: {execution.pending_domain_blocks} legacy domain blocks still require removal. Check recovery on the child device.</p>}
    {isUndo && (execution.active_pause_leases ?? 0) > 0 && <p role="status" className="text-sm text-amber-900">Last report: {execution.active_pause_leases} other pause leases remained active. Undoing this action does not end those other pauses.</p>}
    {(execution.lease_status === "legacy_unverified" || (execution.legacy_unverified_processes ?? 0) > 0) && <p role="alert" className="text-sm text-amber-900">The last report contains unverified legacy process records. Check the device; recovery cannot be confirmed from this receipt.</p>}
    {execution.persistence_failed && <p role="alert" className="text-sm text-red-800">The device reported a problem saving recovery state. {execution.rollback_succeeded ? "The same report says the immediate rollback succeeded." : "A successful rollback was not confirmed. Check the device."}</p>}
    <details className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-700"><summary className="cursor-pointer font-semibold">Last reported execution details</summary>
      {execution.lease_status && <p className="mt-2">Reported pause state: {execution.lease_status.replaceAll("_", " ")}</p>}
      {execution.lease_expires_at && <p className="mt-1">App pause deadline: {formatDateTime(execution.lease_expires_at)}</p>}
      {execution.scan_complete === false && <p className="mt-1">The process scan was incomplete.</p>}
      {execution.partial_failure && <p className="mt-1">The device reported a partial failure.</p>}
      {execution.has_error && <p className="mt-1">The device reported an execution error.</p>}
      {observed.length > 0 && <dl className="mt-2 grid gap-x-4 gap-y-1 sm:grid-cols-2">{observed.map(([key, label]) => <div key={key} className="flex justify-between gap-3"><dt>{label}</dt><dd className="font-semibold">{execution[key] as number}</dd></div>)}</dl>}
    </details>
  </>;
}
