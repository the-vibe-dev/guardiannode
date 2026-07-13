import { useEffect, useState } from "react";
import { api } from "../api";

interface InFlight {
  event_id: string;
  tier: string;
  app_name: string | null;
  window_title: string | null;
  device_id: string | null;
  stage: string;
  elapsed_ms: number;
}

interface Health {
  status: string;
  tier: string;
  mode?: string;
  protection?: { level: "full" | "reduced" | "rules_only"; warnings: string[] };
  tesseract_available?: boolean;
  ocr?: {
    available: boolean;
    languages: string[];
    recent: {
      status_counts: Record<string, number>;
      error_counts: Record<string, number>;
    };
  };
  queue: {
    in_flight_count: number;
    in_flight: InFlight[];
    window_seconds: number;
    last_classified_at?: string | null;
    throughput: {
      frames_in_window: number;
      avg_latency_ms: number;
      p50_latency_ms: number;
      p95_latency_ms: number;
      severity_counts: Record<string, number>;
    };
  };
  pending_classification?: number;
  classification_capacity?: {
    status: "ok" | "backlog" | "unhealthy";
    estimated_delay_ms: number;
    latency_basis_ms: number;
  };
  agent_queues?: {
    device_id: string;
    hostname: string;
    queued_frames: number;
    age_seconds: number;
  }[];
  ollama: {
    url: string;
    available: boolean;
    error: string | null;
    text_model: string;
    text_model_present: boolean;
    vision_model: string;
    vision_model_present: boolean;
  };
}

export default function PipelineHealth() {
  const [h, setH] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const data = await api.pipelineHealth();
        if (!cancelled) {
          setH(data as any);
          setError(null);
        }
      } catch (e: any) {
        if (!cancelled) setError(e.message || "Unable to reach backend");
      }
    }
    tick();
    const id = setInterval(tick, 2000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm">
        Pipeline status unavailable: {error}
      </div>
    );
  }
  if (!h) return <div className="text-sm text-gray-500">Loading pipeline status…</div>;

  const busy = h.queue.in_flight_count > 0;
  const ollamaOK = h.ollama.available;
  const backlog = (h.agent_queues || []).filter((q) => q.queued_frames > 0);
  const backlogTotal = backlog.reduce((sum, q) => sum + q.queued_frames, 0);
  const pending = h.pending_classification || 0;
  const capacity = h.classification_capacity;

  const protection = h.protection;

  return (
    <div className="bg-white shadow rounded p-4">
      {/* Protection banner: is the AI actually judging frames right now? */}
      {protection && protection.level !== "full" && (
        <div
          className={`mb-3 rounded border p-3 text-sm ${
            protection.level === "rules_only"
              ? "bg-red-50 border-red-200 text-red-800"
              : "bg-yellow-50 border-yellow-300 text-yellow-800"
          }`}
        >
          <div className="font-semibold mb-1">
            {protection.level === "rules_only"
              ? "Reduced protection — running on safety rules only"
              : "Reduced protection"}
          </div>
          <ul className="list-disc ml-5 space-y-0.5">
            {protection.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      {capacity?.status === "unhealthy" && (
        <div className="mb-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          <div className="font-semibold mb-1">Classification backlog is high</div>
          <div>
            Estimated review delay is {fmtMs(capacity.estimated_delay_ms)} for {pending} waiting frame
            {pending === 1 ? "" : "s"}.
          </div>
        </div>
      )}
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold">Pipeline status</h2>
        <div className="flex items-center gap-2 text-xs">
          <Pulse
            on={busy}
            color="bg-yellow-400"
            label={busy ? `Processing ${h.queue.in_flight_count}` : "Idle"}
          />
          {pending > 0 && (
            <Pulse
              on
              color={capacity?.status === "unhealthy" ? "bg-red-500" : "bg-blue-400"}
              label={`${pending} waiting to classify`}
            />
          )}
          {backlogTotal > 0 && (
            <Pulse on color="bg-orange-400" label={`${backlogTotal} waiting upload`} />
          )}
          <Pulse on={ollamaOK} color="bg-green-500" label={ollamaOK ? "Ollama OK" : "Ollama down"} />
          <span className="text-gray-500">mode=<strong>{h.mode || h.tier}</strong></span>
        </div>
      </div>

      {/* Agent-side upload backlog (frames captured but not yet sent) */}
      {backlog.length > 0 && (
        <div className="mb-3 space-y-1">
          {backlog.map((q) => (
            <div key={q.device_id} className="flex items-center gap-2 bg-orange-50 border border-orange-200 rounded px-3 py-1.5 text-sm">
              <div className="w-2 h-2 rounded-full bg-orange-400 animate-pulse" />
              <span className="font-medium">{q.hostname}</span>
              <span className="text-gray-600">
                {q.queued_frames} frame{q.queued_frames > 1 ? "s" : ""} captured, waiting to upload
              </span>
            </div>
          ))}
        </div>
      )}

      {/* In-flight items */}
      {busy ? (
        <div className="space-y-1.5">
          <div className="text-xs text-gray-500">
            Currently classifying {h.queue.in_flight_count} frame
            {h.queue.in_flight_count > 1 ? "s" : ""}:
          </div>
          {h.queue.in_flight.map((it) => (
            <div key={it.event_id} className="flex items-center gap-3 bg-yellow-50 border border-yellow-200 rounded px-3 py-2 text-sm">
              <div className="animate-pulse w-2 h-2 rounded-full bg-yellow-500" />
              <div className="flex-1">
                <div className="font-medium">{it.app_name || "(unknown app)"}</div>
                <div className="text-xs text-gray-600 truncate">{it.window_title}</div>
              </div>
              <div className="text-xs text-gray-500">
                <div>{it.stage.replace(/_/g, " ")}</div>
                <div>{(it.elapsed_ms / 1000).toFixed(1)}s</div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-sm text-gray-500 italic">No frames in flight.</div>
      )}

      {/* Throughput */}
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs lg:grid-cols-6">
        <Stat label="Frames (5m)" value={String(h.queue.throughput.frames_in_window)} />
        <Stat label="Avg latency" value={fmtMs(h.queue.throughput.avg_latency_ms)} />
        <Stat label="P95 latency" value={fmtMs(h.queue.throughput.p95_latency_ms)} />
        <Stat label="Queue delay" value={capacity ? fmtMs(capacity.estimated_delay_ms) : "—"} />
        <Stat label="Severity" value={fmtSev(h.queue.throughput.severity_counts)} />
        <Stat label="Last classified" value={fmtWhen(h.queue.last_classified_at)} />
      </div>

      {/* Ollama models */}
      <div className="mt-3 text-xs text-gray-600 space-y-0.5">
        <div>
          OCR: {h.ocr?.available ?? h.tesseract_available ? (
            <span className="text-green-700">✓ ready</span>
          ) : (
            <span className="text-red-600">✗ unavailable</span>
          )}
          {h.ocr?.languages?.length ? <span> ({h.ocr.languages.join(", ")})</span> : null}
          {h.ocr?.recent?.error_counts && Object.keys(h.ocr.recent.error_counts).length > 0 ? (
            <span className="ml-2 text-red-600">
              recent failures: {Object.entries(h.ocr.recent.error_counts).map(([name, count]) => `${name}=${count}`).join(", ")}
            </span>
          ) : null}
        </div>
        <div>
          Ollama: <code className="bg-gray-100 px-1 rounded">{h.ollama.url}</code>
          {h.ollama.error && <span className="text-red-600 ml-2">{h.ollama.error}</span>}
        </div>
        <div>
          Text model: <code>{h.ollama.text_model}</code>{" "}
          {h.ollama.text_model_present ? (
            <span className="text-green-700">✓ loaded</span>
          ) : (
            <span className="text-red-600">✗ missing</span>
          )}
        </div>
        <div>
          Vision model: <code>{h.ollama.vision_model}</code>{" "}
          {h.ollama.vision_model_present ? (
            <span className="text-green-700">✓ loaded</span>
          ) : (
            <span className="text-red-600">✗ missing</span>
          )}
        </div>
      </div>
    </div>
  );
}

function Pulse({ on, color, label }: { on: boolean; color: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`w-2 h-2 rounded-full ${on ? color : "bg-gray-300"} ${on ? "animate-pulse" : ""}`} />
      <span className={on ? "text-gray-700" : "text-gray-400"}>{label}</span>
    </span>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-50 rounded p-2">
      <div className="text-gray-500 uppercase text-[10px]">{label}</div>
      <div className="font-mono">{value}</div>
    </div>
  );
}

function fmtMs(ms: number): string {
  if (ms === 0) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function fmtWhen(iso: string | null | undefined): string {
  if (!iso) return "never";
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 90) return `${Math.round(seconds)}s ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)}m ago`;
  return `${Math.round(seconds / 3600)}h ago`;
}

function fmtSev(counts: Record<string, number>): string {
  const parts: string[] = [];
  for (const k of ["critical", "high", "medium", "low", "none"]) {
    if (counts[k]) parts.push(`${counts[k]} ${k[0].toUpperCase()}`);
  }
  return parts.join(" ") || "—";
}
