import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, HardDrive, HeartHandshake, LockKeyhole, Mail, ShieldCheck } from "lucide-react";
import { api, type ConsentWithdrawalResult } from "../api";

const choiceDefinitions = [
  { key: "screenshots", label: "Review screenshots", detail: "Capture the visible screen for local safety checks. Turning this off stops screenshot monitoring.", icon: Eye },
  { key: "apps_and_urls", label: "Record app and web context", detail: "Keep separate app, URL, and window-title metadata. Turning this off omits those fields from new events; screenshots and OCR may still contain visible context.", icon: ShieldCheck },
  { key: "retention", label: "Keep alert history", detail: "Retain evidence according to Settings. Turning this off pauses new monitoring because processing without retained history is not yet supported. Existing evidence keeps its retention schedule.", icon: HardDrive },
  { key: "notifications", label: "Send parent notifications", detail: "Allow automatic alerts and metadata-only digests through configured channels. Turning this off stops automatic sends.", icon: Mail },
] as const;

type ChoiceKey = typeof choiceDefinitions[number]["key"];

export default function PrivacyConsent() {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: ["consent"], queryFn: api.consentStatus });
  const [selected, setSelected] = useState<Record<ChoiceKey, boolean>>({ screenshots: true, apps_and_urls: true, retention: true, notifications: true });
  const [notice, setNotice] = useState(false);
  const [externalAi, setExternalAi] = useState(false);
  const [withdrawalOutcome, setWithdrawalOutcome] = useState<{ disposition: "retain" | "delete"; result: ConsentWithdrawalResult } | null>(null);

  useEffect(() => {
    const saved = status.data?.record?.choices;
    if (!saved) return;
    setSelected((previous) => Object.fromEntries(Object.keys(previous).map((key) => [key, Boolean(saved[key])])) as Record<ChoiceKey, boolean>);
    setExternalAi(Boolean(saved.external_ai));
    setNotice(Boolean(saved.child_notice_acknowledged));
  }, [status.data]);

  const grant = useMutation({
    mutationFn: () => api.grantConsent(status.data!.notice_version, { ...selected, external_ai: externalAi, child_notice_acknowledged: notice }),
    onSuccess: () => {
      setWithdrawalOutcome(null);
      queryClient.invalidateQueries({ queryKey: ["consent"] });
      queryClient.invalidateQueries({ queryKey: ["onboarding"] });
      queryClient.invalidateQueries({ queryKey: ["notification-status"] });
    },
  });
  const withdraw = useMutation({
    mutationFn: (disposition: "retain" | "delete") => api.withdrawConsent(disposition),
    onSuccess: (result, disposition) => {
      setWithdrawalOutcome({ disposition, result });
      queryClient.setQueryData(["consent"], result);
      queryClient.invalidateQueries({ queryKey: ["consent"] });
      queryClient.invalidateQueries({ queryKey: ["onboarding"] });
      queryClient.invalidateQueries({ queryKey: ["notification-status"] });
      queryClient.invalidateQueries({ queryKey: ["devices"] });
      queryClient.removeQueries({ queryKey: ["alerts"] });
      queryClient.removeQueries({ queryKey: ["overview"] });
      queryClient.removeQueries({ queryKey: ["capture-status"] });
    },
  });

  if (status.isPending) return <div className="page-status" role="status">Loading privacy choices…</div>;
  if (status.error) return <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">{(status.error as Error).message}</div>;

  function submit(event: FormEvent) {
    event.preventDefault();
    grant.mutate();
  }

  function stopMonitoring(disposition: "retain" | "delete") {
    const detail = disposition === "delete"
      ? "Monitoring will stop and paired device credentials will be revoked. GuardianNode will attempt to delete retained family evidence and queued captures. Any failures will need another attempt. Backups, existing exports and downloaded copies are not included. Deleted evidence cannot be recovered by this action."
      : "Monitoring will stop and paired device credentials will be revoked. Existing evidence will remain until its retention deadline or until you delete it.";
    if (window.confirm(`${detail}\n\nContinue?`)) withdraw.mutate(disposition);
  }

  return (
    <div className="space-y-6">
      <header><p className="mb-1 text-sm font-medium text-[#275e3d]">Parent controls</p><h1 className="font-display text-2xl font-bold text-[#18313a] sm:text-3xl">Privacy & consent</h1><p className="mt-2 max-w-3xl text-sm text-slate-600">Choose what your family is comfortable monitoring. These choices are recorded locally and can be withdrawn at any time.</p></header>
      <div className={`flex items-center gap-3 rounded-xl border p-4 ${status.data!.active ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
        <span className="grid h-10 w-10 place-items-center rounded-full bg-white"><HeartHandshake aria-hidden="true" className={status.data!.active ? "text-emerald-700" : "text-amber-700"} /></span>
        <div><strong className="block text-[#18313a]">{status.data!.active ? (status.data!.record?.choices.retention === false ? "Privacy choices saved; new monitoring is paused" : "Current consent is active") : "Monitoring is waiting for your consent"}</strong><span className="text-xs text-slate-600">Privacy notice {status.data!.notice_version}</span></div>
      </div>
      <form onSubmit={submit} className="rounded-xl border border-slate-200 bg-white p-5 sm:p-6">
        <fieldset><legend className="font-display text-lg font-semibold">What GuardianNode may process</legend><p className="mt-1 text-sm text-slate-500">All core safety analysis stays on your GuardianNode server.</p>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">{choiceDefinitions.map((choice) => { const Icon = choice.icon; return (
            <label key={choice.key} className="flex cursor-pointer gap-3 rounded-lg border border-slate-200 p-4 hover:border-sky-300"><input type="checkbox" checked={selected[choice.key]} onChange={(event) => setSelected({ ...selected, [choice.key]: event.target.checked })} className="mt-1 h-4 w-4 accent-[#275e3d]" /><span><span className="flex items-center gap-2 font-semibold text-[#18313a]"><Icon aria-hidden="true" size={17} />{choice.label}</span><span className="mt-1 block text-xs leading-5 text-slate-600">{choice.detail}</span></span></label>
          ); })}</div>
        </fieldset>
        {!selected.retention && <p role="status" className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Saving with alert history disabled pauses new monitoring. Turn history back on and save to resume eligible devices.</p>}
        <label className="mt-4 flex cursor-pointer gap-3 rounded-lg border border-slate-200 p-4"><input type="checkbox" checked={externalAi} onChange={(event) => setExternalAi(event.target.checked)} className="mt-1 h-4 w-4 accent-[#275e3d]" /><span><span className="flex items-center gap-2 font-semibold"><LockKeyhole aria-hidden="true" size={17} />Allow optional external AI review</span><span className="mt-1 block text-xs leading-5 text-slate-600">Off by default. This choice and a separate preview and parent confirmation are both required for every external review.</span></span></label>
        <label className="mt-4 flex cursor-pointer gap-3 rounded-lg bg-[#f3f6f8] p-4"><input required type="checkbox" checked={notice} onChange={(event) => setNotice(event.target.checked)} className="mt-1 h-4 w-4 accent-[#275e3d]" /><span><strong className="block text-sm">I have shown the child-facing monitoring notice.</strong><span className="mt-1 block text-xs leading-5 text-slate-600">It explains that GuardianNode is active, what parents can review, and how the child can make a request.</span></span></label>
        <div className="mt-5 flex flex-wrap gap-3">
          <button disabled={grant.isPending || withdraw.isPending || !notice} className="min-h-11 rounded-lg bg-[#0d3b4a] px-5 py-2 text-sm font-semibold text-white hover:bg-[#164f60] disabled:opacity-50">{status.data!.active ? "Update choices" : "Agree and continue"}</button>
          {status.data!.active && <>
            <button type="button" disabled={withdraw.isPending || grant.isPending} onClick={() => stopMonitoring("retain")} className="min-h-11 rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">Withdraw and retain evidence…</button>
            <button type="button" disabled={withdraw.isPending || grant.isPending} onClick={() => stopMonitoring("delete")} className="min-h-11 rounded-lg border border-red-200 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50">Withdraw and delete evidence…</button>
          </>}
          {!status.data!.active && status.data!.record?.status === "withdrawn" && <button type="button" disabled={withdraw.isPending || grant.isPending} onClick={() => stopMonitoring("delete")} className="min-h-11 rounded-lg border border-red-200 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50">{withdraw.isPending ? "Retrying deletion…" : status.data!.record.choices.evidence_disposition === "delete" ? "Retry evidence deletion…" : "Delete remaining evidence…"}</button>}
        </div>
        {(grant.error || withdraw.error) && <p role="alert" className="mt-3 text-sm text-red-700">{((grant.error || withdraw.error) as Error).message}</p>}
        {grant.isSuccess && !withdrawalOutcome && <p role="status" className="mt-3 text-sm text-emerald-800">Privacy choices saved.</p>}
      </form>
      {withdrawalOutcome && <WithdrawalOutcome disposition={withdrawalOutcome.disposition} result={withdrawalOutcome.result} />}
      {status.data!.record?.status === "withdrawn" && <p className="text-xs text-slate-600">Backups, existing exports and downloaded copies are not included in evidence deletion. Manage those copies separately. You can retry deletion while monitoring remains stopped. <a href="/settings" className="font-semibold text-brand-700 underline">View persistent queue and deletion status in Settings.</a></p>}
    </div>
  );
}

function WithdrawalOutcome({ disposition, result }: { disposition: "retain" | "delete"; result: ConsentWithdrawalResult }) {
  if (disposition === "retain") return <div role="status" className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">Monitoring stopped and paired device credentials were revoked. Existing evidence was retained under its retention schedule.</div>;
  const deletion = result.deletion;
  const pendingFailed = deletion?.pending_captures?.failed ?? 0;
  const partial = pendingFailed > 0 || (deletion?.remaining_events ?? 0) > 0 || (deletion?.remaining_blobs ?? 0) > 0;
  return <div role={partial ? "alert" : "status"} className={`space-y-2 rounded-lg border p-4 text-sm ${partial ? "border-amber-200 bg-amber-50 text-amber-950" : "border-slate-200 bg-slate-50 text-slate-800"}`}>
    <p className="font-semibold">{partial ? "Monitoring stopped; some evidence still needs deletion." : "Monitoring stopped. Deletion attempt finished."}</p>
    {deletion ? <>
      <p>Removed {deletion.events ?? 0} event records and {deletion.blobs ?? 0} retained evidence files.{deletion.pending_captures && ` Removed ${deletion.pending_captures.deleted} queued capture files.`}</p>
      {pendingFailed > 0 && <p>Queued capture cleanup reported {pendingFailed} {pendingFailed === 1 ? "failure" : "failures"}. Some queued files may remain.</p>}
      {(deletion.remaining_events !== undefined || deletion.remaining_blobs !== undefined) && <p>Remaining: {deletion.remaining_events ?? "unknown"} event records and {deletion.remaining_blobs ?? "unknown"} retained evidence files.</p>}
      {partial && <p>Retry evidence deletion. If failures continue, check storage permissions and available disk space.</p>}
    </> : <p>The server did not return deletion totals. You can retry evidence deletion to check the remaining files.</p>}
    <p>Backups, existing exports and downloaded copies are not included.</p>
  </div>;
}
