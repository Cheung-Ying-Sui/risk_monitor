import { CATEGORY_PRESENTATION, formatOccurredAt, PRECISION_LABELS } from "./event-presentation";
import { hasCoordinates } from "@/services/ukmto";
import type { MaritimeIntelligenceEvent } from "@/types/maritime-intelligence";
import { CategoryIcon } from "./category-icon";

export function EventDetailPanel({ event, onClose }: { event: MaritimeIntelligenceEvent; onClose: () => void }) {
  const category = CATEGORY_PRESENTATION[event.category];
  return (
    <aside className="intelligence-detail" aria-label={`${event.title}事件详情`}>
      <header className="intelligence-detail-header">
        <div className="intelligence-detail-heading"><span>事件详情</span><button type="button" onClick={onClose} aria-label="关闭事件详情">×</button></div>
        <h2>{event.title}</h2>
        <div><span className="intelligence-detail-category"><i className={`intelligence-category-symbol category-${event.category}`}><CategoryIcon category={event.category} /></i>{category.label}</span><strong>UKMTO</strong></div>
      </header>
      <div className="intelligence-detail-scroll">
        <section className="intelligence-detail-facts">
          <div><span>事件编号</span><strong>{event.id}</strong></div>
          <div><span>地点</span><strong>{event.locationName}</strong></div>
          <div><span>发生时间</span><strong>{formatOccurredAt(event.occurredAt)}</strong></div>
          <div><span>发布时间</span><strong>{formatOccurredAt(event.publishedAt)}</strong></div>
          <div><span>位置精度</span><strong>{PRECISION_LABELS[event.locationPrecision || "unknown"] || "精度未知"}</strong></div>
          <div><span>经纬度</span><strong>{hasCoordinates(event) ? `${event.latitude.toFixed(5)}, ${event.longitude.toFixed(5)}` : "来源未提供有效坐标"}</strong></div>
          {event.vesselType && <div><span>船型</span><strong>{event.vesselType}</strong></div>}
          <div><span>最近采集</span><strong>{formatOccurredAt(event.lastSeenAt)}</strong></div>
        </section>
        <section className="intelligence-detail-section">
          <span>UKMTO 原始报告</span>
          <p className="intelligence-report-text">{event.summary}</p>
        </section>
        <section className="intelligence-detail-section">
          <span>信息来源</span>
          <div className="intelligence-source-list">
            {event.sources.map(source => source.url && /^https:\/\/(www\.)?ukmto\.org\//i.test(source.url)
              ? <a key={source.id} href={source.url} target="_blank" rel="noopener noreferrer">查看 {source.name} 原文 ↗</a>
              : <span key={source.id}>{source.name}</span>)}
          </div>
          <p>UKMTO / Crown copyright。事件位置不代表船舶实时位置。</p>
        </section>
      </div>
    </aside>
  );
}
