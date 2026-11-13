import { useEffect, useMemo, useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { api } from "../api";
import SeverityBadge from "../components/SeverityBadge";
import { formatDateTime } from "../utils/datetime";

function dateBoundary(day: string, nextDay = false): string {
  const date = new Date(`${day}T00:00:00`);
  if (nextDay) date.setDate(date.getDate() + 1);
  return date.toISOString();
}

export default function RiskFeed() {
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const invalidRange = Boolean(since && until && since > until);

  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(query.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [query]);

  const devices = useQuery({ queryKey: ["devices"], queryFn: api.devices });
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: api.profiles });
  const params: Record<string, string> = { limit: "50" };
  if (severity) params.severity = severity;
  if (status) params.status = status;
  if (deviceId) params.device_id = deviceId;
  if (profileId) params.profile_id = profileId;
  if (search) params.q = search;
  if (since) params.since = dateBoundary(since);
  if (until) params.until = dateBoundary(until, true);

  const feed = useInfiniteQuery({
    queryKey: ["alerts", "feed", params],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => api.alerts({ ...params, ...(pageParam ? { cursor: pageParam } : {}) }),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: !invalidRange,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });
  const alerts = useMemo(() => {
    const unique = new Map<string, NonNullable<typeof feed.data>["pages"][number]["items"][number]>();
    for (const page of feed.data?.pages ?? []) for (const alert of page.items) unique.set(alert.alert_id, alert);
    return [...unique.values()];
  }, [feed.data]);
  const deviceNames = useMemo(() => new Map((devices.data ?? []).map((device) => [device.device_id, device.hostname])), [devices.data]);
  const profileNames = useMemo(() => new Map((profiles.data ?? []).map((profile) => [profile.profile_id, profile.display_name])), [profiles.data]);
  const openCount = feed.data?.pages[0]?.open_count;
  const hasFilters = Boolean(severity || status || deviceId || profileId || query || since || until);

  function clearFilters() {
    setSeverity(""); setStatus(""); setDeviceId(""); setProfileId("");
    setQuery(""); setSearch(""); setSince(""); setUntil("");
  }

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="mb-1 text-sm font-medium text-[#275e3d]">Family safety signals</p>
          <h1 className="font-display text-2xl font-bold text-[#18313a] sm:text-3xl">Risk feed</h1>
          <p className="mt-2 text-sm text-slate-600">Review alerts from every child and device. Search covers all retained alerts.</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {openCount !== undefined && <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800">{openCount} open across family</span>}
          <button onClick={() => void feed.refetch()} disabled={feed.isFetching || invalidRange} className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm font-semibold disabled:opacity-50"><RefreshCw aria-hidden="true" size={16} /> Refresh</button>
        </div>
      </header>
      <section aria-label="Filter alerts" className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
        <div role="group" aria-label="Severity" className="flex flex-wrap gap-2 text-sm">
          {["", "critical", "high", "medium", "low"].map((value) => <button key={value || "all"} aria-pressed={severity === value} onClick={() => setSeverity(value)} className={`min-h-10 rounded-lg border px-3 capitalize ${severity === value ? "border-brand-700 bg-brand-700 text-white" : "border-slate-300 text-slate-700"}`}>{value || "All severities"}</button>)}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label className="text-sm sm:col-span-2 lg:col-span-3"><span className="font-medium text-slate-700">Search alerts</span><input type="search" maxLength={200} className="mt-1 min-h-11 w-full rounded-lg border border-slate-300 px-3" placeholder="What happened, app, or category…" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
          <label className="text-sm"><span className="font-medium text-slate-700">Status</span><select className="mt-1 min-h-11 w-full rounded-lg border border-slate-300 px-3" value={status} onChange={(event) => setStatus(event.target.value)}>{["", "open", "reviewed", "false_positive", "escalated", "dismissed"].map((value) => <option key={value || "any"} value={value}>{value ? value.replaceAll("_", " ") : "Any status"}</option>)}</select></label>
          <label className="text-sm"><span className="font-medium text-slate-700">Child</span><select className="mt-1 min-h-11 w-full rounded-lg border border-slate-300 px-3" value={profileId} onChange={(event) => setProfileId(event.target.value)}><option value="">All children</option>{(profiles.data ?? []).map((profile) => <option key={profile.profile_id} value={profile.profile_id}>{profile.display_name}</option>)}</select></label>
          <label className="text-sm"><span className="font-medium text-slate-700">Device</span><select className="mt-1 min-h-11 w-full rounded-lg border border-slate-300 px-3" value={deviceId} onChange={(event) => setDeviceId(event.target.value)}><option value="">All devices</option>{(devices.data ?? []).map((device) => <option key={device.device_id} value={device.device_id}>{device.hostname}</option>)}</select></label>
          <label className="text-sm"><span className="font-medium text-slate-700">From date</span><input type="date" className="mt-1 min-h-11 w-full rounded-lg border border-slate-300 px-3" value={since} onChange={(event) => setSince(event.target.value)} /></label>
          <label className="text-sm"><span className="font-medium text-slate-700">Through date</span><input type="date" className="mt-1 min-h-11 w-full rounded-lg border border-slate-300 px-3" value={until} onChange={(event) => setUntil(event.target.value)} /></label>
          {hasFilters && <button className="min-h-11 self-end rounded-lg border border-slate-300 px-3 text-sm font-semibold text-slate-700" onClick={clearFilters}>Clear filters</button>}
        </div>
        <p className="text-xs text-slate-500">Dates use this browser’s local timezone. Results refresh every 30 seconds while this page is active.</p>
        {(devices.isError || profiles.isError) && <p role="status" className="text-sm text-amber-800">Some family names could not load. Alerts remain available with their device and profile IDs. <button className="underline" onClick={() => { void devices.refetch(); void profiles.refetch(); }}>Retry names</button></p>}
      </section>
      {invalidRange && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">Choose a through date on or after the from date.</p>}
      {!invalidRange && feed.isError && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">Could not load {feed.isFetchNextPageError ? "older " : ""}alerts: {feed.error.message}. <button onClick={() => void (feed.isFetchNextPageError ? feed.fetchNextPage() : feed.refetch())} className="font-semibold underline">Retry</button></div>}
      {!invalidRange && feed.isPending && <p role="status" className="page-status">Loading alerts…</p>}
      {!invalidRange && feed.data && <>
        <div className="flex flex-wrap justify-between gap-2 text-xs text-slate-500" aria-live="polite"><span>{alerts.length} {alerts.length === 1 ? "alert" : "alerts"} loaded{feed.hasNextPage ? " · more available" : " · end of results"}</span><span>{query.trim() !== search ? "Searching…" : feed.isFetching ? "Updating…" : `Updated ${formatDateTime(feed.dataUpdatedAt)}`}</span></div>
        <div role="region" aria-label="Alert results" tabIndex={0} className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="min-w-[760px] w-full">
            <caption className="sr-only">Alerts matching the selected filters, newest first</caption>
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500"><tr><th scope="col" className="p-3">Severity</th><th scope="col" className="p-3">What happened</th><th scope="col" className="p-3">Where</th><th scope="col" className="p-3">Status</th><th scope="col" className="p-3">When</th><th scope="col" className="p-3"><span className="sr-only">Review</span></th></tr></thead>
            <tbody>
              {alerts.length === 0 && <tr><td colSpan={6} className="p-8 text-center text-sm text-slate-500">{hasFilters ? "No alerts match these filters. Try another search or clear the filters." : "No alerts yet. Signals from monitored devices will appear here."}</td></tr>}
              {alerts.map((alert) => <tr key={alert.alert_id} className="border-t border-slate-100 align-top hover:bg-slate-50">
                <td className="p-3"><SeverityBadge severity={alert.severity} /></td>
                <td className="max-w-md p-3 text-sm"><div className="line-clamp-2">{(alert.repeat_count || 1) > 1 && <span className="mr-1.5 rounded-full bg-orange-100 px-1.5 py-0.5 text-xs font-semibold text-orange-800" title={`Seen ${alert.repeat_count} times`}>×{alert.repeat_count}</span>}{alert.summary || <em className="text-slate-400">No summary</em>}</div>{Boolean(alert.categories?.length) && <div className="mt-1 flex flex-wrap gap-1">{alert.categories?.slice(0, 3).map((category) => <span key={category} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">{category.replaceAll("_", " ")}</span>)}</div>}</td>
                <td className="p-3 text-sm"><div className="font-medium">{alert.app_name || "—"}</div><div className="text-xs text-slate-500">{alert.device_id ? deviceNames.get(alert.device_id) || alert.device_id : "—"}{alert.profile_id ? ` · ${profileNames.get(alert.profile_id) || alert.profile_id}` : ""}</div></td>
                <td className="whitespace-nowrap p-3 text-sm">{alert.status.replaceAll("_", " ")}</td>
                <td className="whitespace-nowrap p-3 text-sm text-slate-500">{formatDateTime(alert.created_at)}{(alert.repeat_count || 1) > 1 && alert.last_seen_at && <div className="text-xs">last {formatDateTime(alert.last_seen_at)}</div>}</td>
                <td className="p-3 text-right"><Link to={`/alerts/${alert.alert_id}`} aria-label={`Review alert ${alert.alert_id}`} className="inline-flex min-h-11 items-center text-sm font-semibold text-brand-700 underline">Review</Link></td>
              </tr>)}
            </tbody>
          </table>
        </div>
        {feed.hasNextPage && <button disabled={feed.isFetching} onClick={() => void feed.fetchNextPage()} className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-4 text-sm font-semibold disabled:opacity-50">{feed.isFetchingNextPage ? "Loading older alerts…" : "Load older alerts"}</button>}
      </>}
    </div>
  );
}
