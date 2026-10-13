"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { formatAisAge, formatNullableNumber, formatObservedAt, parseVesselSearchIdentifier } from "@/components/vessel-tracking/vessel-presentation";
import { VesselSearchPreview } from "@/components/vessel-tracking/vessel-search-preview";
import { matchesInsuredVessel } from "@/lib/insured-vessels";
import type { DeclaredVessel } from "@/types/insurance";
import type { LiveVessel, VesselSearchResult } from "@/types/vessels";

interface LiveVesselListProps {
  vessels: LiveVessel[];
  insuredVessels: DeclaredVessel[];
  insuranceStatus: "loading" | "ready" | "error";
  selectedVesselId: string | null;
  searchQuery: string;
  searchResult: VesselSearchResult | null;
  searchLoading: boolean;
  searchError: string | null;
  adding: boolean;
  addError: string | null;
  stoppingVesselId: string | null;
  stopError: { vesselId: string; message: string } | null;
  onSearchQueryChange: (value: string) => void;
  onSearchDatabase: () => void;
  onLocateSearchResult: () => void;
  onAddSearchResult: () => void;
  onSelectVessel: (vesselId: string) => void;
  onStopVessel: (vesselId: string) => Promise<boolean>;
}

export function LiveVesselList({ vessels, insuredVessels, insuranceStatus, selectedVesselId, searchQuery, searchResult, searchLoading, searchError, adding, addError, stoppingVesselId, stopError, onSearchQueryChange, onSearchDatabase, onLocateSearchResult, onAddSearchResult, onSelectVessel, onStopVessel }: LiveVesselListProps) {
  const itemRefs = useRef<Map<string, HTMLLIElement>>(new Map());
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [openMenuVesselId, setOpenMenuVesselId] = useState<string | null>(null);
  const [confirmStopVesselId, setConfirmStopVesselId] = useState<string | null>(null);
  const normalizedQuery = searchQuery.trim().toLowerCase();
  const filteredVessels = useMemo(
    () => vessels.filter(vessel => !normalizedQuery || [vessel.name, vessel.imo, vessel.mmsi].some(value => value?.toLowerCase().includes(normalizedQuery))),
    [normalizedQuery, vessels],
  );
  const canSearchDatabase = filteredVessels.length === 0 && parseVesselSearchIdentifier(searchQuery) !== null;
  const withoutLivePosition = insuredVessels.filter(insured => !vessels.some(vessel => matchesInsuredVessel(vessel, insured)));

  useEffect(() => {
    if (!selectedVesselId) return;
    itemRefs.current.get(selectedVesselId)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedVesselId]);

  return (
    <section className="live-vessel-browser" aria-label="实时船舶列表">
      <header className="live-vessel-browser-header">
        <span>实时船舶</span>
        <strong>正在跟踪 {vessels.length} 艘</strong>
      </header>

      <form
        className="live-vessel-search"
        role="search"
        onSubmit={event => {
          event.preventDefault();
          if (filteredVessels.length > 0 && normalizedQuery) onSelectVessel(filteredVessels[0].id);
          else onSearchDatabase();
        }}
      >
        <span aria-hidden="true">⌕</span>
        <label className="sr-only" htmlFor="live-vessel-search-input">搜索实时船舶</label>
        <input
          ref={searchInputRef}
          id="live-vessel-search-input"
          value={searchQuery}
          onChange={event => onSearchQueryChange(event.target.value)}
          placeholder="船名、IMO 或 MMSI"
        />
        <button type="submit" aria-label="提交船舶搜索" disabled={searchLoading}>{searchLoading ? "…" : "↵"}</button>
      </form>

      {canSearchDatabase && !searchResult && (
        <button type="button" className="vessel-database-search" onClick={onSearchDatabase} disabled={searchLoading}>
          {searchLoading ? "正在搜索船舶数据库…" : "搜索船舶数据库"}
        </button>
      )}
      {searchError && <p className="vessel-search-error" role="alert">{searchError}</p>}
      {searchResult && (
        <VesselSearchPreview result={searchResult} adding={adding} addError={addError} onLocate={onLocateSearchResult} onAdd={onAddSearchResult} />
      )}

      <ul className="live-vessel-list">
        {filteredVessels.map(vessel => {
          const selected = vessel.id === selectedVesselId;
          const confirmingStop = confirmStopVesselId === vessel.id;
          const vesselIdentifier = vessel.imo && vessel.imo !== "0" ? `IMO ${vessel.imo}` : `MMSI ${vessel.mmsi ?? "—"}`;
          return (
            <li
              key={vessel.id}
              ref={element => {
                if (element) itemRefs.current.set(vessel.id, element);
                else itemRefs.current.delete(vessel.id);
              }}
              className={`${selected ? "selected " : ""}${confirmingStop ? "confirming" : ""}`.trim()}
            >
              <button
                type="button"
                className="live-vessel-select"
                aria-pressed={selected}
                onClick={() => onSelectVessel(vessel.id)}
              >
                <span className="live-vessel-item-heading">
                  <strong>{vessel.name}</strong>
                  <small>{vesselIdentifier}</small>
                </span>
                <span className="live-vessel-item-status">
                  {insuranceStatus === "ready" && <small className="insurance-origin-status">{insuredVessels.some(insured => matchesInsuredVessel(vessel, insured)) ? "投保申报" : "Demo"}</small>}
                  {insuranceStatus === "error" && <small>投保状态待核验</small>}
                  <small>{vessel.navigationStatus}</small>
                  {vessel.sog !== null && <strong>{formatNullableNumber(vessel.sog, " kn")}</strong>}
                </span>
                <span className="live-vessel-item-update" title={formatObservedAt(vessel.observedAt)}>
                  <i aria-hidden="true" />
                  AIS {formatAisAge(vessel.observedAt)}
                </span>
              </button>
              <button
                type="button"
                className="live-vessel-more"
                aria-label={`More actions for ${vessel.name}`}
                aria-expanded={openMenuVesselId === vessel.id}
                onClick={() => {
                  setConfirmStopVesselId(null);
                  setOpenMenuVesselId(current => current === vessel.id ? null : vessel.id);
                }}
              >•••</button>
              {openMenuVesselId === vessel.id && confirmStopVesselId !== vessel.id && (
                <div className="live-vessel-context-menu">
                  <button type="button" onClick={() => { onSelectVessel(vessel.id); setOpenMenuVesselId(null); }}>查看／定位</button>
                  <button type="button" className="danger" onClick={() => setConfirmStopVesselId(vessel.id)}>停止跟踪</button>
                </div>
              )}
              {confirmingStop && (
                <div className="live-vessel-stop-confirm" role="alertdialog" aria-label={`Stop tracking ${vessel.name}`}>
                  <strong>停止实时跟踪？</strong>
                  <p>此操作仅停止实时跟踪，不会删除船舶主数据及历史 AIS、航程和航线数据。</p>
                  {stopError?.vesselId === vessel.id && <small role="alert">{stopError.message}</small>}
                  <div>
                    <button type="button" onClick={() => { setConfirmStopVesselId(null); setOpenMenuVesselId(null); }} disabled={stoppingVesselId === vessel.id}>取消</button>
                    <button
                      type="button"
                      className="danger"
                      disabled={stoppingVesselId === vessel.id}
                      onClick={async () => {
                        if (await onStopVessel(vessel.id)) {
                          setConfirmStopVesselId(null);
                          setOpenMenuVesselId(null);
                        }
                      }}
                    >{stoppingVesselId === vessel.id ? "正在停止…" : "停止跟踪"}</button>
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>

      {insuranceStatus === "ready" && withoutLivePosition.length > 0 && <section className="insured-vessels-pending" aria-label="暂无实时船位的投保船舶">
        <strong>投保申报船舶 · 暂无实时船位</strong>
        <small>已从保单管理同步；仅在取得 AIS 船位后显示于实时地图。</small>
        {withoutLivePosition.map(vessel => <div key={vessel.imo_number ?? vessel.vessel_name}><span>{vessel.vessel_name}</span><small>IMO {vessel.imo_number ?? "待补"} · {vessel.declaration_number} · {({
          invalid_imo: "IMO 无效", awaiting_ais_provider: "船位数据源暂不可用", awaiting_imo_match: "等待 Chinaports 按 IMO 匹配船舶", mmsi_confirmation_required: "等待船舶身份核实", not_tracking: "未启动跟踪", awaiting_position: "已启动跟踪，等待船位", stale_position: "仅有历史船位", current: "船位同步中", unknown: "状态暂不可用",
        } as Record<string, string>)[vessel.tracking_status ?? "unknown"]}</small></div>)}
      </section>}

      {filteredVessels.length === 0 && !searchResult && <p className="live-vessel-empty">没有符合搜索条件的跟踪船舶。</p>}

      <footer className="live-vessel-actions">
        <button type="button" onClick={() => searchInputRef.current?.focus()}><span>+</span> 添加船舶</button>
        <button type="button" title="跟踪管理功能即将上线" disabled>跟踪管理</button>
      </footer>
    </section>
  );
}
