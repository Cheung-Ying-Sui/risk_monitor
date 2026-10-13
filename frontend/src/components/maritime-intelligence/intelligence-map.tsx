"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { CATEGORY_PRESENTATION } from "./event-presentation";
import { createCategoryIcon } from "./category-icon";
import { createVesselMarkerBody } from "@/lib/vessel-marker";
import { vesselRiskLabel, type RiskLoadStatus } from "./vessel-risk-label";
import type { VesselRiskCount } from "@/services/ukmto";
import { getBaseMapStyle, showOnlyMarineLabels } from "@/lib/map-style";
import { configureMapLibreWorker } from "@/lib/maplibre-worker";
import type { InsuredLiveVessel } from "@/lib/insured-vessels";
import type { MaritimeIntelligenceEvent } from "@/types/maritime-intelligence";

import { hasCoordinates } from "@/services/ukmto";

// Preserve source attribution but do not render a collapsible circle-i button.
class ExpandedAttributionControl extends maplibregl.AttributionControl {
  onAdd(map: maplibregl.Map) {
    const container = super.onAdd(map);
    container.querySelector("summary")?.remove();
    container.setAttribute("open", "");
    return container;
  }
}

export function IntelligenceMap({ filterLabel, riskCounts, riskStatus, loading, events, insuredVessels, selectedEventId, selectedVesselId, onSelectEvent, onSelectVessel }: {
  filterLabel: string;
  riskCounts: VesselRiskCount[];
  riskStatus: RiskLoadStatus;
  loading: boolean;
  events: MaritimeIntelligenceEvent[];
  insuredVessels: InsuredLiveVessel[];
  selectedEventId: string | null;
  selectedVesselId: string | null;
  onSelectEvent: (eventId: string | null) => void;
  onSelectVessel: (vesselId: string | null) => void;
}) {
  const mappedEvents = useMemo(() => events.filter(hasCoordinates), [events]);
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<Map<string, maplibregl.Marker>>(new Map());
  const vesselMarkersRef = useRef<Map<string, maplibregl.Marker>>(new Map());
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState(false);

  useEffect(() => {
    if (!containerRef.current) return;
    let map: maplibregl.Map | undefined;
    let errorTimer: number | undefined;
    const markerStore = markersRef.current;
    const vesselMarkerStore = vesselMarkersRef.current;

    try {
      configureMapLibreWorker();
      map = new maplibregl.Map({
        container: containerRef.current,
        style: getBaseMapStyle("light"),
        center: [28, 18],
        zoom: 1.55,
        minZoom: 1.2,
        maxZoom: 14,
        attributionControl: false,
        dragRotate: false,
        pitchWithRotate: false,
      });
      mapRef.current = map;
      map.addControl(new ExpandedAttributionControl({ compact: false }), "bottom-right");
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.on("load", () => {
        if (!map) return;
        showOnlyMarineLabels(map);
        setMapReady(true);
      });
      map.on("click", () => { onSelectEvent(null); onSelectVessel(null); });
      map.on("error", event => {
        if (!event.error?.message.includes("404")) setMapError(true);
      });
    } catch {
      errorTimer = window.setTimeout(() => setMapError(true), 0);
    }

    return () => {
      if (errorTimer) window.clearTimeout(errorTimer);
      markerStore.forEach(marker => marker.remove());
      markerStore.clear();
      vesselMarkerStore.forEach(marker => marker.remove());
      vesselMarkerStore.clear();
      if (mapRef.current === map) mapRef.current = null;
      map?.remove();
    };
  }, [onSelectEvent, onSelectVessel]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    markersRef.current.forEach(marker => marker.remove());
    markersRef.current.clear();

    mappedEvents.forEach(event => {
      const presentation = CATEGORY_PRESENTATION[event.category];
      const markerElement = document.createElement("button");
      markerElement.type = "button";
      markerElement.className = `intelligence-marker category-${event.category} severity-${event.severity}`;
      markerElement.dataset.eventId = event.id;
      markerElement.setAttribute("aria-label", `${presentation.label}: ${event.title}`);
      const symbol = createCategoryIcon(event.category);
      markerElement.appendChild(symbol);
      markerElement.addEventListener("click", clickEvent => {
        clickEvent.stopPropagation();
        onSelectEvent(event.id);
      });

      const marker = new maplibregl.Marker({ element: markerElement, anchor: "center" })
        .setLngLat([event.longitude, event.latitude])
        .addTo(map);
      markersRef.current.set(event.id, marker);
    });

    if (mappedEvents.length === 1) {
      map.flyTo({ center: [mappedEvents[0].longitude, mappedEvents[0].latitude], zoom: 4.2, duration: 500 });
    } else if (mappedEvents.length > 1) {
      const bounds = mappedEvents.reduce(
        (currentBounds, event) => currentBounds.extend([event.longitude, event.latitude]),
        new maplibregl.LngLatBounds([mappedEvents[0].longitude, mappedEvents[0].latitude], [mappedEvents[0].longitude, mappedEvents[0].latitude]),
      );
      map.fitBounds(bounds, { padding: { top: 70, bottom: 85, left: Math.min(350, map.getContainer().clientWidth * 0.35), right: 70 }, maxZoom: 5, duration: 500 });
    }
  }, [mappedEvents, mapReady, onSelectEvent]);

  useEffect(() => {
    const map = mapRef.current;
    vesselMarkersRef.current.forEach(marker => marker.remove());
    vesselMarkersRef.current.clear();
    if (!map || !mapReady) return;
    insuredVessels.forEach(({ vessel, declaration }) => {
      if (vesselMarkersRef.current.has(vessel.id)) return;
      const markerElement = document.createElement("button");
      markerElement.type = "button";
      markerElement.className = "vessel-marker intelligence-vessel-marker";
      markerElement.appendChild(createVesselMarkerBody(vessel.markerDirection));
      const risk = riskCounts.find(row => row.vessel_id === vessel.id);
      const matchingPosition = risk?.latest_position?.observed_at && Date.parse(risk.latest_position.observed_at) === Date.parse(vessel.observedAt)
        && risk.latest_position.latitude === vessel.position[1] && risk.latest_position.longitude === vessel.position[0];
      const status = riskStatus === "ready" && risk?.calculation_status === "ok" && !matchingPosition ? "loading" : riskStatus;
      if (status === "ready" && risk?.calculation_status === "ok" && (risk.event_count ?? 0) > 0) {
        const badge = document.createElement("span");
        badge.className = "intelligence-vessel-count";
        badge.textContent = String(risk.event_count);
        markerElement.appendChild(badge);
      }
      markerElement.classList.toggle("selected", vessel.id === selectedVesselId);
      markerElement.setAttribute("aria-pressed", String(vessel.id === selectedVesselId));
      markerElement.title = `已投保船舶 ${declaration.vessel_name} · 最近 AIS 船位 · ${vessel.observedAt} · ${vesselRiskLabel(risk, status)}`;
      markerElement.setAttribute("aria-label", markerElement.title);
      markerElement.addEventListener("click", event => {
        event.stopPropagation();
        onSelectVessel(vessel.id);
      });
      const marker = new maplibregl.Marker({ element: markerElement, anchor: "center" })
        .setLngLat(vessel.position).addTo(map);
      vesselMarkersRef.current.set(vessel.id, marker);
    });
  }, [insuredVessels, mapReady, onSelectVessel, riskCounts, riskStatus, selectedVesselId]);

  useEffect(() => {
    const map = mapRef.current;
    vesselMarkersRef.current.forEach((marker, id) => marker.getElement().classList.toggle("selected", id === selectedVesselId));
    const selectedVessel = insuredVessels.find(item => item.vessel.id === selectedVesselId)?.vessel;
    if (map && selectedVessel) map.flyTo({ center: selectedVessel.position, zoom: Math.max(map.getZoom(), 5), duration: 650 });
  }, [insuredVessels, selectedVesselId, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    const selected = insuredVessels.find(item => item.vessel.id === selectedVesselId);
    if (!map || !mapReady || !selected) return;
    const risk = riskCounts.find(row => row.vessel_id === selectedVesselId);
    const position = risk?.latest_position;
    const matchingPosition = position && Date.parse(position.observed_at) === Date.parse(selected.vessel.observedAt)
      && position.latitude === selected.vessel.position[1] && position.longitude === selected.vessel.position[0];
    const status = riskStatus === "ready" && risk?.calculation_status === "ok" && !matchingPosition ? "loading" : riskStatus;
    const content = document.createElement("div");
    content.className = "intelligence-vessel-report";
    content.setAttribute("role", "status");
    const add = (tag: string, text: string) => {
      const node = document.createElement(tag);
      node.textContent = text;
      content.appendChild(node);
    };
    add("strong", selected.declaration.vessel_name);
    add("b", vesselRiskLabel(risk, status));
    add("span", "统计半径：500 海里 · " + filterLabel);
    const observedAt = risk?.latest_position?.observed_at ?? selected.vessel.observedAt;
    const observed = new Date(observedAt);
    add("span", "AIS 更新时间：" + (Number.isNaN(observed.getTime()) ? "未知" : observed.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }) + "（北京时间）"));
    add("small", "仅为当前位置附近的数据记录，不代表途经、事故概率或安全结论。");
    content.addEventListener("click", event => event.stopPropagation());
    const popup = new maplibregl.Popup({ closeButton: true, closeOnClick: false, maxWidth: "300px", offset: 18, className: "intelligence-vessel-popup" })
      .setLngLat(selected.vessel.position).setDOMContent(content).addTo(map);
    const close = () => onSelectVessel(null);
    popup.on("close", close);
    return () => { popup.off("close", close); popup.remove(); };
  }, [insuredVessels, selectedVesselId, mapReady, riskCounts, riskStatus, filterLabel, onSelectVessel]);

  useEffect(() => {
    const map = mapRef.current;
    markersRef.current.forEach((marker, eventId) => {
      marker.getElement().classList.toggle("selected", eventId === selectedEventId);
      marker.getElement().setAttribute("aria-pressed", String(eventId === selectedEventId));
    });
    const selectedEvent = mappedEvents.find(event => event.id === selectedEventId);
    if (map && selectedEvent) {
      map.flyTo({ center: [selectedEvent.longitude, selectedEvent.latitude], zoom: Math.max(map.getZoom(), 4.2), duration: 650 });
    }
  }, [mappedEvents, selectedEventId, mapReady]);

  return (
    <section className="intelligence-map" aria-label="全球海事情报事件地图">
      <div ref={containerRef} className="intelligence-map-canvas" />
      {!mapReady && !mapError && <div className="intelligence-map-state"><i />正在初始化事件地图</div>}
      {mapError && <div className="intelligence-map-state error"><i />底图暂不可用</div>}
      {mapReady && !mapError && !mappedEvents.length && !insuredVessels.length && <div className="intelligence-map-state" role="status">{loading ? "正在读取真实事件与 AIS 数据…" : "当前筛选下暂无可定位的真实数据"}</div>}
      <footer className="intelligence-map-status"><span><i />事件图层</span><span>地图 {mappedEvents.length} 条 · 无坐标 {events.length - mappedEvents.length} 条</span><span>已投保船舶 {insuredVessels.length} 艘</span><span className="intelligence-map-spacer" /><span>UKMTO 事件 / AIS 船位</span></footer>
    </section>
  );
}
