import { formatObservedAt } from "@/components/vessel-tracking/vessel-presentation";
import type { InsuranceVoyagePrediction } from "@/types/navigation";

const STATUS: Record<InsuranceVoyagePrediction["status"], string> = {
  eligible: "可预测", estimated: "承保航程估算", ais_stale: "AIS 过期，暂停预测",
  position_unavailable: "暂无有效 AIS / 船舶尚未关联跟踪", destination_unresolved: "目的港未解析，待核实",
  destination_mismatch: "申报与 AIS 目的港冲突，待核实", route_pending: "等待生成相容航线",
  voyage_completed: "航程已结束（MVP 推定）", ambiguous_active_shipments: "同船多票目的港不一致或不明确，待核实",
  needs_review: "路线进度证据异常，待核实",
};
const WARNINGS: Record<string, string> = {
  ais_fallback_needs_review: "按 AIS 目的地估算，待核实",
  ais_destination_unverified: "AIS 目的地缺失或未识别，使用申报目的港",
  multiple_declared_destinations_need_review: "申报包含多个目的港，无法确定本票最终目的港",
  declaration_ais_destination_mismatch: "请核实申报与 AIS 目的地，不自动覆盖申报",
  route_projection_ambiguous: "当前位置对应多个航段，暂停进度与 ETA",
  route_progress_jump: "进度发生异常跳跃/回退，暂停进度与 ETA",
  route_generation_or_activation_failed: "航线生成或保存未完成，将重试",
};

export function NavigationPredictionBrowser({ voyages, status, error, selectedShipmentId, onSelectShipment, onRetry }: {
  voyages: InsuranceVoyagePrediction[];
  status: "loading" | "ready" | "error";
  error: string | null;
  selectedShipmentId: string | null;
  onSelectShipment: (shipmentId: string | null) => void;
  onRetry: () => void;
}) {
  const selected = voyages.find(v => v.shipment_id === selectedShipmentId) ?? null;
  return <div className="voyage-history-browser prediction-browser" aria-live="polite">
    <span className="voyage-history-heading">活动承保航程预测</span>
    {status === "loading" && <div className="tracking-live-message"><strong>正在核验承保航程…</strong></div>}
    {status === "error" && <div className="tracking-live-message error"><strong>无法加载承保预测</strong><small>{error}</small></div>}
    {status === "ready" && <>
      <label className="voyage-history-search"><span className="sr-only">选择承保航程</span>
        <select value={selected?.shipment_id ?? ""} onChange={e => onSelectShipment(e.target.value || null)} disabled={!voyages.length}>
          <option value="">{voyages.length ? "选择投保申报航程" : "暂无活动承保航程"}</option>
          {voyages.map(v => <option key={v.shipment_id} value={v.shipment_id}>{v.declaration_number} · {v.vessel_name ?? v.imo ?? "船舶待核实"} · {v.discharge_port_raw ?? "目的港待核实"}</option>)}
        </select>
      </label>
      {selected && <div className="tracking-layer-status">
        <strong>{selected.declaration_number} · {selected.vessel_name}</strong>
        <small>{STATUS[selected.status]}</small>
        <div><span>标识</span><small>IMO {selected.imo ?? "—"} / MMSI {selected.mmsi ?? "—"}</small></div>
        <div><span>申报航程</span><small>{selected.loading_port_raw ?? "—"} → {selected.discharge_port_raw ?? "待补"}</small></div>
        <div><span>AIS 目的地</span><small>{selected.ais_destination_raw ?? "—"}</small></div>
        <div><span>ETD</span><small>{selected.etd ? formatObservedAt(selected.etd) : "—"}</small></div>
        <div><span>最新 AIS</span><small>{selected.latest_ais_at ? formatObservedAt(selected.latest_ais_at) : "—"}</small></div>
        {selected.destination_source === "ais_fallback" && <strong>按 AIS 目的地估算，待核实</strong>}
        {selected.status === "estimated" && selected.prediction && <>
          <div><span>预测目的港</span><small>{selected.destination_normalized ?? "—"}</small></div>
          <div><span>路线版本</span><small>v{selected.route_version ?? "—"}</small></div>
          <div><span>航程进度</span><small>{selected.progress === null ? "—" : (selected.progress*100).toFixed(1)+"%"}</small></div>
          <div><span>剩余距离</span><small>{selected.remaining_distance_nm?.toFixed(1) ?? "—"} NM</small></div>
          <div><span>预计到达</span><small>{selected.eta ? formatObservedAt(selected.eta) : "暂不可估算"}</small></div>
          <div><span>置信度</span><small>{selected.confidence === null ? "—" : (selected.confidence*100).toFixed(1)+"%"}</small></div>
        </>}
        {selected.warnings.map(w => <small key={w}>{WARNINGS[w] ?? w}</small>)}
      </div>}
    </>}
    <button type="button" onClick={onRetry}>刷新承保航程</button>
    <small className="voyage-history-empty">到港停泊后启动的结束状态仅为 MVP 推定，不是卸货证明或法律保险责任结论。</small>
  </div>;
}
