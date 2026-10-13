"use client";
import { useCallback, useEffect, useState } from "react";
import { getInsuranceVoyagePredictions } from "@/services/vessels";
import type { InsuranceVoyagePrediction } from "@/types/navigation";

export function useInsuranceVoyagePredictions(enabled: boolean) {
  const [result, setResult] = useState<{ items: InsuranceVoyagePrediction[]; status: "loading" | "ready" | "error"; error: string | null }>({ items: [], status: "loading", error: null });
  const [version, setVersion] = useState(0);
  const [previousEnabled, setPreviousEnabled] = useState(enabled);
  // Discard the previous mode's snapshot before children can render its route.
  if (previousEnabled !== enabled) {
    setPreviousEnabled(enabled);
    setResult({ items: [], status: "loading", error: null });
  }
  const retry = useCallback(() => setVersion(v => v+1), []);
  useEffect(() => {
    if (!enabled) return;
    let controller: AbortController | null = null;
    let cancelled = false;
    let inFlight = false;
    const load = () => {
      controller?.abort();
      const request = new AbortController();
      controller = request;
      inFlight = true;
      setResult({ items: [], status: "loading", error: null });
      getInsuranceVoyagePredictions(AbortSignal.any([request.signal, AbortSignal.timeout(30000)]))
        .then(items => { if (!cancelled && !request.signal.aborted) setResult({ items, status: "ready", error: null }); })
        .catch(error => { if (!cancelled && !request.signal.aborted) setResult({ items: [], status: "error", error: error instanceof Error ? error.message : "承保航程预测不可用" }); })
        .finally(() => { if (controller === request) inFlight = false; });
    };
    void Promise.resolve().then(() => { if (!cancelled) load(); });
    const timer = window.setInterval(() => { if (!inFlight) load(); }, 15000);
    const onStorage = (event: StorageEvent) => { if (event.key === "insurance-workspace-updated") load(); };
    window.addEventListener("insurance-workspace-updated", load);
    window.addEventListener("storage", onStorage);
    window.addEventListener("focus", load);
    return () => {
      cancelled = true; controller?.abort(); window.clearInterval(timer);
      window.removeEventListener("insurance-workspace-updated", load);
      window.removeEventListener("storage", onStorage); window.removeEventListener("focus", load);
    };
  }, [enabled, version]);
  return { ...result, items: enabled ? result.items : [], retry };
}
