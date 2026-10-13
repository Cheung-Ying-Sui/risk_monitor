"use client";

import { useCallback, useEffect, useState } from "react";
import { toLiveVessel } from "@/components/vessel-tracking/vessel-presentation";
import { getLatestPosition, getVessels, VesselApiError } from "@/services/vessels";
import type { LiveVessel, LiveVesselLoadIssue } from "@/types/vessels";

type LoadStatus = "idle" | "loading" | "ready" | "error";
const MAX_LIVE_POSITION_AGE_MS = 24 * 60 * 60 * 1000;

class StalePositionError extends Error {}

export function useLiveVessels(enabled: boolean, refreshIntervalMs = 0) {
  const [status, setStatus] = useState<LoadStatus>("idle");
  const [vessels, setVessels] = useState<LiveVessel[]>([]);
  const [issues, setIssues] = useState<LiveVesselLoadIssue[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [requestVersion, setRequestVersion] = useState(0);

  const reload = useCallback(() => setRequestVersion(version => version + 1), []);
  const retry = useCallback(() => reload(), [reload]);
  const refresh = useCallback(() => reload(), [reload]);

  useEffect(() => {
    if (!enabled || refreshIntervalMs <= 0) return;
    const timer = window.setInterval(refresh, refreshIntervalMs);
    return () => window.clearInterval(timer);
  }, [enabled, refresh, refreshIntervalMs]);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    let cancelled = false;

    async function loadLiveVessels() {
      await Promise.resolve();
      if (cancelled) return;
      setStatus(current => current === "ready" ? "ready" : "loading");
      setIssues([]);
      setError(null);

      try {
        const apiVessels = await getVessels(controller.signal);

        // Phase 3.3 initial integration: latest positions are fetched concurrently
        // per vessel. Replace this N+1 pattern with a bulk current-status endpoint.
        const positionResults = await Promise.allSettled(
          apiVessels.map(async vessel => {
            const position = await getLatestPosition(vessel.id, controller.signal);
            const observedAt = Date.parse(position.observed_at);
            if (!Number.isFinite(observedAt) || observedAt > Date.now() + 5 * 60_000 || Date.now() - observedAt > MAX_LIVE_POSITION_AGE_MS) {
              throw new StalePositionError("AIS 船位超过 24 小时或时间无效。");
            }
            return toLiveVessel(vessel, position);
          }),
        );
        if (cancelled) return;

        const nextVessels: LiveVessel[] = [];
        const nextIssues: LiveVesselLoadIssue[] = [];
        positionResults.forEach((result, index) => {
          if (result.status === "fulfilled") {
            nextVessels.push(result.value);
            return;
          }
          const reason = result.reason;
          if (reason instanceof DOMException && reason.name === "AbortError") return;
          const notFound = reason instanceof VesselApiError && reason.status === 404;
          nextIssues.push({
            vesselId: apiVessels[index].id,
            kind: reason instanceof StalePositionError ? "stale_position" : notFound ? "position_not_found" : "position_request_failed",
            message: reason instanceof Error ? reason.message : "Latest position request failed.",
          });
        });

        setVessels(nextVessels);
        setIssues(nextIssues);
        setStatus("ready");
      } catch (reason) {
        if (cancelled || (reason instanceof DOMException && reason.name === "AbortError")) return;
        setStatus("error");
        setVessels([]);
        setIssues([]);
        setError(reason instanceof Error ? reason.message : "Unable to load vessel data.");
      }
    }

    void loadLiveVessels();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [enabled, requestVersion]);

  return { status, vessels, issues, error, retry, refresh };
}
