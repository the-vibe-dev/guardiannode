import { useEffect, useState } from "react";
import { api } from "../api";
import { formatDateTime } from "../utils/datetime";

export default function Audit() {
  const [rows, setRows] = useState<any[]>([]);
  const [action, setAction] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const params: Record<string, string> = { limit: "200" };
    if (action.trim()) params.action = action.trim();
    api.audit(params).then(setRows).catch((e) => setErr(e.message));
  }, [action]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-bold">Audit</h1>
        <label className="text-sm">
          <span className="text-xs text-gray-500">Action filter</span>
          <input
            className="block border rounded px-2 py-1 mt-1"
            value={action}
            onChange={(e) => setAction(e.target.value)}
            placeholder="alert.view"
          />
        </label>
      </div>
      {err && <div className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm">{err}</div>}
      <div className="overflow-x-auto bg-white shadow rounded">
        <table className="min-w-[760px] w-full">
          <thead className="bg-gray-100 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="p-3">Time</th>
              <th className="p-3">Actor</th>
              <th className="p-3">Action</th>
              <th className="p-3">Target</th>
              <th className="p-3">Details</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={5} className="p-6 text-center text-gray-500">No audit entries found.</td></tr>
            )}
            {rows.map((row) => (
              <tr key={row.id} className="border-t align-top">
                <td className="p-3 text-sm text-gray-500">{formatDateTime(row.created_at)}</td>
                <td className="p-3 text-sm">{row.actor}</td>
                <td className="p-3 text-sm font-medium">{row.action}</td>
                <td className="p-3 text-sm">{row.target || "-"}</td>
                <td className="p-3 text-xs font-mono max-w-md break-words">
                  {JSON.stringify(row.details || {})}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
