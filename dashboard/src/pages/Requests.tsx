import { useState } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Clock3, MessageCircleQuestion, RefreshCw, X } from "lucide-react";
import { api, type ChildRequest } from "../api";
import { formatDateTime } from "../utils/datetime";

export default function Requests() {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("open");
  const [notice, setNotice] = useState("");
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: api.profiles });
  const devices = useQuery({ queryKey: ["devices"], queryFn: api.devices });
  const requests = useInfiniteQuery({
    queryKey: ["child-requests", "list", status],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => api.childRequests({ limit: "50", ...(status ? { status } : {}), ...(pageParam ? { cursor: pageParam } : {}) }),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });
  const review = useMutation({
    mutationFn: ({ id, decision, note }: { id: string; decision: "approved" | "denied" | "dismissed"; note: string }) => api.reviewChildRequest(id, decision, note.trim() || undefined),
    onSuccess: () => {
      setNotice("Your response was recorded. Any device or app change must be applied separately.");
      void queryClient.invalidateQueries({ queryKey: ["child-requests"] });
    },
    // Refresh after conflicts too: another parent may already have handled it.
    onError: () => { void queryClient.invalidateQueries({ queryKey: ["child-requests"] }); },
  });
  const rows = [...new Map((requests.data?.pages.flatMap((page) => page.items) ?? []).map((row) => [row.request_id, row])).values()];
  const profileName = (id: string | null) => profiles.data?.find((profile) => profile.profile_id === id)?.display_name || id;
  const deviceName = (id: string | null) => devices.data?.find((device) => device.device_id === id)?.hostname || id;

  return (
    <div className="space-y-6">
      <header><p className="mb-1 text-sm font-medium text-[#275e3d]">Family conversation</p><h1 className="font-display text-2xl font-bold text-[#18313a] sm:text-3xl">Requests</h1><p className="mt-2 max-w-2xl text-sm text-slate-600">Review a child’s request and send a clear response. Approval records your decision; it does not automatically add screen time or unblock an app or site.</p></header>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="text-sm"><span className="font-medium text-slate-700">Request status</span><select className="ml-3 min-h-11 rounded-lg border border-slate-300 bg-white px-3" value={status} onChange={(event) => setStatus(event.target.value)}>{["open", "", "approved", "denied", "dismissed", "expired"].map((value) => <option key={value || "all"} value={value}>{value ? value[0].toUpperCase() + value.slice(1) : "All requests"}</option>)}</select></label>
        <button onClick={() => void requests.refetch()} disabled={requests.isFetching} className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm font-semibold disabled:opacity-50"><RefreshCw aria-hidden="true" size={16} />Refresh requests</button>
      </div>
      {notice && <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">{notice}</p>}
      {requests.isPending && <div className="page-status" role="status">Loading requests…</div>}
      {requests.isError && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">Could not load requests: {requests.error.message}. <button className="underline" onClick={() => void (requests.isFetchNextPageError ? requests.fetchNextPage() : requests.refetch())}>Retry requests</button></div>}
      {requests.data && <section className="rounded-xl border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4"><h2 className="font-display font-semibold">{status ? `${status[0].toUpperCase() + status.slice(1)} requests` : "All requests"}</h2><span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800">{requests.data.pages[0].open_count} open across family</span></div>
        {rows.length ? <div className="divide-y divide-slate-100">{rows.map((row) => <RequestRow key={row.request_id} row={row} familyLabel={[profileName(row.profile_id), deviceName(row.device_id)].filter(Boolean).join(" · ")} busy={review.isPending} onReview={(decision, note) => review.mutate({ id: row.request_id, decision, note })} />)}</div> : <div className="grid place-items-center px-5 py-16 text-center"><MessageCircleQuestion aria-hidden="true" className="text-slate-400" size={34} /><h2 className="mt-3 font-display font-semibold">No {status ? `${status} ` : ""}requests</h2><p className="mt-1 text-sm text-slate-500">Requests from paired devices appear here. Try another status to see past decisions.</p></div>}
        <div className="border-t border-slate-100 p-4 text-xs text-slate-500">{rows.length} loaded{requests.hasNextPage ? " · more available" : " · end of results"}{requests.hasNextPage && <button onClick={() => void requests.fetchNextPage()} disabled={requests.isFetching} className="mt-3 min-h-11 w-full rounded-lg border border-slate-300 text-sm font-semibold text-slate-700 disabled:opacity-50">{requests.isFetchingNextPage ? "Loading older requests…" : "Load older requests"}</button>}</div>
      </section>}
      {review.error && <p role="alert" className="text-sm text-red-700">{review.error.message}</p>}
    </div>
  );
}

function RequestRow({ row, familyLabel, busy, onReview }: { row: ChildRequest; familyLabel: string; busy: boolean; onReview: (status: "approved" | "denied" | "dismissed", note: string) => void }) {
  const [note, setNote] = useState("");
  return <article className="grid gap-4 p-5 lg:grid-cols-[1fr_22rem]">
    <div><div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold capitalize text-[#18313a]">{row.request_type.replaceAll("_", " ")}</h3><span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold capitalize ${row.status === "open" ? "bg-amber-50 text-amber-800" : "bg-slate-100 text-slate-600"}`}>{row.status}</span></div><p className="mt-1 text-xs text-slate-500">{familyLabel || "Unassigned device"}</p>{row.target && <p className="mt-2 break-words text-sm font-medium text-slate-700">For: {row.target}</p>}{row.reason && <p className="mt-1 whitespace-pre-wrap break-words text-sm text-slate-600">“{row.reason}”</p>}<p className="mt-2 flex items-center gap-1 text-xs text-slate-500"><Clock3 aria-hidden="true" size={13} />{formatDateTime(row.created_at)}</p>{row.status === "open" && row.expires_at && <p className="mt-1 text-xs text-slate-500">Expires {formatDateTime(row.expires_at)}</p>}{row.response_note && <p className="mt-3 whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-3 text-sm text-slate-700"><strong>Parent response:</strong> {row.response_note}</p>}</div>
    {row.status === "open" && <div className="space-y-3"><label className="block text-sm"><span className="font-medium text-slate-700">Response to {familyLabel || "this request"} (optional)</span><textarea maxLength={4096} value={note} onChange={(event) => setNote(event.target.value)} disabled={busy} rows={2} className="mt-1 w-full rounded-lg border border-slate-300 p-2" placeholder="Explain your decision or suggest another time." /></label><div className="flex flex-wrap gap-2"><button disabled={busy} onClick={() => onReview("approved", note)} className="inline-flex min-h-11 items-center gap-1.5 rounded-lg bg-[#275e3d] px-4 py-2 text-sm font-semibold text-white hover:bg-[#1c4a30] disabled:opacity-50"><Check aria-hidden="true" size={16} />Approve</button><button disabled={busy} onClick={() => onReview("denied", note)} className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"><X aria-hidden="true" size={16} />Deny</button><button disabled={busy} onClick={() => onReview("dismissed", note)} className="min-h-11 rounded-lg px-3 text-sm font-semibold text-slate-600 underline disabled:opacity-50">Dismiss</button></div></div>}
  </article>;
}
