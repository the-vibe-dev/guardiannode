import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Check, CircleAlert, Clock3, Laptop, ShieldCheck, UsersRound } from "lucide-react";
import { Link } from "react-router-dom";
import { api, type Alert, type Device, type Profile } from "../api";
import { formatDateTime } from "../utils/datetime";

export default function Dashboard() {
  const overview = useQuery({ queryKey: ["overview"], queryFn: api.overview, refetchInterval: 15_000 });
  const alerts = useQuery({ queryKey: ["alerts", "home"], queryFn: () => api.alerts({ limit: "5" }) });
  const devices = useQuery({ queryKey: ["devices"], queryFn: api.devices });
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: api.profiles });
  const requests = useQuery({ queryKey: ["child-requests", "open"], queryFn: () => api.childRequests({ status: "open", limit: "5" }) });
  const onboarding = useQuery({ queryKey: ["onboarding"], queryFn: api.onboardingStatus });
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });

  const firstError = [overview, alerts, devices, profiles, requests, onboarding].find((query) => query.error)?.error;
  if (firstError) return <ErrorState message={(firstError as Error).message} />;
  if ([overview, alerts, devices, profiles, requests, onboarding].some((query) => query.isPending)) {
    return <div className="page-status" role="status">Loading your family overview…</div>;
  }

  const data = overview.data!;
  const openRequests = requests.data!.open_count;
  const attentionCount = data.open_alert_count + openRequests;
  const deviceRows = devices.data!;
  const profileRows = profiles.data!;

  return (
    <div className="space-y-6">
      <header className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
        <div>
          <p className="mb-1 text-sm font-medium text-[#275e3d]">Family overview</p>
          <h1 className="font-display text-2xl font-bold tracking-tight text-[#18313a] sm:text-3xl">
            Good {greeting()}, {me.data?.display_name || "Parent"}
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">A calm summary of what needs you, what is covered, and whether protection is working.</p>
        </div>
        <div className="inline-flex items-center gap-2 self-start rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-800" role="status">
          <span className="h-2 w-2 rounded-full bg-emerald-600" /> Local protection active
        </div>
      </header>

      {!onboarding.data!.complete && <OnboardingCard currentStep={onboarding.data!.current_step} steps={onboarding.data!.steps} />}

      <section aria-labelledby="attention-heading" className="rounded-xl border border-slate-200 bg-white p-5 shadow-[0_8px_28px_rgba(13,59,74,0.06)] sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-[#18313a]"><CircleAlert aria-hidden="true" className="text-amber-600" size={21} /><h2 id="attention-heading" className="font-display text-lg font-semibold">Needs your attention</h2></div>
            <p className="mt-1 text-sm text-slate-500">{attentionCount ? `${attentionCount} item${attentionCount === 1 ? "" : "s"} waiting for a parent` : "Nothing needs action right now"}</p>
          </div>
          <Link to="/risks" className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold text-[#0d3b4a] hover:bg-slate-50">Review alerts <ArrowRight aria-hidden="true" size={16} /></Link>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <AttentionStat label="Critical or high today" value={data.counts_24h.critical + data.counts_24h.high} tone="urgent" />
          <AttentionStat label="Open alerts" value={data.open_alert_count} />
          <AttentionStat label="Child requests" value={openRequests} href="/requests" />
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.35fr_0.9fr]">
        <section aria-labelledby="activity-heading" className="rounded-xl border border-slate-200 bg-white p-5 sm:p-6">
          <div className="flex items-center justify-between gap-3"><h2 id="activity-heading" className="font-display text-lg font-semibold">Recent activity</h2><Link to="/risks" className="text-sm font-semibold text-[#275e3d] hover:underline">View all</Link></div>
          <div className="mt-4 divide-y divide-slate-100">
            {alerts.data!.items.length ? alerts.data!.items.map((alert) => <ActivityRow key={alert.alert_id} alert={alert} profiles={profileRows} devices={deviceRows} />) : <EmptyActivity />}
          </div>
        </section>

        <div className="space-y-6">
          <Coverage profiles={profileRows} devices={deviceRows} />
          <section aria-labelledby="system-heading" className="rounded-xl border border-slate-200 bg-white p-5">
            <div className="flex items-center gap-2"><ShieldCheck aria-hidden="true" className="text-[#275e3d]" size={20} /><h2 id="system-heading" className="font-display font-semibold">System status</h2></div>
            <dl className="mt-4 space-y-3 text-sm">
              <StatusRow label="Devices online" value={`${data.devices_online} of ${data.devices_total}`} ok={data.devices_total > 0 && data.devices_online === data.devices_total} />
              <StatusRow label="Devices paused" value={String(data.devices_paused)} ok={data.devices_paused === 0} />
              <StatusRow label="Data location" value="This server" ok />
            </dl>
            <Link to="/settings" className="mt-4 inline-flex min-h-11 items-center gap-1 text-sm font-semibold text-[#275e3d] hover:underline">Open diagnostics <ArrowRight aria-hidden="true" size={15} /></Link>
          </section>
        </div>
      </div>
    </div>
  );
}

function greeting() {
  const hour = new Date().getHours();
  return hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
}

function AttentionStat({ label, value, tone, href }: { label: string; value: number; tone?: "urgent"; href?: string }) {
  const content = <><span className={`font-display text-2xl font-bold ${tone && value ? "text-red-700" : "text-[#18313a]"}`}>{value}</span><span className="text-sm text-slate-600">{label}</span></>;
  const classes = "flex min-h-20 flex-col justify-center rounded-lg border border-slate-200 bg-[#f8fafb] px-4 py-3";
  return href ? <Link className={`${classes} hover:border-[#7ec6f5]`} to={href}>{content}</Link> : <div className={classes}>{content}</div>;
}

function ActivityRow({ alert, profiles, devices }: { alert: Alert; profiles: Profile[]; devices: Device[] }) {
  const child = profiles.find((profile) => profile.profile_id === alert.profile_id)?.display_name;
  const device = devices.find((row) => row.device_id === alert.device_id)?.hostname;
  const label = child || device || "Family device";
  return (
    <Link to={`/alerts/${alert.alert_id}`} className="group grid gap-3 py-4 first:pt-1 sm:grid-cols-[auto_1fr_auto] sm:items-center">
      <SeverityDot severity={alert.severity} />
      <span className="min-w-0"><span className="block truncate text-sm font-semibold text-[#18313a] group-hover:text-[#275e3d]">{alert.summary || alert.categories[0]?.replaceAll("_", " ") || "Safety alert ready for review"}</span><span className="mt-1 block text-xs text-slate-500">{label}{alert.app_name ? ` · ${alert.app_name}` : ""} · {formatDateTime(alert.created_at)}</span></span>
      <span className="justify-self-start rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold capitalize text-slate-700 sm:justify-self-end">{alert.severity}</span>
    </Link>
  );
}

function SeverityDot({ severity }: { severity: string }) {
  const urgent = severity === "critical" || severity === "high";
  return <span className={`grid h-9 w-9 place-items-center rounded-full ${urgent ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-700"}`}>{urgent ? <AlertTriangle aria-hidden="true" size={17} /> : <Clock3 aria-hidden="true" size={17} />}</span>;
}

function EmptyActivity() {
  return <div className="flex items-center gap-3 py-8 text-sm text-slate-600"><span className="grid h-10 w-10 place-items-center rounded-full bg-emerald-50 text-emerald-700"><Check aria-hidden="true" size={19} /></span><span><strong className="block text-[#18313a]">No recent alerts</strong>Your latest reviewed activity will appear here.</span></div>;
}

function Coverage({ profiles, devices }: { profiles: Profile[]; devices: Device[] }) {
  return (
    <section aria-labelledby="coverage-heading" className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex items-center gap-2"><UsersRound aria-hidden="true" className="text-[#275e3d]" size={20} /><h2 id="coverage-heading" className="font-display font-semibold">Family coverage</h2></div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <Link to="/profiles" className="rounded-lg bg-[#f3f6f8] p-4 hover:bg-slate-100"><span className="font-display text-2xl font-bold">{profiles.length}</span><span className="mt-1 block text-xs text-slate-600">Children</span></Link>
        <Link to="/devices" className="rounded-lg bg-[#f3f6f8] p-4 hover:bg-slate-100"><span className="font-display text-2xl font-bold">{devices.length}</span><span className="mt-1 block text-xs text-slate-600">Devices</span></Link>
      </div>
      <div className="mt-4 space-y-2">{devices.slice(0, 3).map((device) => <div key={device.device_id} className="flex items-center justify-between gap-3 text-sm"><span className="flex min-w-0 items-center gap-2"><Laptop aria-hidden="true" size={15} className="shrink-0 text-slate-500" /><span className="truncate">{device.hostname}</span></span><span className={`text-xs font-semibold capitalize ${device.status === "online" ? "text-emerald-700" : "text-slate-500"}`}>{device.status.replaceAll("_", " ")}</span></div>)}</div>
    </section>
  );
}

function StatusRow({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return <div className="flex items-center justify-between gap-4"><dt className="text-slate-600">{label}</dt><dd className="flex items-center gap-1.5 font-semibold text-[#18313a]"><span className={`h-2 w-2 rounded-full ${ok ? "bg-emerald-600" : "bg-amber-500"}`} />{value}</dd></div>;
}

const stepLabels: Record<string, string> = { timezone: "Set your family timezone", child: "Add a child", notice: "Review the monitoring notice", privacy_choices: "Choose privacy settings", pairing: "Pair a child device", self_test: "Run the first device check", recovery: "Store your recovery kit" };

function OnboardingCard({ currentStep, steps }: { currentStep: string | null; steps: Array<{ id: string; complete: boolean }> }) {
  const done = steps.filter((step) => step.complete).length;
  const target = currentStep === "child" ? "/profiles" : currentStep === "pairing" || currentStep === "self_test" ? "/devices" : currentStep === "notice" || currentStep === "privacy_choices" ? "/privacy" : "/settings";
  return <section className="flex flex-col justify-between gap-4 rounded-xl border border-sky-200 bg-sky-50 p-5 sm:flex-row sm:items-center"><div><p className="text-xs font-semibold uppercase tracking-wider text-sky-800">Finish setup · {done} of {steps.length}</p><h2 className="mt-1 font-display font-semibold text-[#18313a]">{stepLabels[currentStep || ""] || "Complete family setup"}</h2><p className="mt-1 text-sm text-slate-600">GuardianNode will keep this checklist here until protection is ready.</p></div><Link to={target} className="inline-flex min-h-11 shrink-0 items-center justify-center gap-1.5 rounded-lg bg-[#0d3b4a] px-4 py-2 text-sm font-semibold text-white hover:bg-[#164f60]">Continue setup <ArrowRight aria-hidden="true" size={16} /></Link></section>;
}

function ErrorState({ message }: { message: string }) {
  return <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-5 text-red-800"><strong>Couldn’t load the family overview.</strong><p className="mt-1 text-sm">{message}</p></div>;
}
