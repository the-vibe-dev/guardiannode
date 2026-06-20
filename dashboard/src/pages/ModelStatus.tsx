import { useEffect, useState } from "react";
import { api } from "../api";

export default function ModelStatus() {
  const [status, setStatus] = useState<any>(null);
  const [testText, setTestText] = useState("add me on snap and don't tell your parents");
  const [testResult, setTestResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.modelStatus().then(setStatus); }, []);

  async function test() {
    setBusy(true);
    try { setTestResult(await api.testModel(testText)); }
    finally { setBusy(false); }
  }

  const info = status?.tier_info;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Models</h1>

      {status && info && (
        <div className="bg-white shadow rounded p-4">
          <h2 className="font-semibold mb-2">Detection mode</h2>
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="rounded-full bg-brand-100 text-brand-700 text-xs font-semibold px-2 py-0.5">
              {info.label || status.tier}
            </span>
            <Coverage on={info.detects_images} label="Images (nudity, gore, weapons)" />
            <Coverage on={info.detects_text} label="On-screen text" />
          </div>
          <p className="text-sm text-gray-600">{info.summary}</p>
          {info.detects_images === false && (
            <p className="mt-2 text-sm text-orange-700 bg-orange-50 border border-orange-200 rounded p-2">
              This machine has no capable GPU, so visual-only risks aren't detected.
              Pair it with a GPU-enabled GuardianNode server for full coverage.
            </p>
          )}
          <div className="mt-2 text-xs text-gray-500">
            Vision model: <code>{status.vision_model}</code>
            {status.tier !== "text_only" ? null : <> · text model: <code>{status.text_model}</code></>}
          </div>
        </div>
      )}

      <div className="bg-white shadow rounded p-4">
        <h2 className="font-semibold mb-2">Ollama status</h2>
        {status ? (
          <div className="text-sm space-y-1">
            <div>URL: <code>{status.ollama_url}</code></div>
            <div>Reachable: {status.ollama_available ? "✅" : "❌"}</div>
            {status.error && <div className="text-red-700">Error: {status.error}</div>}
            <div>Installed models: {(status.models_installed || []).join(", ") || "(none)"}</div>
          </div>
        ) : <div className="text-gray-500">Loading…</div>}
      </div>

      <div className="bg-white shadow rounded p-4">
        <h2 className="font-semibold mb-2">Test the classifier</h2>
        <textarea className="w-full border rounded p-2 text-sm" rows={3}
                  value={testText} onChange={(e) => setTestText(e.target.value)} />
        <button onClick={test} disabled={busy}
                className="mt-2 bg-brand-500 hover:bg-brand-700 text-white px-3 py-2 rounded">
          {busy ? "Running…" : "Run"}
        </button>
        {testResult && (
          <pre className="mt-3 bg-gray-50 border rounded p-3 text-xs">{JSON.stringify(testResult, null, 2)}</pre>
        )}
      </div>
    </div>
  );
}

function Coverage({ on, label }: { on: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1 text-xs ${on ? "text-green-700" : "text-gray-400"}`}>
      <span>{on ? "✓" : "✕"}</span>
      {label}
    </span>
  );
}
