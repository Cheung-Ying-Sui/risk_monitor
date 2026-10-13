import { useMemo, useState } from "react";
import type { PortCallType, VoyageHistoryItem, VoyagePortCall } from "@/types/voyage-history";

const dateFormatter = new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", timeZone: "UTC" });
const detailDateFormatter = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: "UTC" });

function formatDate(value?: string, detailed = false) {
  if (!value) return "进行中";
  return (detailed ? detailDateFormatter : dateFormatter).format(new Date(value));
}

function portCallLabel(type: PortCallType) {
  return ({ origin: "始发港", destination: "目的港", scheduled: "计划挂靠", unscheduled: "临时挂靠" } as Record<string, string>)[type] ?? type;
}

function intermediatePortCallCount(voyage: VoyageHistoryItem) {
  return Math.max(voyage.portCalls.length - 2, 0);
}

function VoyageHistoryListItem({ voyage, selected, onSelect }: { voyage: VoyageHistoryItem; selected: boolean; onSelect: () => void }) {
  const portCallCount = intermediatePortCallCount(voyage);

  return (
    <button type="button" className={`voyage-history-item${selected ? " selected" : ""}`} onClick={onSelect}>
      <div className="voyage-history-route"><strong>{voyage.originPort}</strong><span>→</span><strong>{voyage.destinationPort}</strong></div>
      <div className="voyage-history-dates"><span>{formatDate(voyage.startedAt)} – {formatDate(voyage.completedAt)}</span><small>{voyage.status === "completed" ? "已完成" : voyage.status === "in_progress" ? "进行中" : voyage.status}</small></div>
      <div className="voyage-history-meta"><span>{portCallCount ? `${portCallCount} 次中途挂靠` : "直航"}</span><span>{voyage.totalDistanceNm?.toLocaleString()} 海里</span></div>
    </button>
  );
}

function PortCallList({ portCalls }: { portCalls: VoyagePortCall[] }) {
  return (
    <ol className="voyage-port-call-list">
      {portCalls.map((portCall, index) => (
        <li key={portCall.id} className={portCall.type === "unscheduled" ? "unscheduled" : ""}>
          <span className="port-call-sequence">{index + 1}</span>
          <div><strong>{portCall.portName}</strong><small>{portCall.countryCode}</small></div>
          <span className={`port-call-type ${portCall.type}`}>{portCallLabel(portCall.type)}</span>
        </li>
      ))}
    </ol>
  );
}

function VoyageDetail({ voyage, onBack }: { voyage: VoyageHistoryItem; onBack: () => void }) {
  return (
    <div className="voyage-history-detail">
      <button type="button" className="voyage-history-back" onClick={onBack} aria-label="返回航程历史">
        <span className="voyage-history-back-arrow" aria-hidden="true">←</span>
        <span>航程历史</span>
      </button>
      <div className="voyage-detail-route"><strong>{voyage.originPort}</strong><span>→</span><strong>{voyage.destinationPort}</strong></div>
      <div className="voyage-detail-summary">
        <span>{formatDate(voyage.startedAt, true)}</span>
        <span>{formatDate(voyage.completedAt, true)}</span>
        <small>{voyage.legs.length} 个航段 · 完整航程</small>
      </div>
      <span className="voyage-detail-section-title">港口挂靠</span>
      <PortCallList portCalls={voyage.portCalls} />
    </div>
  );
}

export function VoyageHistoryBrowser({ voyages, selectedVoyageId, onSelectVoyage }: { voyages: VoyageHistoryItem[]; selectedVoyageId: string | null; onSelectVoyage: (voyageId: string) => void }) {
  const [query, setQuery] = useState("");
  const [detailVoyageId, setDetailVoyageId] = useState<string | null>(null);
  const detailVoyage = voyages.find(voyage => voyage.id === detailVoyageId);
  const filteredVoyages = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) return voyages;
    return voyages.filter(voyage =>
      [voyage.originPort, voyage.destinationPort, ...voyage.portCalls.map(portCall => portCall.portName)]
        .some(value => value.toLowerCase().includes(normalizedQuery)),
    );
  }, [query, voyages]);

  if (detailVoyage) return <VoyageDetail voyage={detailVoyage} onBack={() => setDetailVoyageId(null)} />;

  return (
    <div className="voyage-history-browser">
      <span className="voyage-history-heading">航程历史</span>
      <label className="voyage-history-search">
        <span className="sr-only">搜索航程</span>
        <input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索航程…" />
      </label>
      <span className="voyage-history-year">2026</span>
      <div className="voyage-history-list">
        {filteredVoyages.map(voyage => (
          <VoyageHistoryListItem
            key={voyage.id}
            voyage={voyage}
            selected={voyage.id === selectedVoyageId}
            onSelect={() => {
              onSelectVoyage(voyage.id);
              setDetailVoyageId(voyage.id);
            }}
          />
        ))}
        {!filteredVoyages.length && <span className="voyage-history-empty">没有符合搜索条件的航程。</span>}
      </div>
    </div>
  );
}
