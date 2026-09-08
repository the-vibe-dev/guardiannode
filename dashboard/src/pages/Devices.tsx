import { useEffect, useMemo, useState } from "react";
import { Check, Copy, Download, Laptop, Pause, Play, Plus, Trash2 } from "lucide-react";
import { api, type Device, type PairStart, type Profile } from "../api";
import { formatDateTime } from "../utils/datetime";

const PAUSE_OPTIONS = [
  { seconds: 15 * 60, label: "15 minutes" },
  { seconds: 60 * 60, label: "1 hour" },
  { seconds: 4 * 60 * 60, label: "4 hours" },
  { seconds: 24 * 60 * 60, label: "24 hours" },
];

function statusColor(status: string) {
  if (status === "online") return "bg-emerald-50 text-emerald-800 ring-emerald-200";
  if (status === "paused") return "bg-amber-50 text-amber-800 ring-amber-200";
  if (status === "disabled" || status === "consent_withdrawn") return "bg-rose-50 text-rose-800 ring-rose-200";
  return "bg-slate-100 text-slate-700 ring-slate-200";
}

function StatusBadge({ device }: { device: Device }) {
  return (
    <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold capitalize ring-1 ring-inset ${statusColor(device.status)}`}>
      {device.status.replaceAll("_", " ")}
    </span>
  );
}

function ProfileSelect({ device, profiles, onChange }: { device: Device; profiles: Profile[]; onChange: (profileId: string) => void }) {
  return (
    <select
      aria-label={`Child profile for ${device.hostname}`}
      className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
      value={device.profile_id || ""}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">— unassigned —</option>
      {profiles.map((profile) => <option key={profile.profile_id} value={profile.profile_id}>{profile.display_name}</option>)}
    </select>
  );
}

export default function Devices() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [pairCode, setPairCode] = useState<PairStart | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pauseSeconds, setPauseSeconds] = useState(60 * 60);
  const [now, setNow] = useState(Date.now());

  function reload() {
    api.devices().then(setDevices).catch((reason: Error) => setError(reason.message));
  }

  useEffect(() => {
    reload();
    api.profiles().then(setProfiles).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!pairCode) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [pairCode]);

  const secondsRemaining = useMemo(() => pairCode
    ? Math.max(0, Math.ceil((new Date(pairCode.expires_at).getTime() - now) / 1000))
    : 0, [now, pairCode]);
  const countdown = `${Math.floor(secondsRemaining / 60)}:${String(secondsRemaining % 60).padStart(2, "0")}`;

  async function assignProfile(deviceId: string, profileId: string) {
    setError(null);
    try {
      await api.assignDeviceProfile(deviceId, profileId || null);
      reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not assign this profile");
    }
  }

  async function startPair() {
    setError(null);
    setNotice(null);
    try {
      const response = await api.startPair();
      setPairCode(response);
      setNow(Date.now());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start secure pairing");
    }
  }

  async function copy(value: string, label: string) {
    try {
      await navigator.clipboard.writeText(value);
      setNotice(`${label} copied.`);
    } catch {
      setError(`Could not copy ${label.toLowerCase()}; select it manually.`);
    }
  }

  async function pause(deviceId: string) {
    setError(null);
    try {
      await api.pauseDevice(deviceId, pauseSeconds);
      setNotice("Monitoring pause recorded.");
      reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not pause monitoring");
    }
  }

  async function resume(deviceId: string) {
    setError(null);
    try {
      await api.resumeDevice(deviceId);
      setNotice("Monitoring resumed.");
      reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not resume monitoring");
    }
  }

  async function revoke(deviceId: string, hostname: string) {
    if (!window.confirm(`Remove "${hostname}"? Its agent will stop sending events until it is paired again.`)) return;
    setError(null);
    try {
      await api.revokeDevice(deviceId);
      setNotice(`${hostname} removed.`);
      reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not remove this device");
    }
  }

  const actions = (device: Device) => (
    <div className="flex flex-wrap items-center gap-2">
      {device.status === "paused" ? (
        <button onClick={() => resume(device.device_id)} className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
          <Play aria-hidden="true" size={16} /> Resume
        </button>
      ) : device.status !== "disabled" && device.status !== "consent_withdrawn" ? (
        <button onClick={() => pause(device.device_id)} className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
          <Pause aria-hidden="true" size={16} /> Pause
        </button>
      ) : null}
      {device.status !== "disabled" && (
        <button onClick={() => revoke(device.device_id, device.hostname)} className="inline-flex min-h-11 items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-50">
          <Trash2 aria-hidden="true" size={16} /> Remove
        </button>
      )}
    </div>
  );

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="mb-1 text-sm font-medium text-[#275e3d]">Family coverage</p><h1 className="font-display text-2xl font-bold text-[#18313a] sm:text-3xl">Devices</h1><p className="mt-2 text-sm text-slate-600">Pair, assign, pause, or remove computers your family controls.</p></div>
        <button onClick={startPair} className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-[#275e3d] px-4 py-2 text-sm font-semibold text-white hover:bg-[#1c4a30]"><Plus aria-hidden="true" size={18} /> Add device</button>
      </header>

      {pairCode && (
        <section className="rounded-2xl border border-sky-200 bg-sky-50 p-5" aria-labelledby="pair-heading">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 id="pair-heading" className="font-display text-lg font-semibold text-[#18313a]">Pair a child device securely</h2><p className="mt-1 text-sm text-slate-700">Transfer the downloaded file privately and compare the CA check words on both PCs.</p></div><span className={`rounded-full px-3 py-1 text-sm font-semibold ${secondsRemaining ? "bg-white text-sky-900" : "bg-rose-100 text-rose-800"}`} aria-live="polite">{secondsRemaining ? `Expires in ${countdown}` : "Code expired"}</span></div>
          <ol className="mt-4 list-decimal space-y-1 pl-5 text-sm text-slate-700"><li>Download the trust bundle and move it to the child PC.</li><li>Select it in the child installer.</li><li>Enter the exact server URL and single-use code below.</li><li>Delete the bundle after pairing succeeds.</li></ol>
          <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] lg:items-end">
            <div><span className="block text-xs font-semibold uppercase tracking-wide text-slate-600">Pairing code</span><div className="mt-1 flex items-center gap-2"><code className="rounded-lg bg-white px-3 py-2 font-mono text-2xl font-bold tracking-[0.2em] text-[#18313a]">{pairCode.code}</code><button onClick={() => copy(pairCode.code, "Pairing code")} className="grid min-h-11 min-w-11 place-items-center rounded-lg border border-sky-200 bg-white text-sky-900" aria-label="Copy pairing code"><Copy aria-hidden="true" size={18} /></button></div></div>
            <div className="min-w-0"><span className="block text-xs font-semibold uppercase tracking-wide text-slate-600">Exact server URL</span><div className="mt-1 flex items-center gap-2"><code className="min-w-0 flex-1 break-all rounded-lg bg-white px-3 py-3 text-xs text-[#18313a]">{pairCode.server_url}</code><button onClick={() => copy(pairCode.server_url, "Server URL")} className="grid min-h-11 min-w-11 place-items-center rounded-lg border border-sky-200 bg-white text-sky-900" aria-label="Copy server URL"><Copy aria-hidden="true" size={18} /></button></div></div>
            {secondsRemaining ? <a href={pairCode.bundle_url} download className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-[#0d3b4a] px-4 py-2 text-sm font-semibold text-white hover:bg-[#164f60]"><Download aria-hidden="true" size={18} /> Download .gnpair bundle</a> : <button onClick={startPair} className="min-h-11 rounded-lg bg-[#0d3b4a] px-4 py-2 text-sm font-semibold text-white">Generate new code</button>}
          </div>
          <p className="mt-4 text-xs text-slate-600"><strong>CA check words:</strong> {pairCode.ca_words.join(" · ")} · Full fingerprint available in the bundle. Expires {formatDateTime(pairCode.expires_at)}.</p>
        </section>
      )}

      {error && <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{error}</div>}
      {notice && <div role="status" className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800"><Check aria-hidden="true" size={17} /> {notice}</div>}

      <section className="rounded-2xl border border-slate-200 bg-white shadow-sm" aria-labelledby="paired-devices-heading">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4"><div><h2 id="paired-devices-heading" className="font-display font-semibold text-[#18313a]">Paired devices</h2><p className="text-xs text-slate-500">Last status reported by each endpoint.</p></div><label className="text-xs font-semibold text-slate-600">Pause duration<select value={pauseSeconds} onChange={(event) => setPauseSeconds(Number(event.target.value))} className="ml-2 min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm font-normal text-slate-800">{PAUSE_OPTIONS.map((option) => <option key={option.seconds} value={option.seconds}>{option.label}</option>)}</select></label></div>

        {devices.length === 0 ? <div className="grid place-items-center px-5 py-12 text-center"><Laptop aria-hidden="true" className="text-slate-300" size={38} /><p className="mt-3 font-semibold text-slate-700">No devices paired yet</p><p className="mt-1 text-sm text-slate-500">Complete privacy consent, then choose Add device.</p></div> : (
          <>
            <div className="divide-y divide-slate-200 md:hidden">{devices.map((device) => <article key={device.device_id} className="space-y-4 p-5"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><h3 className="truncate font-semibold text-[#18313a]">{device.hostname}</h3><p className="text-xs text-slate-500">Last seen {formatDateTime(device.last_seen)}</p></div><StatusBadge device={device} /></div><ProfileSelect device={device} profiles={profiles} onChange={(profileId) => assignProfile(device.device_id, profileId)} />{device.status === "paused" && device.paused_until && <p className="text-xs text-amber-800">Paused until {formatDateTime(device.paused_until)}</p>}{actions(device)}</article>)}</div>
            <div className="hidden overflow-x-auto md:block"><table className="w-full"><caption className="sr-only">Paired GuardianNode child devices</caption><thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500"><tr><th scope="col" className="p-4">Computer</th><th scope="col" className="p-4">Child</th><th scope="col" className="p-4">Status</th><th scope="col" className="p-4">Last seen</th><th scope="col" className="p-4">Actions</th></tr></thead><tbody className="divide-y divide-slate-200">{devices.map((device) => <tr key={device.device_id}><th scope="row" className="p-4 text-left font-semibold text-[#18313a]">{device.hostname}</th><td className="p-4"><ProfileSelect device={device} profiles={profiles} onChange={(profileId) => assignProfile(device.device_id, profileId)} /></td><td className="p-4"><StatusBadge device={device} />{device.status === "paused" && device.paused_until && <span className="mt-1 block text-xs text-slate-500">until {formatDateTime(device.paused_until)}</span>}</td><td className="p-4 text-sm text-slate-600">{formatDateTime(device.last_seen)}</td><td className="p-4">{actions(device)}</td></tr>)}</tbody></table></div>
          </>
        )}
      </section>
    </div>
  );
}
