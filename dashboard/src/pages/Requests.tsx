import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Clock3, MessageCircleQuestion, X } from "lucide-react";
import { api, type ChildRequest } from "../api";
import { formatDateTime } from "../utils/datetime";

export default function Requests() {
  const queryClient = useQueryClient();
  const requests = useQuery({ queryKey: ["child-requests"], queryFn: () => api.childRequests({ limit: "100" }) });
  const review = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "approved" | "denied" | "dismissed" }) => api.reviewChildRequest(id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["child-requests"] }),
  });

  if (requests.isPending) return <div className="page-status" role="status">Loading requests…</div>;
  if (requests.error) return <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">{(requests.error as Error).message}</div>;
  const rows = requests.data!.items;
  return (
    <div className="space-y-6">
      <header><p className="mb-1 text-sm font-medium text-[#275e3d]">Family conversation</p><h1 className="font-display text-2xl font-bold text-[#18313a] sm:text-3xl">Requests</h1><p className="mt-2 max-w-2xl text-sm text-slate-600">Children can ask for more time or an exception. A parent always makes the decision.</p></header>
      <section className="rounded-xl border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4"><h2 className="font-display font-semibold">All requests</h2><span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800">{requests.data!.open_count} open</span></div>
        {rows.length ? <div className="divide-y divide-slate-100">{rows.map((row) => <RequestRow key={row.request_id} row={row} busy={review.isPending} onReview={(status) => review.mutate({ id: row.request_id, status })} />)}</div> : <div className="grid place-items-center px-5 py-16 text-center"><MessageCircleQuestion aria-hidden="true" className="text-slate-400" size={34} /><h2 className="mt-3 font-display font-semibold">No requests yet</h2><p className="mt-1 text-sm text-slate-500">New requests from paired devices will appear here.</p></div>}
      </section>
      {review.error && <p role="alert" className="text-sm text-red-700">{(review.error as Error).message}</p>}
    </div>
  );
}

function RequestRow({ row, busy, onReview }: { row: ChildRequest; busy: boolean; onReview: (status: "approved" | "denied" | "dismissed") => void }) {
  return <article className="grid gap-4 p-5 lg:grid-cols-[1fr_auto] lg:items-center"><div><div className="flex flex-wrap items-center gap-2"><span className="font-semibold capitalize text-[#18313a]">{row.request_type.replaceAll("_", " ")}</span><span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold capitalize ${row.status === "open" ? "bg-amber-50 text-amber-800" : "bg-slate-100 text-slate-600"}`}>{row.status}</span></div>{row.target && <p className="mt-2 text-sm font-medium text-slate-700">For: {row.target}</p>}{row.reason && <p className="mt-1 text-sm text-slate-600">“{row.reason}”</p>}<p className="mt-2 flex items-center gap-1 text-xs text-slate-500"><Clock3 aria-hidden="true" size={13} />{formatDateTime(row.created_at)}</p></div>{row.status === "open" && <div className="flex flex-wrap gap-2"><button disabled={busy} onClick={() => onReview("approved")} className="inline-flex min-h-11 items-center gap-1.5 rounded-lg bg-[#275e3d] px-4 py-2 text-sm font-semibold text-white hover:bg-[#1c4a30] disabled:opacity-50"><Check aria-hidden="true" size={16} />Approve</button><button disabled={busy} onClick={() => onReview("denied")} className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"><X aria-hidden="true" size={16} />Deny</button></div>}</article>;
}
