import { CATEGORY_PRESENTATION, formatRelativeTime, UKMTO_CATEGORIES } from "./event-presentation";
import type { UKMTOIncidentType, MaritimeIntelligenceEvent } from "@/types/maritime-intelligence";
import type { DeclaredVessel } from "@/types/insurance";
import type { InsuredLiveVessel } from "@/lib/insured-vessels";
import { CategoryIcon } from "./category-icon";

export type IntelligenceFilter = "all" | UKMTOIncidentType;
export type IntelligenceTimeRange = "all" | "7d" | "30d" | "custom";

function positionLabel(value: number, positive: string, negative: string) {
  return `${Math.abs(value).toFixed(3)}°${value >= 0 ? positive : negative}`;
}

function observedAtLabel(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "时间未知" : `${date.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })}（北京时间）`;
}

function awaitingPositionLabel(vessel: DeclaredVessel, trackingStatus: string) {
  if (trackingStatus === "error") return "船位服务暂不可用";
  if (trackingStatus === "loading") return "正在同步 AIS 船位…";
  if (vessel.tracking_status === "stale_position") return "AIS 船位超过 24 小时，暂不显示在地图";
  if (vessel.tracking_status === "awaiting_position") return "已开始跟踪，等待首个 AIS 船位";
  if (vessel.tracking_status === "not_tracking" || vessel.tracking_status === "awaiting_imo_match") return "尚未建立有效 AIS 跟踪";
  return "暂无 24 小时内的有效 AIS 船位";
}

const FILTERS: Array<{ id: IntelligenceFilter; label: string }> = [
  { id: "all", label: "全部" },
  ...UKMTO_CATEGORIES.map(id => ({ id, label: CATEGORY_PRESENTATION[id].label })),
];

function IntelligenceEventItem({ event, selected, onSelect }: { event: MaritimeIntelligenceEvent; selected: boolean; onSelect: () => void }) {
  const category = CATEGORY_PRESENTATION[event.category];
  return (
    <button type="button" className={`intelligence-event-item${selected ? " selected" : ""}`} onClick={onSelect} aria-pressed={selected}>
      <span className="intelligence-event-classification">
        <span className={`intelligence-category-symbol category-${event.category}`} aria-hidden="true"><CategoryIcon category={event.category} /></span>
        <strong>UKMTO</strong>
        <span>·</span>
        <span>{category.label.toUpperCase()}</span>
      </span>
      <span className="intelligence-event-title">{event.title}</span>
      <span className="intelligence-event-meta">
        <span>{event.locationName}</span>
        <small>发布于 {formatRelativeTime(event.publishedAt)} · {event.latitude === null || event.longitude === null ? "暂无坐标" : "来源坐标"}</small>
      </span>
    </button>
  );
}

export function IntelligenceFeed({ events, insuredVessels, insuredLiveVessels, insuranceStatus, trackingStatus, activeFilter, timeRange, customStartDate, customEndDate, selectedEventId, selectedVesselId, onSelectVessel, onFilterChange, onTimeRangeChange, onCustomStartDateChange, onCustomEndDateChange, onSelectEvent, loading, error, onRefresh }: {
  events: MaritimeIntelligenceEvent[];
  insuredVessels: DeclaredVessel[];
  insuredLiveVessels: InsuredLiveVessel[];
  insuranceStatus: "loading" | "ready" | "error";
  trackingStatus: "idle" | "loading" | "ready" | "error";
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  activeFilter: IntelligenceFilter;
  timeRange: IntelligenceTimeRange;
  customStartDate: string;
  customEndDate: string;
  selectedEventId: string | null;
  selectedVesselId: string | null;
  onSelectVessel: (vesselId: string | null) => void;
  onFilterChange: (filter: IntelligenceFilter) => void;
  onTimeRangeChange: (range: IntelligenceTimeRange) => void;
  onCustomStartDateChange: (date: string) => void;
  onCustomEndDateChange: (date: string) => void;
  onSelectEvent: (eventId: string) => void;
}) {
  return (
    <aside className="intelligence-feed" aria-label="海事情报动态">
      <header className="intelligence-feed-header">
        <span>海事情报</span>
        <div><strong>近期事件</strong><small>UKMTO 官方报告</small></div>
      </header>
      <section className="intelligence-insured-vessels" aria-label="投保申报船舶">
        <strong>已投保船舶 · AIS 船位</strong>
        {insuranceStatus === "loading" && <small>正在读取保单管理数据…</small>}
        {insuranceStatus === "error" && <small>暂时无法核验投保申报数据。</small>}
        {insuranceStatus === "ready" && !insuredVessels.length && <small>暂无有效投保申报船舶。</small>}
        {insuranceStatus === "ready" && insuredVessels.map(vessel => {
          const live = insuredLiveVessels.find(item => item.declaration === vessel)?.vessel;
          const details = <><span className="intelligence-insured-vessel-name">{vessel.vessel_name}</span>
            <small>IMO {vessel.imo_number ?? "待补"} · {vessel.declaration_number}</small>
            {live ? <><small className="intelligence-insured-position">{positionLabel(live.position[1], "N", "S")} · {positionLabel(live.position[0], "E", "W")}</small>
              <small>最近 AIS：{observedAtLabel(live.observedAt)}</small></>
              : <small>{awaitingPositionLabel(vessel, trackingStatus)}</small>}</>;
          return live ? <button key={vessel.imo_number ?? vessel.vessel_name} type="button"
            className={`intelligence-insured-vessel-row${selectedVesselId === live.id ? " selected" : ""}`}
            onClick={() => onSelectVessel(live.id)} aria-pressed={selectedVesselId === live.id}>
            {details}
          </button> : <div key={vessel.imo_number ?? vessel.vessel_name} className="intelligence-insured-vessel-row">{details}</div>;
        })}
      </section>
      <div className="intelligence-time-filter">
        <label htmlFor="intelligence-time-range">发布时间（UTC）</label>
        <select id="intelligence-time-range" value={timeRange} onChange={event => onTimeRangeChange(event.target.value as IntelligenceTimeRange)}>
          <option value="all">全部时间</option>
          <option value="7d">最近 7 天</option>
          <option value="30d">最近 30 天</option>
          <option value="custom">自定义范围</option>
        </select>
        {timeRange === "custom" && (
          <div className="intelligence-custom-dates">
            <label><span>开始</span><input type="date" value={customStartDate} max={customEndDate} onChange={event => onCustomStartDateChange(event.target.value)} /></label>
            <label><span>结束</span><input type="date" value={customEndDate} min={customStartDate} onChange={event => onCustomEndDateChange(event.target.value)} /></label>
          </div>
        )}
      </div>
      <div className="intelligence-filters" role="group" aria-label="按类别筛选海事事件">
        {FILTERS.map(filter => (
          <button key={filter.id} type="button" className={activeFilter === filter.id ? "active" : ""} aria-pressed={activeFilter === filter.id} onClick={() => onFilterChange(filter.id)}>
            {filter.id !== "all" && <span className={`intelligence-filter-symbol category-${filter.id}`} aria-hidden="true"><CategoryIcon category={filter.id} /></span>}
            {filter.label}
          </button>
        ))}
      </div>
      <div className="intelligence-feed-count"><span>事件动态</span><strong>{loading ? "…" : events.length}</strong><button className="intelligence-refresh" type="button" onClick={onRefresh} disabled={loading}>刷新</button></div>
      <div className="intelligence-event-list" aria-busy={loading}>
        {loading && <p className="intelligence-empty-feed" role="status">正在加载 UKMTO 事件…</p>}
        {error && <div className="intelligence-empty-feed" role="alert"><p>{error}</p><button className="intelligence-refresh" type="button" onClick={onRefresh}>重试</button></div>}
        {events.map(event => <IntelligenceEventItem key={event.id} event={event} selected={selectedEventId === event.id} onSelect={() => onSelectEvent(event.id)} />)}
        {!loading && !error && !events.length && <p className="intelligence-empty-feed">所选类别和时间范围内没有海事事件。</p>}
      </div>
    </aside>
  );
}
