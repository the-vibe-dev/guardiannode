import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../api";

export default function ModelStatus() {
  const health = useQuery({ queryKey: ["model-status"], queryFn: api.modelStatus, refetchInterval: 30_000 });
  const status = health.data;
  const [testText, setTestText] = useState("add me on snap and don't tell your parents");
  const probe = useMutation({ mutationFn: api.testModel });
  const testResult = probe.data;

  const info = status?.tier_info;

  return (
    <div className="space-y-4">
      <header><h1 className="text-2xl font-bold">Models</h1><p className="mt-2 text-sm text-slate-600">Check which local models can review screenshots and extracted text. Installed models and a reachable server do not guarantee a successful review; check each device’s latest result on Home.</p></header>
      {health.isError && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">Could not load AI model status: {health.error.message}. <button onClick={() => void health.refetch()} disabled={health.isFetching} className="min-h-11 font-semibold underline disabled:opacity-50">Retry model status</button></div>}
      {health.isError && status && <p className="text-xs text-amber-900">Previously loaded model status is shown below and may be out of date.</p>}

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
              This configured mode reviews extracted text. A vision model is not assessing visual-only content in this mode.
            </p>
          )}
          <div className="mt-2 text-xs text-gray-500">
            Vision model: <code>{status.vision_model}</code>
            <> · text model: <code>{status.text_model}</code></>
          </div>
        </div>
      )}

      <div className="bg-white shadow rounded p-4">
        <h2 className="font-semibold mb-2">Ollama status</h2>
        {status ? (
          <div className="text-sm space-y-3">
            <EndpointStatus
              label="Vision"
              url={status.vision_ollama_url || status.ollama_url}
              reachable={status.vision_ollama_available ?? status.ollama_available}
              models={status.vision_models_installed || status.models_installed || []}
            />
            <EndpointStatus
              label="Text"
              url={status.text_ollama_url || status.ollama_url}
              reachable={status.text_ollama_available ?? status.ollama_available}
              models={status.text_models_installed || status.models_installed || []}
            />
            {status.error && <div className="text-red-700">Error: {status.error}</div>}
          </div>
        ) : health.isPending ? <div role="status" className="text-gray-500">Loading model status…</div> : <div className="text-gray-500">Model status unavailable.</div>}
      </div>

      <div className="bg-white shadow rounded p-4">
        <h2 className="font-semibold mb-2">Test text classification</h2>
        <p className="mb-3 text-sm text-slate-600">Use a synthetic example to check text review. This does not test screenshot capture, OCR, or vision accuracy.</p>
        <textarea disabled={probe.isPending} aria-label="Synthetic test text" className="w-full border rounded p-2 text-sm" rows={3}
                  value={testText} onChange={(e) => { setTestText(e.target.value); probe.reset(); }} />
        <button onClick={() => probe.mutate(testText)} disabled={probe.isPending || !testText.trim()}
                className="mt-2 bg-brand-500 hover:bg-brand-700 text-white px-3 py-2 rounded">
          {probe.isPending ? "Running…" : "Run text test"}
        </button>
        {probe.isError && <p role="alert" className="mt-3 text-sm text-red-700">Text test failed: {probe.error.message}. No successful result was recorded.</p>}
        {testResult && !probe.isPending && !probe.isError && (
          <pre className="mt-3 overflow-auto whitespace-pre-wrap break-words bg-gray-50 border rounded p-3 text-xs">{JSON.stringify(testResult, null, 2)}</pre>
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

function EndpointStatus({ label, url, reachable, models }: { label: string; url: string; reachable: boolean; models: string[] }) {
  return (
    <div>
      <div className="font-medium">{label}</div>
      <div>URL: <code>{url}</code></div>
      <div>Reachable: {reachable ? "yes" : "no"}</div>
      <div>Installed models: {models.join(", ") || "(none)"}</div>
    </div>
  );
}
