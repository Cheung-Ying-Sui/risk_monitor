"use client";

import { useCallback, useEffect, useState } from "react";
import { getInsuredVessels } from "@/services/insurance";
import type { DeclaredVessel } from "@/types/insurance";

export function useInsuredVessels(refreshIntervalMs = 0) {
  const [vessels, setVessels] = useState<DeclaredVessel[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [requestVersion, setRequestVersion] = useState(0);
  const refresh = useCallback(() => setRequestVersion(version => version + 1), []);

  useEffect(() => {
    if (refreshIntervalMs <= 0) return;
    const timer = window.setInterval(refresh, refreshIntervalMs);
    return () => window.clearInterval(timer);
  }, [refresh, refreshIntervalMs]);

  useEffect(() => {
    const controller = new AbortController();
    getInsuredVessels(controller.signal)
      .then(rows => { if (!controller.signal.aborted) { setVessels(rows); setStatus("ready"); } })
      .catch(() => { if (!controller.signal.aborted) setStatus("error"); });
    return () => controller.abort();
  }, [requestVersion]);

  return { vessels, status, refresh };
}
