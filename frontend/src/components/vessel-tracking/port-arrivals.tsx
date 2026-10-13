"use client";

import { useEffect, useState } from "react";
import { fetchPortArrivals, type PortArrivals } from "@/services/port-humidity";

const ETA_FORMAT = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

export default function PortArrivalsList({ portCode }: { portCode: string }) {
  const [data, setData] = useState<PortArrivals | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchPortArrivals(portCode, controller.signal)
      .then(result => { setData(result); setStatus("ready"); })
      .catch(error => { if (error.name !== "AbortError") setStatus("error"); });
    const refresh = window.setInterval(() => setRetry(value => value + 1), 5 * 60 * 1000);
    return () => { controller.abort(); window.clearInterval(refresh); };
  }, [portCode, retry]);

  const current = data?.port_code === portCode ? data : null;
  return <section className="port-humidity-arrivals" aria-label="本港关联申报船舶">
    <div className="port-humidity-arrivals-heading">
      <h3>本港关联申报船舶</h3>
      {status === "ready" && current && <span>{current.arrivals.length} 艘</span>}
    </div>
    <p>今天剩余时间＋后续 5 个完整自然日 · 上海时间 · ETA 来自已确认投保申报。</p>
    <p>申报 ETA 不一定是该港实际靠港时间；多目的地共用同一申报 ETA。本列表仅辅助申报与风险工作流，非 AIS 到港预测，也非湿度风险结论。</p>
    {status === "error" ? <div className="port-humidity-chart-state" role="alert">船舶列表加载失败。
      <button type="button" onClick={() => { setStatus("loading"); setRetry(value => value + 1); }}>重试</button>
    </div> : !current ? <div className="port-humidity-chart-state" role="status">正在加载关联申报船舶…</div>
      : current.arrivals.length === 0 ? <div className="port-humidity-chart-state">该时段暂无目的地精确匹配本港的已确认投保申报。</div>
      : <ul className="port-humidity-arrivals-list">{current.arrivals.map(arrival => <li key={arrival.imo_number ?? arrival.vessel_name}>
        <div><strong>{arrival.vessel_name}</strong>{arrival.imo_number && <small>IMO {arrival.imo_number}</small>}<small>申报目的地：{arrival.discharge_port || "—"}</small></div>
        <div className="port-humidity-arrival-eta"><span>申报 ETA</span><strong>{ETA_FORMAT.format(new Date(arrival.eta))}</strong></div>
      </li>)}</ul>}
  </section>;
}
