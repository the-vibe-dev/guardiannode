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

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Models</h1>
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
