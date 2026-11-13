import { useEffect, useState } from "react";
import { api } from "../api";
import { formatDateTime } from "../utils/datetime";

type Profile = {
  profile_id: string;
  display_name: string;
  age_group: string;
  created_at: string;
  notes: string | null;
  custom_watch_phrases: string[];
  alert_policy: any;
};

export default function Profiles() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [meta, setMeta] = useState<any>(null);
  const [name, setName] = useState("");
  const [age, setAge] = useState("10_13");
  const [initialPhrases, setInitialPhrases] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  function reload() {
    api.profiles().then(setProfiles).catch((e) => setErr(e.message));
  }
  useEffect(() => {
    reload();
    api.policyMeta().then(setMeta).catch(() => {});
  }, []);

  async function create() {
    setErr(null);
    if (!name.trim()) return;
    setCreating(true);
    const phrases = initialPhrases
      .split(/[,\n]/)
      .map((s) => s.trim())
      .filter(Boolean);
    try {
      await api.createProfile(name.trim(), age, undefined, phrases);
      setName("");
      setInitialPhrases("");
      reload();
    } catch (e: any) {
      setErr(e.message || String(e));
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Child profiles</h1>

      {err && (
        <div role="alert" className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm">{err}</div>
      )}

      <div className="bg-white shadow rounded p-4 space-y-3">
        <div className="flex gap-2 items-end flex-wrap">
          <label className="flex-1 min-w-[180px]">
            <span className="text-xs text-gray-500">Display name</span>
            <input
              className="block w-full border rounded px-2 py-1 mt-1"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Alex"
            />
          </label>
          <label>
            <span className="text-xs text-gray-500">Age group</span>
            <select
              className="block border rounded px-2 py-1 mt-1"
              value={age}
              onChange={(e) => setAge(e.target.value)}
            >
              <option value="under_10">Under 10</option>
              <option value="10_13">10–13</option>
              <option value="14_17">14–17</option>
            </select>
          </label>
          <button
            onClick={create}
            disabled={creating || !name.trim()}
            className="bg-brand-500 hover:bg-brand-700 text-white px-3 py-2 rounded"
          >
            {creating ? "Adding…" : "Add"}
          </button>
        </div>
        <label className="block">
          <span className="text-xs text-gray-500">
            Watch phrases (optional) — child's real name, address, school, nicknames.
            One per line, or comma-separated. Any match triggers a high-severity alert.
          </span>
          <textarea
            className="block w-full border rounded px-2 py-1 mt-1 text-sm font-mono"
            rows={3}
            value={initialPhrases}
            onChange={(e) => setInitialPhrases(e.target.value)}
            placeholder={"Alex Example\n123 Example Street\nExample Middle School"}
          />
        </label>
      </div>

      <div className="space-y-3">
        {profiles.length === 0 && (
          <div className="bg-white shadow rounded p-6 text-center text-gray-500">
            No profiles yet.
          </div>
        )}
        {profiles.map((p) => (
          <ProfileCard key={p.profile_id} profile={p} meta={meta} onSaved={reload} />
        ))}
      </div>
    </div>
  );
}

function ProfileCard({ profile, meta, onSaved }: { profile: Profile; meta: any; onSaved: () => void }) {
  const [phrases, setPhrases] = useState<string[]>(profile.custom_watch_phrases || []);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setPhrases(profile.custom_watch_phrases || []);
  }, [profile.profile_id]);

  function addPhrase() {
    const v = draft.trim();
    if (!v) return;
    if (phrases.some((p) => p.toLowerCase() === v.toLowerCase())) {
      setDraft("");
      return;
    }
    setPhrases([...phrases, v]);
    setDraft("");
  }

  function removePhrase(i: number) {
    setPhrases(phrases.filter((_, j) => j !== i));
  }

  async function save() {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const saved = await api.updateProfile(profile.profile_id, { custom_watch_phrases: phrases });
      setPhrases(saved.custom_watch_phrases || []);
      setMsg("Saved");
      setTimeout(() => setMsg(null), 2000);
      onSaved();
    } catch (e: any) {
      setErr(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  const original = profile.custom_watch_phrases || [];
  const dirty =
    phrases.length !== original.length ||
    phrases.some((p, i) => p !== original[i]);

  return (
    <div className="bg-white shadow rounded p-4">
      <div className="flex items-baseline justify-between flex-wrap gap-2">
        <div>
          <span className="text-lg font-semibold">{profile.display_name}</span>
          <span className="ml-2 text-xs text-gray-500">age {profile.age_group.replace("_", "–")}</span>
        </div>
        <span className="text-xs text-gray-400">
          created {formatDateTime(profile.created_at)}
        </span>
      </div>

      <div className="mt-3">
        <div className="text-xs text-gray-500 mb-1">
          Watch phrases — child's name, address, school, anything to flag if it appears on screen.
        </div>
        <div className="flex flex-wrap gap-1.5 mb-2 min-h-[28px]">
          {phrases.length === 0 && (
            <span className="text-xs italic text-gray-400">No watch phrases yet.</span>
          )}
          {phrases.map((p, i) => (
            <span
              key={`${p}-${i}`}
              className="inline-flex items-center gap-1 bg-amber-50 border border-amber-200 text-amber-900 text-xs rounded px-2 py-0.5"
            >
              {p}
              <button
                onClick={() => removePhrase(i)}
                className="text-amber-700 hover:text-red-700 leading-none"
                aria-label={`Remove ${p}`}
                title="Remove"
              >
                ×
              </button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            aria-label={`Add a watch phrase for ${profile.display_name}`}
            className="flex-1 border rounded px-2 py-1 text-sm"
            placeholder="Add a phrase and press Enter"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addPhrase();
              }
            }}
          />
          <button
            onClick={addPhrase}
            className="bg-gray-100 hover:bg-gray-200 text-gray-800 px-3 py-1 rounded text-sm"
          >
            Add
          </button>
          <button
            onClick={save}
            disabled={busy || !dirty}
            className="bg-brand-500 hover:bg-brand-700 disabled:bg-brand-500/40 text-white px-3 py-1 rounded text-sm"
          >
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
        {msg && <div className="text-xs text-green-700 mt-1">{msg}</div>}
        {err && <div role="alert" className="text-xs text-red-700 mt-1">{err}</div>}
      </div>

      {meta && <PolicyEditor profile={profile} meta={meta} onSaved={onSaved} />}
    </div>
  );
}

const SEV_LABEL: Record<string, string> = {
  low: "Low+", medium: "Medium+", high: "High+", critical: "Critical only",
};
const MODE_LABEL: Record<string, string> = {
  alert: "Alert me", monitor: "Monitor quietly", allow: "Ignore this signal",
};
const CAPTURE_LABEL: Record<string, string> = {
  tight: "Frequent screenshots", balanced: "Balanced screenshots", leeway: "Fewer screenshots",
};

function PolicyEditor({ profile, meta, onSaved }: { profile: Profile; meta: any; onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const [policy, setPolicy] = useState<any>(() => JSON.parse(JSON.stringify(profile.alert_policy || {})));
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { setPolicy(JSON.parse(JSON.stringify(profile.alert_policy || {}))); }, [profile.profile_id]);

  function setCat(key: string, field: string, value: any) {
    const cats = { ...(policy.categories || {}) };
    cats[key] = { ...(cats[key] || { mode: "alert" }), [field]: value };
    setPolicy({ ...policy, categories: cats });
  }

  async function save(reset = false) {
    setBusy(true); setMsg(null); setError(null);
    try {
      const saved = await api.updateProfile(profile.profile_id,
        reset ? { reset_policy_to_age_default: true } : { alert_policy: policy });
      setPolicy(JSON.parse(JSON.stringify(saved.alert_policy || {})));
      setMsg(reset ? "Reset to age defaults" : "Screenshot & alert settings saved");
      setTimeout(() => setMsg(null), 2500);
      onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save screenshot & alert settings");
    } finally { setBusy(false); }
  }

  const cats = policy.categories || {};
  return (
    <div className="mt-4 border-t pt-3">
      <button aria-expanded={open} onClick={() => setOpen(!open)} className="text-sm font-medium text-brand-700">
        {open ? "▾" : "▸"} Screenshot & alert settings
      </button>
      {open && (
        <div className="mt-3 space-y-3">
          <p className="text-xs text-gray-500">
            Choose screenshot frequency and which review signals need an alert. These settings
            control monitoring and notifications; they do not restrict device use. Self-harm,
            grooming, threats, and your watch phrases remain enabled for review.
            Detection can still miss or misinterpret content.
          </p>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm">
              <span className="text-xs text-gray-500">Only alert me at or above</span>
              <select className="mt-1 w-full border rounded px-2 py-1"
                value={policy.min_severity || "medium"}
                onChange={(e) => setPolicy({ ...policy, min_severity: e.target.value })}>
                {(meta.severities || []).map((s: string) => <option key={s} value={s}>{SEV_LABEL[s] || s}</option>)}
              </select>
            </label>
            <label className="text-sm">
              <span className="text-xs text-gray-500">Screenshot frequency</span>
              <select className="mt-1 w-full border rounded px-2 py-1"
                value={(policy.capture && policy.capture.level) || "balanced"}
                onChange={(e) => setPolicy({ ...policy, capture: { ...(policy.capture || {}), level: e.target.value } })}>
                {(meta.capture_levels || []).map((l: string) => <option key={l} value={l}>{CAPTURE_LABEL[l] || l}</option>)}
              </select>
            </label>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-gray-400 text-left">
                <tr><th className="py-1">Behavior to watch</th><th className="py-1">Alert handling</th><th className="py-1">Only when</th></tr>
              </thead>
              <tbody>
                {(meta.tunable_categories || []).map((c: any) => {
                  const cur = cats[c.key] || { mode: "alert" };
                  return (
                    <tr key={c.key} className="border-t">
                      <td className="py-1.5 pr-2">{c.label}</td>
                      <td className="py-1.5 pr-2">
                        <select aria-label={`${c.label}: what to do`} className="border rounded px-1.5 py-0.5"
                          value={cur.mode || "alert"} onChange={(e) => setCat(c.key, "mode", e.target.value)}>
                          {(meta.modes || []).map((m: string) => <option key={m} value={m}>{MODE_LABEL[m] || m}</option>)}
                        </select>
                      </td>
                      <td className="py-1.5">
                        <select aria-label={`${c.label}: minimum severity`} className="border rounded px-1.5 py-0.5 disabled:opacity-40"
                          disabled={cur.mode === "allow"}
                          value={cur.min_severity || policy.min_severity || "medium"}
                          onChange={(e) => setCat(c.key, "min_severity", e.target.value)}>
                          {(meta.severities || []).map((s: string) => <option key={s} value={s}>{SEV_LABEL[s] || s}</option>)}
                        </select>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="text-xs text-gray-500">
            Protected review signals: {(meta.protected_categories || []).map((c: string) => c.replace(/_/g, " ")).join(", ")}
          </div>

          <div className="flex gap-2 items-center">
            <button onClick={() => save(false)} disabled={busy}
              className="bg-brand-500 hover:bg-brand-700 disabled:opacity-50 text-white px-3 py-1.5 rounded text-sm">
              {busy ? "Saving…" : "Save screenshot settings"}
            </button>
            <button onClick={() => save(true)} disabled={busy}
              className="text-sm text-gray-500 underline">
              Reset to age defaults
            </button>
            {msg && <span className="text-xs text-green-700">{msg}</span>}
          </div>
          {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        </div>
      )}
    </div>
  );
}
