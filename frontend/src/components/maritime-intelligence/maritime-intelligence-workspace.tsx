"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { EventDetailPanel } from "./event-detail-panel";
import { IntelligenceFeed, type IntelligenceFilter, type IntelligenceTimeRange } from "./intelligence-feed";
import { IntelligenceMap } from "./intelligence-map";
import { fetchUKMTOEvents, fetchVesselRiskCounts, incidentQueryParams, type VesselRiskCount } from "@/services/ukmto";
import { useInsuredVessels } from "@/hooks/use-insured-vessels";
import { useLiveVessels } from "@/hooks/use-live-vessels";
import { matchInsuredLiveVessels } from "@/lib/insured-vessels";
import type { MaritimeIntelligenceEvent } from "@/types/maritime-intelligence";

export function MaritimeIntelligenceWorkspace() {
  const insuranceData = useInsuredVessels(60_000);
  const trackedData = useLiveVessels(true, 60_000);
  const refreshInsured = insuranceData.refresh;
  const refreshTracked = trackedData.refresh;
  const mappedInsuredVessels = useMemo(() => insuranceData.status === "ready"
    ? matchInsuredLiveVessels(insuranceData.vessels, trackedData.vessels)
    : [], [insuranceData.status, insuranceData.vessels, trackedData.vessels]);
  const [activeFilter, setActiveFilter] = useState<IntelligenceFilter>("all");
  const [timeRange, setTimeRange] = useState<IntelligenceTimeRange>("all");
  const [customStartDate, setCustomStartDate] = useState("");
  const [customEndDate, setCustomEndDate] = useState("");
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [selectedVesselId, setSelectedVesselId] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<{ key: string; events: MaritimeIntelligenceEvent[]; error: string | null }>({ key: "", events: [], error: null });
  const key = JSON.stringify([activeFilter, timeRange, customStartDate, customEndDate, revision]);
  const params = useMemo(() => {
    if (timeRange === "custom" && (!customStartDate || !customEndDate || customStartDate > customEndDate)) return null;
    return incidentQueryParams({ category: activeFilter, timeRange, start: customStartDate, end: customEndDate });
    // Revision also advances the relative time window on refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeFilter, timeRange, customStartDate, customEndDate, revision]);
  const riskKey = JSON.stringify([key, insuranceData.vessels, trackedData.vessels]);
  const [riskResult, setRiskResult] = useState<{ key: string; rows: VesselRiskCount[]; error: boolean }>({ key: "", rows: [], error: false });
  const riskStatus = riskResult.key !== riskKey ? "loading" : riskResult.error ? "error" : "ready";
  const riskCounts = riskResult.key === riskKey && !riskResult.error ? riskResult.rows : [];
  const filterLabel = `UKMTO 发布时间（UTC）：${params?.get("from") ?? "不限起始时间"} 至 ${params?.get("to") ?? "不限结束时间"}；类别：${activeFilter === "all" ? "全部" : activeFilter}`;
  const validationError = timeRange === "custom" && (!customStartDate || !customEndDate || customStartDate > customEndDate)
    ? "请选择有效的开始和结束日期。" : null;
  const loading = !validationError && result.key !== key;
  const events = result.key === key && !validationError ? result.events : [];
  const error = validationError || (result.key === key ? result.error : null);
  const detailEvent = events.find(event => event.id === selectedEventId) ?? null;
  const selectEvent = useCallback((id: string | null) => { setSelectedEventId(id); if (id) setSelectedVesselId(null); }, []);
  const selectVessel = useCallback((id: string | null) => { setSelectedVesselId(id); if (id) setSelectedEventId(null); }, []);
  const refreshAll = useCallback(() => {
    setRevision(value => value + 1);
    refreshInsured();
    refreshTracked();
  }, [refreshInsured, refreshTracked]);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => { if (event.key === "insurance-workspace-updated") refreshAll(); };
    window.addEventListener("insurance-workspace-updated", refreshAll);
    window.addEventListener("storage", onStorage);
    window.addEventListener("focus", refreshAll);
    return () => {
      window.removeEventListener("insurance-workspace-updated", refreshAll);
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("focus", refreshAll);
    };
  }, [refreshAll]);

  useEffect(() => {
    if (validationError) return;
    const controller = new AbortController();
    fetchUKMTOEvents({ category: activeFilter, timeRange, start: customStartDate, end: customEndDate }, controller.signal, params ?? undefined)
      .then(events => { if (!controller.signal.aborted) setResult({ key, events, error: null }); })
      .catch(error => {
        if (!controller.signal.aborted) setResult({ key, events: [], error: error instanceof Error && error.name !== "TypeError" && error.name !== "TimeoutError"
          ? error.message : "暂时无法获取 UKMTO 事件，请检查服务连接后重试。" });
      });
    return () => controller.abort();
  }, [key, activeFilter, timeRange, customStartDate, customEndDate, validationError, params]);

  useEffect(() => {
    if (!params) return;
    const controller = new AbortController();
    fetchVesselRiskCounts(params, controller.signal)
      .then(rows => { if (!controller.signal.aborted) setRiskResult({ key: riskKey, rows, error: false }); })
      .catch(() => { if (!controller.signal.aborted) setRiskResult({ key: riskKey, rows: [], error: true }); });
    return () => controller.abort();
  }, [params, riskKey]);

  return (
    <div className={`maritime-intelligence-workspace${detailEvent ? " has-event-detail" : ""}`}>
      <IntelligenceFeed events={events} insuredVessels={insuranceData.vessels} insuredLiveVessels={mappedInsuredVessels}
        insuranceStatus={insuranceData.status} trackingStatus={trackedData.status} activeFilter={activeFilter} timeRange={timeRange}
        customStartDate={customStartDate} customEndDate={customEndDate} selectedEventId={selectedEventId}
        selectedVesselId={selectedVesselId} onSelectVessel={selectVessel}
        loading={loading} error={error} onRefresh={refreshAll}
        onFilterChange={filter => { setActiveFilter(filter); setSelectedEventId(null); }}
        onTimeRangeChange={range => { setTimeRange(range); setSelectedEventId(null); }}
        onCustomStartDateChange={date => { setCustomStartDate(date); setSelectedEventId(null); }}
        onCustomEndDateChange={date => { setCustomEndDate(date); setSelectedEventId(null); }}
        onSelectEvent={selectEvent} />
      <IntelligenceMap events={events} insuredVessels={mappedInsuredVessels} selectedEventId={selectedEventId}
        riskCounts={riskCounts} riskStatus={validationError ? "error" : riskStatus} filterLabel={filterLabel} loading={loading || insuranceData.status === "loading" || trackedData.status === "loading"}
        selectedVesselId={selectedVesselId} onSelectEvent={selectEvent} onSelectVessel={selectVessel} />
      {detailEvent && <EventDetailPanel event={detailEvent} onClose={() => setSelectedEventId(null)} />}
    </div>
  );
}
