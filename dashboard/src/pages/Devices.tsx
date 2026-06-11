import { useEffect, useState } from "react";
import { api } from "../api";
import { formatDateTime } from "../utils/datetime";

export default function Devices() {
  const [devices, setDevices] = useState<any[]>([]);
  const [profiles, setProfiles] = useState<any[]>([]);
  const [pairCode, setPairCode] = useState<{ code: string; expires_at: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    api.devices().then(setDevices).catch((e) => setError(e.message));
  }

  useEffect(() => {
    reload();
    api.profiles().then(setProfiles).catch(() => {});
  }, []);

  async function assignProfile(device_id: string, profile_id: string) {
    setError(null);
    try {
      await api.assignDeviceProfile(device_id, profile_id || null);
      reload();
    } catch (e: any) { setError(e.message); }
  }

  async function startPair() {
    setError(null);
    try {
      const r = await api.startPair();
      setPairCode(r);
    } catch (e: any) { setError(e.message); }
  }

  async function pause(id: string) {
    await api.pauseDevice(id, 60 * 60); reload();
  }
  async function resume(id: string) {
    await api.resumeDevice(id); reload();
  }
  async function revoke(id: string, hostname: string) {
    if (!window.confirm(`Remove "${hostname}"? Its agent will stop being able to send events until it is paired again.`)) return;
    try {
      await api.revokeDevice(id);
      reload();
    } catch (e: any) { setError(e.message); }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Devices</h1>
        <button onClick={startPair} className="bg-brand-500 hover:bg-brand-700 text-white px-4 py-2 rounded">
          Add device
        </button>
      </div>

      {pairCode && (
        <div className="bg-yellow-50 border border-yellow-200 rounded p-4">
          <div className="text-sm">Type this code into the GuardianNode installer on the child's PC:</div>
          <div className="text-4xl font-mono font-bold tracking-widest text-center my-3">{pairCode.code}</div>
          <div className="text-xs text-gray-600 text-center">Expires at {formatDateTime(pairCode.expires_at)}</div>
        </div>
      )}

      {error && <div className="text-red-700">{error}</div>}

      <div className="overflow-x-auto bg-white shadow rounded">
      <table className="min-w-[680px] w-full">
        <thead className="bg-gray-100 text-left text-xs uppercase text-gray-500">
          <tr>
            <th className="p-3">Hostname</th>
            <th className="p-3">Child</th>
            <th className="p-3">Status</th>
            <th className="p-3">Last seen</th>
            <th className="p-3"></th>
          </tr>
        </thead>
        <tbody>
          {devices.length === 0 && (
            <tr><td colSpan={5} className="p-6 text-center text-gray-500">No devices yet. Click "Add device" to start.</td></tr>
          )}
          {devices.map((d) => (
            <tr key={d.device_id} className="border-t">
              <td className="p-3 font-medium">{d.hostname}</td>
              <td className="p-3">
                <select
                  className="border rounded px-2 py-1 text-sm"
                  value={d.profile_id || ""}
                  onChange={(e) => assignProfile(d.device_id, e.target.value)}
                >
                  <option value="">— unassigned —</option>
                  {profiles.map((p) => (
                    <option key={p.profile_id} value={p.profile_id}>{p.display_name}</option>
                  ))}
                </select>
              </td>
              <td className="p-3">
                <span className={
                  d.status === "online" ? "text-green-700" :
                  d.status === "paused" ? "text-yellow-700" :
                  "text-gray-500"
                }>{d.status}</span>
              </td>
              <td className="p-3 text-sm text-gray-500">{formatDateTime(d.last_seen)}</td>
              <td className="p-3 text-right whitespace-nowrap space-x-3">
                {d.status === "paused" ?
                  <button onClick={() => resume(d.device_id)} className="text-sm underline">Resume</button> :
                  d.status !== "disabled" &&
                  <button onClick={() => pause(d.device_id)} className="text-sm underline">Pause 1h</button>}
                {d.status !== "disabled" &&
                  <button onClick={() => revoke(d.device_id, d.hostname)} className="text-sm underline text-red-700">Remove</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
}
