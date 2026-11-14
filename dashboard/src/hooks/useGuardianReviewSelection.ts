import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";

/** One selected assessment, including its durable queued/running lifecycle. */
export function useGuardianReviewSelection() {
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const selectedId = useRef<string | null>(null);
  const timer = useRef<number | null>(null);
  const mounted = useRef(false);

  const stop = useCallback(() => {
    generation.current += 1;
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; stop(); };
  }, [stop]);

  const load = useCallback(async function loadReview(reviewId: string, current: number) {
    try {
      const next = await api.guardianReview(reviewId);
      if (!mounted.current || current !== generation.current) return;
      setResult(next);
      setError(null);
      if (["queued", "running"].includes(next.status)) {
        timer.current = window.setTimeout(() => { void loadReview(reviewId, current); }, 1500);
      }
    } catch (reason) {
      if (!mounted.current || current !== generation.current) return;
      setError(reason instanceof Error ? reason.message : "Could not load this assessment.");
    } finally {
      if (mounted.current && current === generation.current) setLoading(false);
    }
  }, []);

  const view = useCallback(async (reviewId: string) => {
    stop();
    selectedId.current = reviewId;
    setResult(null);
    setError(null);
    setLoading(true);
    await load(reviewId, generation.current);
  }, [load, stop]);

  const retry = useCallback(() => {
    if (selectedId.current) void view(selectedId.current);
  }, [view]);

  const recordDeletion = useCallback((reviewId: string) => {
    if (selectedId.current !== reviewId) return;
    stop();
    // Do not keep the assessment or preview mounted while awaiting a refresh.
    // Invalidating this selection prevents an older read from restoring it.
    setResult({ review_id: reviewId, status: "deleted" });
    setError(null);
    setLoading(false);
  }, [stop]);

  const clear = useCallback(() => {
    stop();
    selectedId.current = null;
    setResult(null);
    setError(null);
    setLoading(false);
  }, [stop]);

  return { result, loading, error, view, retry, recordDeletion, clear };
}
