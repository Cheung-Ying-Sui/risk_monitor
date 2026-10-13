"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import * as maplibregl from "maplibre-gl";
import { fetchHumidityProfile, fetchWeatherPorts, type HumidityProfile, type WeatherPort } from "@/services/port-humidity";
import PortHumidityCharts from "./port-humidity-charts";
import PortArrivalsList from "./port-arrivals";

const ENGLISH_NAMES: Record<string, string> = {
  CN_YINGKOU: "YINGKOU", CN_TIANJIN: "TIANJIN", CN_QINGDAO: "QINGDAO",
  CN_LIANYUNGANG: "LIANYUNGANG", CN_ZHANJIANG: "ZHANJIANG", CN_FANGCHENGGANG: "FANGCHENGGANG",
};
const PILOT_CODES = new Set(Object.keys(ENGLISH_NAMES));
const HUMIDITY_THRESHOLD = 85;

const METRIC_DESCRIPTIONS = {
  mean_rh: "历史同期有效小时的平均相对湿度，用于了解港口的常态湿度水平。",
  p90_rh: "历史同期相对湿度的第 90 百分位，帮助观察偏高湿度的水平。",
  exceedance: "历史同期有效小时中，RH 达到或超过 85% 的占比；不代表未来停工概率。",
  event_mean: "历史同期连续至少 3 小时高湿度事件的平均持续时间。",
  event_p90: "高湿度事件持续时间的第 90 百分位，用于观察较长事件。",
  events_per_year: "历史同期每个有效年份平均发生的合格高湿度事件次数。",
} as const;

function todayInShanghai() {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
  const value = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return `${value.year}-${value.month}-${value.day}`;
}

function fmt(value: number | null | undefined, unit = "") {
  return value == null ? "—" : `${value.toFixed(1)}${unit}`;
}

function ProfilePopup({ port }: { port: WeatherPort }) {
  const [etaDate, setEtaDate] = useState(todayInShanghai);
  const [profile, setProfile] = useState<HumidityProfile | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [retry, setRetry] = useState(0);
  const requestRef = useRef(0);
  const validDate = /^\d{4}-\d{2}-\d{2}$/.test(etaDate) && !Number.isNaN(Date.parse(`${etaDate}T00:00:00Z`));
  useEffect(() => {
    const sequence = ++requestRef.current;
    if (!validDate) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      fetchHumidityProfile(port.port.port_code, etaDate, "", HUMIDITY_THRESHOLD, controller.signal)
        .then(data => { if (sequence === requestRef.current) { setProfile(data); setStatus("ready"); } })
        .catch(error => { if (sequence === requestRef.current && error.name !== "AbortError") setStatus("error"); });
    }, 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [port.port.port_code, etaDate, retry, validDate]);

  const showLoading = validDate && status === "loading";
  const metrics = profile?.metrics;
  const values = [
    { id: "mean_rh", label: "平均 RH", value: fmt(metrics?.mean_rh, "%") },
    { id: "p90_rh", label: "P90 RH", value: fmt(metrics?.p90_rh, "%") },
    { id: "exceedance", label: "RH≥85% 占比", value: fmt(metrics?.exceedance_fraction == null ? null : metrics.exceedance_fraction * 100, "%") },
    { id: "event_mean", label: "平均持续", value: fmt(metrics?.event_mean_hours, "小时") },
    { id: "event_p90", label: "P90 持续", value: fmt(metrics?.event_p90_hours, "小时") },
    { id: "events_per_year", label: "年均事件", value: fmt(metrics?.events_per_year, "次/年") },
  ] as const;
  const grid = profile?.provenance.grid_coordinates;
  const location = port.analysis_location;

  return <div className="port-humidity-popup-content" onClick={event => event.stopPropagation()}>
    <div className="port-humidity-heading">
      <strong>{port.port.name_zh} / {ENGLISH_NAMES[port.port.port_code]}</strong>
      <span>历史湿度暴露画像 · {location.verification_status === "approximate" ? "近似分析点" : "已核实分析点"}</span>
      <small>{location.name} · {port.coverage_start_utc ? `数据质量：${port.data_quality_status}` : "暂无历史数据"}</small>
    </div>
    <div className="port-humidity-fields">
      <label>ETA 日期<input type="date" value={etaDate} onChange={event => { setEtaDate(event.target.value); setProfile(null); setStatus("loading"); }} /></label>
      <div className="port-humidity-fixed-threshold"><span>RH 阈值</span><strong>{HUMIDITY_THRESHOLD}%（固定）</strong></div>
    </div>
    <div className="port-humidity-window">同期窗口：每年 ETA 月日 ±7 天 · 2016–2025
      {profile?.scope.date_ranges[0] && ` · ${profile.scope.date_ranges[0].start.slice(5)}—${profile.scope.date_ranges[0].end.slice(5)}`}
    </div>
    {!validDate ? <p className="port-humidity-alert">请输入有效 ETA 日期。</p>
      : showLoading ? <p role="status" className="port-humidity-message">正在计算历史样本…</p>
      : status === "error" ? <p className="port-humidity-alert">查询失败。<button type="button" onClick={() => { setStatus("loading"); setRetry(value => value + 1); }}>重试</button></p>
      : profile && profile.quality.valid_year_count === 0 ? <p className="port-humidity-alert">暂无有效历史样本；所选日期的同期窗口未达到 95% 覆盖要求。</p> : null}
    {status === "ready" && profile && <>
      <div className="port-humidity-metrics">{values.map(({ id, label, value }) => <div
        key={id} className="port-humidity-metric" tabIndex={0}
        aria-label={`${label}：${value}。${METRIC_DESCRIPTIONS[id]}`}
      ><span>{label}</span><strong>{value}</strong><span className="port-humidity-metric-help" role="tooltip">{METRIC_DESCRIPTIONS[id]}</span></div>)}</div>
    </>}
    {validDate && <>
      <PortHumidityCharts key={etaDate} portCode={port.port.port_code} etaDate={etaDate} threshold={HUMIDITY_THRESHOLD} />
      <PortArrivalsList key={port.port.port_code} portCode={port.port.port_code} />
    </>}
    {status === "ready" && profile && <>
      {profile.quality.valid_year_count > 0 && metrics?.event_mean_hours == null && <small>—：同期没有可确认的合格高湿度事件。</small>}
      <div className="port-humidity-quality">
        <span>有效年份 {profile.quality.valid_year_count} / 10 · 有效小时 {profile.quality.valid_hour_count} / {profile.quality.expected_hour_count}</span>
        <span>来源：Open-Meteo ERA5 · 版本 {profile.provenance.method_version}</span>
        {grid && <span title={profile.provenance.coordinate_source ?? ""}>请求位置 {location.requested_latitude?.toFixed(3)}, {location.requested_longitude?.toFixed(3)} · ERA5 网格 {grid.latitude.toFixed(3)}, {grid.longitude.toFixed(3)}</span>}
        {profile.quality.censored_event_count > 0 && <span>删失事件 {profile.quality.censored_event_count} 个，未计入事件统计</span>}
        {profile.quality.warnings.map(warning => <span className="warning" key={warning}>{warning}</span>)}
      </div>
    </>}
    <p className="port-humidity-disclaimer">{location.verification_status === "approximate" ? "示范分析位置，并非码头实测；" : ""}历史气象暴露频率 ≠ 实际停工、货损或未来发生概率。事件按起始时间归属；85% 非正式停工限值。</p>
  </div>;
}

export default function PortHumidityLayer({ map, onOpenChange }: {
  map: maplibregl.Map; onOpenChange: (open: boolean) => void;
}) {
  const [ports, setPorts] = useState<WeatherPort[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [selected, setSelected] = useState<WeatherPort | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const popupContainer = useMemo(() => selected && typeof document !== "undefined" ? document.createElement("div") : null, [selected]);

  useEffect(() => {
    const controller = new AbortController();
    let retryTimer: number | undefined;
    fetchWeatherPorts(controller.signal)
      .then(rows => {
        const pilotPorts = rows.filter(row => PILOT_CODES.has(row.port.port_code) && row.analysis_location.is_primary);
        if (pilotPorts.length === 0) throw new Error("未取得试点港口数据");
        setPorts(pilotPorts);
        setLoadError(null);
      })
      .catch(error => {
        if (controller.signal.aborted) return;
        setLoadError(error instanceof Error ? error.message : "气象数据服务暂不可用");
        retryTimer = window.setTimeout(() => setRetry(value => value + 1), 5000);
      });
    return () => { controller.abort(); if (retryTimer) window.clearTimeout(retryTimer); };
  }, [retry]);

  const locatedPorts = useMemo(() => ports.filter(row =>
    Number.isFinite(row.analysis_location.requested_latitude) && Number.isFinite(row.analysis_location.requested_longitude)), [ports]);

  useEffect(() => {
    const markers = locatedPorts.map(port => {
      const element = document.createElement("button");
      element.type = "button";
      element.className = "port-humidity-marker";
      element.setAttribute("aria-label", `${port.port.name_zh}湿度画像`);
      element.title = `${port.port.name_zh} · ${port.coverage_start_utc ? "有历史数据" : "暂无历史数据"}`;
      const tooltip = document.createElement("span");
      tooltip.className = "port-humidity-tooltip";
      tooltip.textContent = port.port.name_zh;
      tooltip.setAttribute("aria-hidden", "true");
      element.appendChild(tooltip);
      element.addEventListener("click", event => { event.stopPropagation(); setSelected(port); });
      return new maplibregl.Marker({ element, anchor: "bottom" })
        .setLngLat([port.analysis_location.requested_longitude!, port.analysis_location.requested_latitude!]).addTo(map);
    });
    return () => { markers.forEach(marker => marker.remove()); };
  }, [map, locatedPorts]);

  useEffect(() => {
    if (!selected || !popupContainer) return;
    const popup = new maplibregl.Popup({ className: "port-humidity-popup", maxWidth: "520px", offset: 18, closeOnClick: false })
      .setLngLat([selected.analysis_location.requested_longitude!, selected.analysis_location.requested_latitude!])
      .setDOMContent(popupContainer).addTo(map);
    popupRef.current = popup;
    onOpenChange(true);
    popup.on("close", () => {
      if (popupRef.current === popup) {
        setSelected(null);
        onOpenChange(false);
      }
    });
    return () => { if (popupRef.current === popup) popupRef.current = null; popup.remove(); };
  }, [map, selected, popupContainer, onOpenChange]);

  return <>
    {loadError && <div className="port-humidity-load-error" role="alert">港口湿度数据暂不可用：{loadError}；正在自动重试。<button onClick={() => { setLoadError(null); setRetry(value => value + 1); }} type="button">立即重试</button></div>}
    {popupContainer && selected && createPortal(<ProfilePopup key={selected.analysis_location.id} port={selected} />, popupContainer)}
  </>;
}
