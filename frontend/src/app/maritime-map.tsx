"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { Feature, FeatureCollection, LineString } from "geojson";
import "maplibre-gl/dist/maplibre-gl.css";
import { LiveVesselList } from "@/components/vessel-tracking/live-vessel-list";
import { NavigationPredictionBrowser } from "@/components/vessel-tracking/navigation-prediction-browser";
import PortHumidityLayer from "@/components/vessel-tracking/port-humidity-layer";
import "./port-humidity.css";
import { formatCoordinate, formatNullableNumber, formatObservedAt, parseVesselSearchIdentifier, toVesselSearchResult } from "@/components/vessel-tracking/vessel-presentation";
import { useLiveVessels } from "@/hooks/use-live-vessels";
import { useInsuredVessels } from "@/hooks/use-insured-vessels";
import { matchesInsuredVessel } from "@/lib/insured-vessels";
import { createVesselMarkerBody } from "@/lib/vessel-marker";
import { useInsuranceVoyagePredictions } from "@/hooks/use-insurance-voyage-predictions";
import { getBaseMapLabel, getBaseMapStyle, showOnlyMarineLabels, type MapTheme } from "@/lib/map-style";
import { configureMapLibreWorker } from "@/lib/maplibre-worker";
import { getRiskZonesGeoJsonUrl } from "@/services/risk-zones";
import { addTrackingVessel, searchVesselByImo, searchVesselByMmsi, stopTrackingVessel, VesselApiError } from "@/services/vessels";
import type { NavigationPrediction } from "@/types/navigation";
import type { LiveVessel, VesselSearchResult } from "@/types/vessels";

type VesselInfoTab = "overview" | "risk";
type TrackingMode = "live" | "prediction";
const VESSEL_INFO_TABS: Array<{ id: VesselInfoTab; label: string }> = [
  { id: "overview", label: "概览" },
  { id: "risk", label: "风险" },
];

const TRACKING_MODES: Array<{ id: TrackingMode; label: string }> = [
  { id: "live", label: "实时" },
  { id: "prediction", label: "预测" },
];

type LineSourceData = Feature<LineString> | FeatureCollection<LineString>;

const EMPTY_LINE: FeatureCollection<LineString> = {
  type: "FeatureCollection",
  features: [],
};

function lineFeature(coordinates: Array<[number, number]>, scope: string): Feature<LineString> {
  return {
    type: "Feature",
    properties: { scope },
    geometry: { type: "LineString", coordinates },
  };
}

interface VesselPanelData {
  id: string;
  name: string;
  imo: string | null;
  mmsi: string | null;
  shipType: string | null;
  aisStatus: string;
  insuranceStatus: string;
  position: [number, number];
  sog: number | null;
  cog: number | null;
  heading: number | null;
  navigationStatus: string;
  destination: string | null;
  lastAisUpdate: string;
  voyage: { origin: string | null; eta: string | null; progress: number | null; historicalTrackStatus: string; predictedRouteStatus: string };
  risk: { overall: string; jwcExposure: string; warRisk: string; sanctionsStatus: string; routeDeviation: string; aisFreshness: string };
}

function liveVesselPanelData(vessel: LiveVessel, prediction: NavigationPrediction | null = null, insuranceStatus = "投保状态待核验"): VesselPanelData {
  const routeDeviation = prediction?.route.status === "deviating" ? "偏离航线" : prediction ? "正常" : "暂无数据";
  return {
    id: vessel.id,
    name: vessel.name,
    imo: vessel.imo,
    mmsi: vessel.mmsi,
    shipType: vessel.shipType,
    aisStatus: vessel.aisStatus,
    insuranceStatus,
    position: vessel.position,
    sog: vessel.sog,
    cog: vessel.cog,
    heading: vessel.heading,
    navigationStatus: vessel.navigationStatus,
    destination: prediction?.destination.name ?? vessel.destination,
    lastAisUpdate: formatObservedAt(vessel.observedAt),
    voyage: {
      origin: null,
      eta: prediction?.eta.estimated_arrival_at ? formatObservedAt(prediction.eta.estimated_arrival_at) : null,
      progress: prediction ? Math.round(prediction.route.progress * 1000) / 10 : null,
      historicalTrackStatus: "暂无数据",
      predictedRouteStatus: prediction ? "启用" : "暂无数据",
    },
    risk: { overall: "暂无数据", jwcExposure: "暂无数据", warRisk: "暂无数据", sanctionsStatus: "暂无数据", routeDeviation, aisFreshness: "暂无数据" },
  };
}

function applyTrackingMode(map: maplibregl.Map, mode: TrackingMode) {
  const predictedVisibility = mode === "prediction" ? "visible" : "none";
  if (map.getLayer("predicted-route-line")) map.setLayoutProperty("predicted-route-line", "visibility", predictedVisibility);
}

function clearLineSource(map: maplibregl.Map, sourceId: string) {
  (map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined)?.setData(EMPTY_LINE);
}

function addRiskZoneLayers(map: maplibregl.Map, theme: MapTheme) {
  const isLight = theme === "light";
  if (!map.getSource("high-risk-sea-areas")) {
    map.addSource("high-risk-sea-areas", {
      type: "geojson",
      data: getRiskZonesGeoJsonUrl(),
      generateId: true,
    });
  }
  if (!map.getLayer("high-risk-sea-fill")) {
    map.addLayer({
      id: "high-risk-sea-fill",
      type: "fill",
      source: "high-risk-sea-areas",
      paint: {
        "fill-color": isLight ? "#d73535" : "#e65252",
        "fill-opacity": isLight ? 0.2 : 0.24,
      },
    });
  }
  if (!map.getLayer("high-risk-sea-outline")) {
    map.addLayer({
      id: "high-risk-sea-outline",
      type: "line",
      source: "high-risk-sea-areas",
      paint: {
        "line-color": isLight ? "#bb2222" : "#ff6b6b",
        "line-width": ["interpolate", ["linear"], ["zoom"], 2, 1, 8, 2.25],
        "line-opacity": 0.9,
      },
    });
  }
}

function VesselStatus({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "positive" | "warning" | "critical" | "info" | "neutral" }) {
  return <span className={`vessel-status ${tone}`}>{children}</span>;
}

function VesselInfoPanel({ vessel, activeTab, onTabChange, onClose }: { vessel: VesselPanelData; activeTab: VesselInfoTab; onTabChange: (tab: VesselInfoTab) => void; onClose: () => void }) {
  const [longitude, latitude] = vessel.position;

  return (
    <aside className="vessel-info-panel" aria-label={`${vessel.name} 船舶信息`}>
      <header className="vessel-info-header">
        <div>
          <span className="vessel-info-kicker">已选船舶</span>
          <strong>{vessel.name}</strong>
        </div>
        <button type="button" className="vessel-info-close" aria-label="关闭船舶信息" onClick={onClose}>×</button>
      </header>

      <nav className="vessel-info-tabs" role="tablist" aria-label="船舶信息分区">
        {VESSEL_INFO_TABS.map(tab => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            className={activeTab === tab.id ? "active" : ""}
            onClick={() => onTabChange(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <div className="vessel-info-content">
        {activeTab === "overview" && (
          <section className="vessel-tab-panel vessel-overview" role="tabpanel">
            <div className="overview-status-row">
              <span>AIS 状态</span>
              <VesselStatus tone="positive">{vessel.aisStatus}</VesselStatus>
            </div>
            <div className="overview-status-row"><span>投保申报状态</span><VesselStatus tone={vessel.insuranceStatus === "Demo" ? "warning" : "info"}>{vessel.insuranceStatus}</VesselStatus></div>

            <div className="overview-group">
              <div className="overview-labels overview-three-columns"><span>船型</span><span>IMO</span><span>MMSI</span></div>
              <div className="overview-data-strip overview-three-columns">
                <strong>{vessel.shipType ?? "—"}</strong>
                <strong>{vessel.imo ?? "—"}</strong>
                <strong>{vessel.mmsi ?? "—"}</strong>
              </div>
            </div>

            <div className="overview-group">
              <span className="overview-section-label">当前位置</span>
              <div className="overview-data-strip overview-position-strip">
                <div><small>纬度</small><strong>{formatCoordinate(latitude, "latitude")}</strong></div>
                <div><small>经度</small><strong>{formatCoordinate(longitude, "longitude")}</strong></div>
                <div><small>最近 AIS</small><strong>{vessel.lastAisUpdate}</strong></div>
              </div>
            </div>

            <div className="overview-group">
              <div className="overview-labels overview-three-columns overview-voyage-labels"><span>起运港</span><span>目的港</span><span>预计到达</span></div>
              <div className="overview-data-strip overview-three-columns overview-voyage-strip">
                <strong>{vessel.voyage.origin ?? "—"}</strong>
                <strong>{vessel.destination ?? "—"}</strong>
                <strong>{vessel.voyage.eta ?? "—"}</strong>
              </div>
            </div>

            <div className="overview-progress">
              <div><span>航程进度</span><strong>{vessel.voyage.progress === null ? "—" : `${vessel.voyage.progress}%`}</strong></div>
              <div className="voyage-progress-track"><i style={{ width: `${vessel.voyage.progress ?? 0}%` }} /></div>
            </div>

            <div className="overview-kpis">
              <div><span>SOG</span><strong>{formatNullableNumber(vessel.sog, " kn")}</strong></div>
              <div><span>COG</span><strong>{formatNullableNumber(vessel.cog, "°")}</strong></div>
              <div><span>船首向</span><strong>{formatNullableNumber(vessel.heading, "°")}</strong></div>
            </div>

            <div className="overview-navigation">
              <span>航行状态</span>
              <strong>{vessel.navigationStatus}</strong>
            </div>

            <div className="overview-route-status">
              <div><span>历史轨迹</span><VesselStatus tone={vessel.voyage.historicalTrackStatus === "可用" ? "positive" : "neutral"}>{vessel.voyage.historicalTrackStatus}</VesselStatus></div>
              <div><span>预测航线</span><VesselStatus tone={vessel.voyage.predictedRouteStatus === "启用" ? "info" : "neutral"}>{vessel.voyage.predictedRouteStatus}</VesselStatus></div>
            </div>
          </section>
        )}

        {activeTab === "risk" && (
          <section className="vessel-tab-panel vessel-risk-panel" role="tabpanel">
            <div className="overview-status-row">
              <span>综合风险</span>
              <VesselStatus tone={vessel.risk.overall === "暂无数据" ? "neutral" : "warning"}>{vessel.risk.overall}</VesselStatus>
            </div>

            <div className="overview-group">
              <div className="overview-labels risk-three-columns"><span>JWC 风险区暴露</span><span>战争险风险</span><span>制裁状态</span></div>
              <div className="risk-data-strip risk-three-columns">
                <VesselStatus tone={vessel.risk.jwcExposure === "暂无数据" ? "neutral" : "positive"}>{vessel.risk.jwcExposure}</VesselStatus>
                <VesselStatus tone={vessel.risk.warRisk === "暂无数据" ? "neutral" : "positive"}>{vessel.risk.warRisk}</VesselStatus>
                <VesselStatus tone={vessel.risk.sanctionsStatus === "暂无数据" ? "neutral" : "positive"}>{vessel.risk.sanctionsStatus}</VesselStatus>
              </div>
            </div>

            <div className="risk-secondary-grid">
              <div><span>航线偏离</span><VesselStatus tone={vessel.risk.routeDeviation === "暂无数据" ? "neutral" : "positive"}>{vessel.risk.routeDeviation}</VesselStatus></div>
              <div><span>AIS 数据时效</span><VesselStatus tone={vessel.risk.aisFreshness === "暂无数据" ? "neutral" : "positive"}>{vessel.risk.aisFreshness}</VesselStatus></div>
            </div>
          </section>
        )}
      </div>
    </aside>
  );
}

export default function MaritimeMap() {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<maplibregl.Map | null>(null);
  const predictedLineRef = useRef<LineSourceData>(EMPTY_LINE);
  const liveMarkersRef = useRef<Map<string, { marker: maplibregl.Marker; element: HTMLDivElement }>>(new Map());
  const searchPreviewMarkerRef = useRef<maplibregl.Marker | null>(null);
  const trackingModeRef = useRef<TrackingMode>("live");
  const ignoreMapDeselectRef = useRef(false);
  const longitudeRef = useRef<HTMLSpanElement>(null);
  const latitudeRef = useRef<HTMLSpanElement>(null);
  const zoomRef = useRef<HTMLSpanElement>(null);
  const mapThemeLabelRef = useRef<HTMLSpanElement>(null);
  const [mapState, setMapState] = useState<"loading" | "ready" | "error">("loading");
  const [humidityMap, setHumidityMap] = useState<maplibregl.Map | null>(null);
  const [humidityOpen, setHumidityOpen] = useState(false);
  const [liveSelectedVesselId, setSelectedVesselId] = useState<string | null>(null);
  const [selectedShipmentId, setSelectedShipmentId] = useState<string | null>(null);
  const [activeInfoTab, setActiveInfoTab] = useState<VesselInfoTab>("overview");
  const [trackingMode, setTrackingMode] = useState<TrackingMode>("live");
  const [vesselSearchQuery, setVesselSearchQuery] = useState("");
  const [vesselSearchResult, setVesselSearchResult] = useState<VesselSearchResult | null>(null);
  const [vesselSearchLoading, setVesselSearchLoading] = useState(false);
  const [vesselSearchError, setVesselSearchError] = useState<string | null>(null);
  const [addingVessel, setAddingVessel] = useState(false);
  const [addVesselError, setAddVesselError] = useState<string | null>(null);
  const [stoppingVesselId, setStoppingVesselId] = useState<string | null>(null);
  const [stopVesselError, setStopVesselError] = useState<{ vesselId: string; message: string } | null>(null);
  const [previewedSearchVesselId, setPreviewedSearchVesselId] = useState<string | null>(null);
  const [pendingSelectedVesselId, setPendingSelectedVesselId] = useState<string | null>(null);
  const liveData = useLiveVessels(true, 60000);
  const insuranceData = useInsuredVessels(60000);
  const voyagesData = useInsuranceVoyagePredictions(trackingMode === "prediction");
  const selectedVoyage = voyagesData.items.find(v => v.shipment_id === selectedShipmentId) ?? null;
  const selectedVesselId = trackingMode === "prediction" ? selectedVoyage?.vessel_id ?? null : liveSelectedVesselId;
  const selectedVessel = liveData.vessels.find(vessel => vessel.id === selectedVesselId) ?? null;
  const predictionData = { status: voyagesData.status, prediction: selectedVoyage?.status === "estimated" ? selectedVoyage.prediction : null };
  const displayedVessel = selectedVessel
    ? liveVesselPanelData(selectedVessel, trackingMode === "prediction" ? predictionData.prediction : null,
      insuranceData.status === "ready" ? (insuranceData.vessels.some(vessel => matchesInsuredVessel(selectedVessel, vessel)) ? "投保申报" : "Demo") : "投保状态待核验")
    : null;

  const normalizedVesselQuery = vesselSearchQuery.trim().toLowerCase();
  const searchedVessel = useMemo(() => {
    if (!normalizedVesselQuery) return null;
    return liveData.vessels.find(vessel => [vessel.name, vessel.imo, vessel.mmsi].some(value => value?.toLowerCase().includes(normalizedVesselQuery))) ?? null;
  }, [liveData.vessels, normalizedVesselQuery]);

  const selectSearchedVessel = () => {
    if (!searchedVessel) return;
    setSelectedVesselId(searchedVessel.id);
    setActiveInfoTab("overview");
    mapInstanceRef.current?.flyTo({ center: searchedVessel.position, zoom: 8, duration: 650 });
  };

  const selectLiveVesselFromList = (vesselId: string) => {
    const vessel = liveData.vessels.find(candidate => candidate.id === vesselId);
    if (!vessel) return;
    setSelectedVesselId(vessel.id);
    setActiveInfoTab("overview");
    const map = mapInstanceRef.current;
    map?.flyTo({ center: vessel.position, zoom: Math.max(map.getZoom(), 7), duration: 650 });
  };

  const updateLiveSearchQuery = (value: string) => {
    setVesselSearchQuery(value);
    setVesselSearchResult(null);
    setVesselSearchError(null);
    setAddVesselError(null);
    setPreviewedSearchVesselId(null);
  };

  const searchVesselDatabase = async () => {
    const identifier = parseVesselSearchIdentifier(vesselSearchQuery);
    if (!identifier) {
      setVesselSearchResult(null);
      setVesselSearchError("请输入有效的 IMO 或 MMSI。");
      return;
    }

    setVesselSearchLoading(true);
    setVesselSearchError(null);
    setAddVesselError(null);
    setPreviewedSearchVesselId(null);
    try {
      const apiResult = identifier.kind === "imo"
        ? await searchVesselByImo(identifier.value)
        : await searchVesselByMmsi(identifier.value);
      setVesselSearchResult(toVesselSearchResult(apiResult));
    } catch (error) {
      setVesselSearchResult(null);
      setVesselSearchError(error instanceof VesselApiError && error.status === 404 ? "未找到该船舶。" : "暂时无法搜索船舶。");
    } finally {
      setVesselSearchLoading(false);
    }
  };

  const locateSearchResult = () => {
    const position = vesselSearchResult?.latestPosition?.position;
    if (!vesselSearchResult || !position) return;
    setPreviewedSearchVesselId(vesselSearchResult.id);
    const map = mapInstanceRef.current;
    map?.flyTo({ center: position, zoom: Math.max(map.getZoom(), 7), duration: 650 });
  };

  const addSearchResultToTracking = async () => {
    if (!vesselSearchResult || vesselSearchResult.isTracked || addingVessel) return;
    setAddingVessel(true);
    setAddVesselError(null);
    try {
      const status = await addTrackingVessel(vesselSearchResult.id);
      if (!status.is_active) throw new Error("Tracking was not activated.");
      setVesselSearchResult(current => current?.id === status.vessel_id ? { ...current, isTracked: true } : current);
      setPreviewedSearchVesselId(null);
      if (vesselSearchResult.latestPosition) setPendingSelectedVesselId(vesselSearchResult.id);
      liveData.refresh();
    } catch {
      setAddVesselError("无法将船舶加入跟踪。");
    } finally {
      setAddingVessel(false);
    }
  };

  const stopLiveTracking = async (vesselId: string) => {
    if (stoppingVesselId) return false;
    setStoppingVesselId(vesselId);
    setStopVesselError(null);
    try {
      const status = await stopTrackingVessel(vesselId);
      if (status.is_active) throw new Error("Tracking remains active.");
      if (selectedVesselId === vesselId) setSelectedVesselId(null);
      setVesselSearchResult(current => current?.id === vesselId ? { ...current, isTracked: false } : current);
      setPreviewedSearchVesselId(current => current === vesselId ? null : current);
      liveData.refresh();
      return true;
    } catch {
      setStopVesselError({ vesselId, message: "无法停止船舶跟踪。" });
      return false;
    } finally {
      setStoppingVesselId(null);
    }
  };

  const changeTrackingMode = (mode: TrackingMode) => {
    setTrackingMode(mode);
    setSelectedVesselId(null);
    setVesselSearchQuery("");
    setVesselSearchResult(null);
    setVesselSearchError(null);
    setAddVesselError(null);
    setPreviewedSearchVesselId(null);
  };

  useEffect(() => {
    trackingModeRef.current = trackingMode;
    const map = mapInstanceRef.current;
    if (!map) return;
    applyTrackingMode(map, trackingMode);
    liveMarkersRef.current.forEach(({ element }, vesselId) => {
      element.style.display = trackingMode === "live" || (trackingMode === "prediction" && vesselId === selectedVesselId) ? "grid" : "none";
    });
  }, [selectedVesselId, trackingMode]);

  useEffect(() => {
    liveMarkersRef.current.forEach(({ element }, vesselId) => element.classList.toggle("selected", selectedVesselId === vesselId));
  }, [selectedVesselId, trackingMode]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || mapState !== "ready") return;
    if (trackingMode !== "prediction" || predictionData.status !== "ready" || !predictionData.prediction) {
      predictedLineRef.current = EMPTY_LINE;
      clearLineSource(map, "predicted-route");
      return;
    }

    const coordinates = predictionData.prediction.route.remaining_geojson.coordinates;
    if (coordinates.length < 2) {
      predictedLineRef.current = EMPTY_LINE;
      clearLineSource(map, "predicted-route");
      return;
    }
    predictedLineRef.current = lineFeature(coordinates, "backend_navigation_prediction");
    (map.getSource("predicted-route") as maplibregl.GeoJSONSource | undefined)?.setData(predictedLineRef.current);
    const bounds = coordinates.reduce(
      (currentBounds, coordinate) => currentBounds.extend(coordinate),
      new maplibregl.LngLatBounds(coordinates[0], coordinates[0]),
    );
    if (selectedVessel) bounds.extend(selectedVessel.position);
    map.fitBounds(bounds, { padding: 80, maxZoom: 8, duration: 650 });
  }, [mapState, predictionData.prediction, predictionData.status, selectedVessel, trackingMode]);

  useEffect(() => {
    if (!mapContainerRef.current) return;

    let map: maplibregl.Map | undefined;
    let errorTimeout: number | undefined;
    let overlaysReady = false;
    let riskZonePopup: maplibregl.Popup | undefined;
    let hoveredRiskZoneId: string | number | undefined;
    const liveMarkerStore = liveMarkersRef.current;
    const theme: MapTheme = "light";

    try {
      configureMapLibreWorker();
      map = new maplibregl.Map({
        container: mapContainerRef.current,
        style: getBaseMapStyle(theme),
        center: [124.1, 29.35],
        zoom: 6.2,
        minZoom: 2,
        maxZoom: 15,
        pitch: 0,
        dragRotate: false,
        pitchWithRotate: false,
        attributionControl: { compact: false },
      });
      mapInstanceRef.current = map;

      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      if (mapThemeLabelRef.current) mapThemeLabelRef.current.textContent = getBaseMapLabel(theme);

      map.on("style.load", () => {
        if (!map) return;
        overlaysReady = true;

        showOnlyMarineLabels(map);
        addRiskZoneLayers(map, theme);

        map.addSource("predicted-route", { type: "geojson", data: predictedLineRef.current });
        map.addLayer({
          id: "predicted-route-line",
          type: "line",
          source: "predicted-route",
          layout: { "line-cap": "butt", "line-join": "round" },
          paint: {
            "line-color": "#42b7ff",
            "line-width": 3,
            "line-opacity": 0.92,
            "line-dasharray": [2, 2],
          },
        });

        applyTrackingMode(map, trackingModeRef.current);

        setMapState("ready");
        setHumidityMap(map);
      });

      const updateMapReadout = () => {
        if (!map) return;
        const center = map.getCenter();
        if (longitudeRef.current) longitudeRef.current.textContent = `${Math.abs(center.lng).toFixed(2)}°${center.lng >= 0 ? "E" : "W"}`;
        if (latitudeRef.current) latitudeRef.current.textContent = `${Math.abs(center.lat).toFixed(2)}°${center.lat >= 0 ? "N" : "S"}`;
        if (zoomRef.current) zoomRef.current.textContent = map.getZoom().toFixed(1);
      };

      map.on("move", updateMapReadout);
      riskZonePopup = new maplibregl.Popup({
        closeButton: false,
        closeOnClick: false,
        offset: 12,
        className: "risk-zone-popup",
      });
      map.on("mousemove", event => {
        if (!map?.getLayer("high-risk-sea-fill")) return;
        const [feature] = map.queryRenderedFeatures(event.point, { layers: ["high-risk-sea-fill"] });
        const nextRiskZoneId = feature?.id;
        if (!feature) {
          hoveredRiskZoneId = undefined;
          map.getCanvas().style.cursor = "";
          riskZonePopup?.remove();
          return;
        }

        map.getCanvas().style.cursor = "pointer";
        if (nextRiskZoneId === hoveredRiskZoneId && riskZonePopup?.isOpen()) {
          riskZonePopup.setLngLat(event.lngLat);
          return;
        }
        hoveredRiskZoneId = nextRiskZoneId;
        const content = document.createElement("div");
        content.className = "risk-zone-popup-content";
        const title = document.createElement("strong");
        title.textContent = typeof feature.properties?.zone_name === "string" ? feature.properties.zone_name : "高风险海区";
        content.appendChild(title);
        const metadata = [feature.properties?.source, feature.properties?.source_document, feature.properties?.effective_date]
          .filter((value): value is string => typeof value === "string" && value.trim().length > 0)
          .join(" · ");
        if (metadata) {
          const description = document.createElement("span");
          description.textContent = metadata;
          content.appendChild(description);
        }
        riskZonePopup?.setLngLat(event.lngLat).setDOMContent(content).addTo(map);
      });
      map.on("click", event => {
        if (ignoreMapDeselectRef.current) return;
        const target = event.originalEvent.target;
        if (target instanceof Element && target.closest(".vessel-marker, .port-humidity-marker, .port-humidity-popup")) return;
        setSelectedVesselId(null);
        setSelectedShipmentId(null);
      });
      map.on("error", event => {
        if (!overlaysReady && !event.error?.message.includes("404")) setMapState("error");
      });
      updateMapReadout();
    } catch {
      errorTimeout = window.setTimeout(() => setMapState("error"), 0);
    }

    return () => {
      if (errorTimeout) window.clearTimeout(errorTimeout);
      liveMarkerStore.forEach(({ marker }) => marker.remove());
      liveMarkerStore.clear();
      riskZonePopup?.remove();
      if (mapInstanceRef.current === map) mapInstanceRef.current = null;
      map?.remove();
    };
  }, []);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || mapState !== "ready") return;
    const markers = liveMarkersRef.current;
    const vesselIds = new Set(liveData.vessels.map(vessel => vessel.id));

    markers.forEach(({ marker }, vesselId) => {
      if (!vesselIds.has(vesselId)) {
        marker.remove();
        markers.delete(vesselId);
      }
    });

    liveData.vessels.forEach(vessel => {
      const existing = markers.get(vessel.id);
      if (existing) {
        existing.marker.setLngLat(vessel.position);
        existing.element.style.display = trackingModeRef.current === "live" || (trackingModeRef.current === "prediction" && vessel.id === selectedVesselId) ? "grid" : "none";
        const markerBody = existing.element.querySelector<HTMLElement>(".vessel-marker-body");
        if (markerBody) markerBody.style.transform = `rotate(${vessel.markerDirection}deg)`;
        return;
      }

      const markerElement = document.createElement("div");
      markerElement.className = "vessel-marker";
      markerElement.style.display = trackingModeRef.current === "live" || (trackingModeRef.current === "prediction" && vessel.id === selectedVesselId) ? "grid" : "none";
      markerElement.setAttribute("aria-label", `${vessel.name} vessel position`);
      markerElement.setAttribute("role", "button");
      markerElement.tabIndex = 0;
      const markerBody = createVesselMarkerBody(vessel.markerDirection);
      markerElement.appendChild(markerBody);

      const selectLiveVessel = () => {
        setVesselSearchQuery("");
        setVesselSearchResult(null);
        setVesselSearchError(null);
        setAddVesselError(null);
        setPreviewedSearchVesselId(null);
        setSelectedVesselId(vessel.id);
        setActiveInfoTab("overview");
      };
      markerElement.addEventListener("click", event => {
        event.stopPropagation();
        ignoreMapDeselectRef.current = true;
        window.setTimeout(() => { ignoreMapDeselectRef.current = false; }, 0);
        selectLiveVessel();
      });
      markerElement.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          event.stopPropagation();
          selectLiveVessel();
        }
      });

      const marker = new maplibregl.Marker({ element: markerElement, anchor: "center" }).setLngLat(vessel.position).addTo(map);
      markers.set(vessel.id, { marker, element: markerElement });
    });

    if (trackingModeRef.current === "live" && liveData.vessels.length === 1) {
      map.flyTo({ center: liveData.vessels[0].position, zoom: Math.max(map.getZoom(), 7), duration: 650 });
    } else if (trackingModeRef.current === "live" && liveData.vessels.length > 1) {
      const bounds = liveData.vessels.reduce(
        (currentBounds, vessel) => currentBounds.extend(vessel.position),
        new maplibregl.LngLatBounds(liveData.vessels[0].position, liveData.vessels[0].position),
      );
      map.fitBounds(bounds, { padding: 80, maxZoom: 8, duration: 650 });
    }
  }, [liveData.vessels, mapState, selectedVesselId]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    searchPreviewMarkerRef.current?.remove();
    searchPreviewMarkerRef.current = null;
    if (!map || mapState !== "ready" || trackingMode !== "live" || previewedSearchVesselId !== vesselSearchResult?.id || !vesselSearchResult.latestPosition) return;

    const markerElement = document.createElement("div");
    markerElement.className = "vessel-search-preview-marker";
    markerElement.setAttribute("aria-label", `${vesselSearchResult.name} search preview position`);
    const marker = new maplibregl.Marker({ element: markerElement, anchor: "center" })
      .setLngLat(vesselSearchResult.latestPosition.position)
      .addTo(map);
    searchPreviewMarkerRef.current = marker;

    return () => {
      marker.remove();
      if (searchPreviewMarkerRef.current === marker) searchPreviewMarkerRef.current = null;
    };
  }, [mapState, previewedSearchVesselId, trackingMode, vesselSearchResult]);

  useEffect(() => {
    if (!pendingSelectedVesselId || liveData.status !== "ready") return;
    const vessel = liveData.vessels.find(candidate => candidate.id === pendingSelectedVesselId);
    if (!vessel) return;
    const selectAfterRefresh = window.setTimeout(() => {
      setPendingSelectedVesselId(null);
      setSelectedVesselId(vessel.id);
      setActiveInfoTab("overview");
      const map = mapInstanceRef.current;
      map?.flyTo({ center: vessel.position, zoom: Math.max(map.getZoom(), 7), duration: 650 });
    }, 0);
    return () => window.clearTimeout(selectAfterRefresh);
  }, [liveData.status, liveData.vessels, pendingSelectedVesselId]);

  return (
    <section className={`map-workspace${displayedVessel ? " has-info-panel" : ""}`} aria-label="交互式海事地图工作区">
      <div ref={mapContainerRef} className="map-container" />
      {humidityMap && <PortHumidityLayer map={humidityMap} onOpenChange={setHumidityOpen} />}

      {mapState !== "ready" && (
        <div className={`map-load-state${mapState === "error" ? " error" : ""}`} role="status">
          <span className="status-dot" />
          {mapState === "loading" ? "正在初始化地图" : "底图暂不可用"}
        </div>
      )}

      {trackingMode === "prediction" && (
        <form
          className="map-vessel-search"
          role="search"
          onSubmit={event => {
            event.preventDefault();
            selectSearchedVessel();
          }}
        >
          <span className="map-vessel-search-icon" aria-hidden="true">⌕</span>
          <input
            value={vesselSearchQuery}
            onChange={event => setVesselSearchQuery(event.target.value)}
            placeholder="搜索船名、IMO 或 MMSI"
            aria-label="搜索船舶"
          />
          {searchedVessel && (
            <button type="button" className="map-vessel-search-result" onClick={selectSearchedVessel}>
              <span><strong>{searchedVessel.name}</strong><small>IMO {searchedVessel.imo ?? "—"}</small></span>
              <small>{searchedVessel.aisStatus}</small>
            </button>
          )}
        </form>
      )}

      <aside className={`tracking-mode-controller${humidityOpen ? " humidity-collapsed" : ""}`} aria-label="跟踪模式控制器">
        <span className="tracking-controller-title">跟踪模式{humidityOpen ? ` · ${trackingMode === "live" ? "实时" : "预测"}` : ""}</span>
        <div className="tracking-mode-segments" role="group" aria-label="选择跟踪模式">
          {TRACKING_MODES.map(mode => (
            <button
              key={mode.id}
              type="button"
              aria-pressed={trackingMode === mode.id}
              className={trackingMode === mode.id ? "active" : ""}
              onClick={() => changeTrackingMode(mode.id)}
            >
              {mode.label}
            </button>
          ))}
        </div>

        {trackingMode === "live" ? (
          <div className="tracking-live-data" aria-live="polite">
            {(liveData.status === "idle" || liveData.status === "loading") && <div className="tracking-live-message"><span className="status-dot" /><strong>正在加载船舶…</strong><small>FASTAPI 实时数据</small></div>}
            {liveData.status === "error" && <div className="tracking-live-message error"><strong>无法加载船舶数据。</strong><small>{liveData.error}</small><button type="button" onClick={liveData.retry}>重试</button></div>}
            {liveData.status === "ready" && (
              <>
                {liveData.issues.length > 0 && <div className="tracking-live-issues"><span>{liveData.issues.length} 艘无有效实时船位</span><small>缺失或超过 24 小时的 AIS 船位不会作为实时位置显示</small></div>}
                <LiveVesselList
                  vessels={liveData.vessels}
                  insuredVessels={insuranceData.vessels}
                  insuranceStatus={insuranceData.status}
                  selectedVesselId={selectedVesselId}
                  searchQuery={vesselSearchQuery}
                  searchResult={vesselSearchResult}
                  searchLoading={vesselSearchLoading}
                  searchError={vesselSearchError}
                  adding={addingVessel}
                  addError={addVesselError}
                  stoppingVesselId={stoppingVesselId}
                  stopError={stopVesselError}
                  onSearchQueryChange={updateLiveSearchQuery}
                  onSearchDatabase={searchVesselDatabase}
                  onLocateSearchResult={locateSearchResult}
                  onAddSearchResult={addSearchResultToTracking}
                  onSelectVessel={selectLiveVesselFromList}
                  onStopVessel={stopLiveTracking}
                />
              </>
            )}
          </div>
        ) : (
          <NavigationPredictionBrowser
            voyages={voyagesData.items}
            status={voyagesData.status}
            error={voyagesData.error}
            selectedShipmentId={selectedShipmentId}
            onSelectShipment={setSelectedShipmentId}
            onRetry={voyagesData.retry}
          />
        )}
      </aside>

      {displayedVessel && (
        <VesselInfoPanel vessel={displayedVessel} activeTab={activeInfoTab} onTabChange={setActiveInfoTab} onClose={() => { setSelectedVesselId(null); setSelectedShipmentId(null); }} />
      )}

      <footer className="map-statusbar">
        <div><span className="status-dot" />实时地图</div>
        <span ref={mapThemeLabelRef}>OPENFREEMAP · POSITRON</span>
        <span>缩放 <span ref={zoomRef}>6.2</span></span>
        <span><span ref={latitudeRef}>29.35°N</span>&nbsp;&nbsp; <span ref={longitudeRef}>124.10°E</span></span>
        <span className="map-spacer" />
        <span>{trackingMode === "live" ? liveData.status === "ready" ? "FASTAPI 实时数据" : liveData.status === "error" ? "实时数据不可用" : "正在加载实时数据" : predictionData.status === "ready" ? "FASTAPI 预测数据" : predictionData.status === "error" ? "预测数据不可用" : "等待选择真实船舶"}</span>
      </footer>
    </section>
  );
}
