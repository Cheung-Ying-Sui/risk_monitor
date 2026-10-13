"use client";

import { formatCoordinate, formatObservedAt } from "@/components/vessel-tracking/vessel-presentation";
import type { VesselSearchResult } from "@/types/vessels";

interface VesselSearchPreviewProps {
  result: VesselSearchResult;
  adding: boolean;
  addError: string | null;
  onLocate: () => void;
  onAdd: () => void;
}

export function VesselSearchPreview({ result, adding, addError, onLocate, onAdd }: VesselSearchPreviewProps) {
  const latestPosition = result.latestPosition;
  const position = latestPosition?.position;

  return (
    <section className="vessel-search-preview" aria-label={`${result.name} 船舶搜索结果`}>
      <header>
        <span>已找到船舶</span>
        <strong className={result.isTracked ? "tracked" : "untracked"}>{result.isTracked ? "已跟踪" : "未跟踪"}</strong>
      </header>
      <h3>{result.name}</h3>
      <div className="vessel-search-preview-identifiers">
        <span><small>IMO</small><strong>{result.imo ?? "—"}</strong></span>
        <span><small>MMSI</small><strong>{result.mmsi ?? "—"}</strong></span>
      </div>
      {position ? (
        <div className="vessel-search-preview-position">
          <span>纬度 {formatCoordinate(position[1], "latitude")}</span>
          <span>经度 {formatCoordinate(position[0], "longitude")}</span>
          <small>最近 AIS {formatObservedAt(latestPosition.observedAt)}</small>
        </div>
      ) : (
        <p className="vessel-search-preview-no-position">暂无最新 AIS 船位。</p>
      )}
      {addError && <p className="vessel-search-action-error" role="alert">{addError}</p>}
      <footer>
        <button type="button" onClick={onLocate} disabled={!position}>定位</button>
        <button type="button" className="primary" onClick={onAdd} disabled={result.isTracked || adding}>
          {adding ? "正在添加…" : result.isTracked ? "已跟踪" : "加入跟踪"}
        </button>
      </footer>
    </section>
  );
}
