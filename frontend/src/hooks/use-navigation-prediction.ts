"use client";

import { useCallback, useEffect, useState } from "react";
import { getNavigationPrediction, VesselApiError } from "@/services/vessels";
import type { NavigationPrediction } from "@/types/navigation";

export type PredictionLoadStatus = "idle" | "loading" | "ready" | "not_found" | "error";

export function useNavigationPrediction(vesselId: string | null, enabled: boolean) {
  const [status, setStatus] = useState<PredictionLoadStatus>("idle");
  const [prediction, setPrediction] = useState<NavigationPrediction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadedForVesselId, setLoadedForVesselId] = useState<string | null>(null);
  const [requestVersion, setRequestVersion] = useState(0);
  const retry = useCallback(() => setRequestVersion(version => version + 1), []);

  useEffect(() => {
    if (!enabled || !vesselId) {
      return;
    }

    const currentVesselId = vesselId;
    const controller = new AbortController();
    let cancelled = false;

    async function loadPrediction() {
      await Promise.resolve();
      if (cancelled) return;
      setLoadedForVesselId(currentVesselId);
      setStatus("loading");
      setPrediction(null);
      setError(null);

      try {
        const result = await getNavigationPrediction(currentVesselId, controller.signal);
        if (cancelled) return;
        setPrediction(result);
        setStatus("ready");
      } catch (reason) {
        if (cancelled || (reason instanceof DOMException && reason.name === "AbortError")) return;
        if (reason instanceof VesselApiError && reason.status === 404) {
          setStatus("not_found");
          setError("该船暂无可用预测，AIS 目的港可能尚未识别。");
          return;
        }
        setStatus("error");
        setError(reason instanceof Error ? reason.message : "无法读取船舶预测。");
      }
    }

    void loadPrediction();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [enabled, requestVersion, vesselId]);

  if (!enabled || !vesselId) return { status: "idle" as const, prediction: null, error: null, retry };
  if (loadedForVesselId !== vesselId) return { status: "loading" as const, prediction: null, error: null, retry };
  return { status, prediction, error, retry };
}
