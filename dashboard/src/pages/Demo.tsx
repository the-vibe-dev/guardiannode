import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

export default function Demo() {
  const [status, setStatus] = useState<any>(null);
  const [scenarios, setScenarios] = useState<any[]>([]);
  const [selected, setSelected] = useState("");
  const [triggered, setTriggered] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.demoStatus(), api.demoScenarios()])
      .then(([nextStatus, nextScenarios]) => {
        setStatus(nextStatus);
        setScenarios(nextScenarios);
        setSelected(nextScenarios[0]?.id || "");
      })
      .catch((error) => setMessage(error.message));
  }, []);

  async function trigger() {
    if (!selected) return;
    setBusy("trigger");
    setMessage(null);
    try {
      setTriggered(await api.triggerDemoScenario(selected));
    } catch (error: any) {
      setMessage(error.message || "The synthetic scenario could not be created.");
    } finally {
      setBusy(null);
    }
  }

  async function reset() {
    if (!window.confirm("Reset all synthetic demo incidents and their local Guardian Reviews? Real incidents are never selected.")) return;
    setBusy("reset");
    setMessage(null);
    try {
      const result = await api.resetDemo();
      setTriggered(null);
      setMessage(`Synthetic demo reset complete. ${result.alerts_removed} alert(s) removed.`);
    } catch (error: any) {
      setMessage(error.message || "The demo could not be reset.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-brand-700">Under-five-minute judge path</p>
        <h1 className="text-2xl font-bold">Guardian Review synthetic demo</h1>
        <p className="mt-1 text-sm text-gray-600">Every scenario is manufactured for demonstration. No real child or family data is included.</p>
      </div>

      {message && <div role="status" className="rounded border bg-white p-3 text-sm">{message}</div>}
      {!status && !message && <p role="status">Checking demo health…</p>}

      {status && (
        <div className="grid gap-3 sm:grid-cols-2">
          <StatusCard label="Demo device" value={status.device.status === "demo_ready" ? "Ready" : status.device.status} ready />
          <StatusCard label="Guardian Review" value={status.guardian_review.ready ? `${status.guardian_review.model} ready` : "Setup required"} ready={status.guardian_review.ready} />
        </div>
      )}

      <ol className="grid gap-2 rounded border bg-white p-4 text-sm sm:grid-cols-4" aria-label="Demo steps">
        <Step number="1" text="Choose and trigger" />
        <Step number="2" text="Review local reasoning" />
        <Step number="3" text="Preview and approve" />
        <Step number="4" text="Guide and give feedback" />
      </ol>

      <section className="rounded border bg-white p-4" aria-labelledby="scenario-heading">
        <h2 id="scenario-heading" className="font-semibold">1. Choose a synthetic scenario</h2>
        {scenarios.length ? (
          <div className="mt-3 space-y-3">
            {scenarios.map((scenario) => (
              <label key={scenario.id} className={`block cursor-pointer rounded border p-3 ${selected === scenario.id ? "border-brand-500 bg-brand-50" : ""}`}>
                <span className="flex items-start gap-3">
                  <input type="radio" name="scenario" value={scenario.id} checked={selected === scenario.id} onChange={() => setSelected(scenario.id)} className="mt-1" />
                  <span><strong>{scenario.title}</strong><span className="block text-sm text-gray-600">{scenario.description}</span><span className="mt-1 block text-xs uppercase text-gray-500">Expected local result: {scenario.expected_local_severity}</span></span>
                </span>
              </label>
            ))}
            <button type="button" onClick={trigger} disabled={busy !== null} className="rounded bg-brand-500 px-4 py-2 text-sm text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-700 focus-visible:ring-offset-2 disabled:opacity-50">
              {busy === "trigger" ? "Running local detection…" : "Trigger synthetic incident"}
            </button>
          </div>
        ) : <p className="mt-2 text-sm text-gray-600">Enable <code>GUARDIANNODE_DEMO_MODE_ENABLED=true</code> to load synthetic scenarios.</p>}
      </section>

      {triggered && (
        <section className="rounded border border-green-300 bg-green-50 p-4" aria-labelledby="created-heading">
          <h2 id="created-heading" className="font-semibold text-green-950">2. Synthetic incident created</h2>
          <p className="mt-1 text-sm text-green-950">Local detection: <strong className="capitalize">{triggered.local_detection.severity}</strong>{triggered.local_detection.categories.length ? ` · ${triggered.local_detection.categories.join(", ")}` : " · no rule matched"}.</p>
          <Link to={triggered.alert_url} className="mt-3 inline-block rounded bg-brand-700 px-4 py-2 text-sm text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-700 focus-visible:ring-offset-2">Open incident and continue →</Link>
        </section>
      )}

      <section className="rounded border bg-white p-4">
        <h2 className="font-semibold">Reset for the next judge</h2>
        <p className="mt-1 text-sm text-gray-600">Reset removes only records with GuardianNode's namespaced synthetic demo IDs. Audit metadata remains.</p>
        <button type="button" onClick={reset} disabled={busy !== null || !status?.enabled} className="mt-3 rounded border border-red-300 px-3 py-2 text-sm text-red-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-600 disabled:opacity-50">{busy === "reset" ? "Resetting…" : "Reset synthetic demo"}</button>
      </section>
    </div>
  );
}

function StatusCard({ label, value, ready }: { label: string; value: string; ready: boolean }) {
  return <div className="rounded border bg-white p-3"><div className="text-xs uppercase text-gray-500">{label}</div><div className={`font-semibold ${ready ? "text-green-700" : "text-amber-700"}`}>{value}</div></div>;
}

function Step({ number, text }: { number: string; text: string }) {
  return <li className="flex items-center gap-2"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-700 text-xs text-white">{number}</span>{text}</li>;
}
