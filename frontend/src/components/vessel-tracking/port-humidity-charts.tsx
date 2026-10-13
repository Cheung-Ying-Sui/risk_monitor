"use client";

import { useEffect, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ReferenceArea,
  ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { fetchHumiditySeasonal, type HumiditySeasonal, type HumiditySeasonalBucket } from "@/services/port-humidity";
import { chartSelection } from "./port-humidity-chart-logic";

const THEME = "#137f83";
const MUTED = "rgba(174, 190, 196, .52)";

function monthFromEta(etaDate: string) {
  return Number(etaDate.slice(5, 7));
}

function dateTooltip(bucket: HumiditySeasonalBucket | undefined, label: string, threshold: number) {
  if (!bucket) return null;
  return <div className="port-humidity-chart-tooltip">
    <strong>{label}</strong>
    <span>2016—2025年 · RH≥{threshold}%</span>
    <span>历史高湿度时间占比：{bucket.percentage == null ? "暂无数据" : `${bucket.percentage.toFixed(1)}%`}</span>
    <span>有效观测：{bucket.valid_hours} 小时 / 应有 {bucket.expected_hours} 小时</span>
  </div>;
}

export default function PortHumidityCharts({ portCode, etaDate, threshold }: {
  portCode: string; etaDate: string; threshold: number;
}) {
  const etaMonth = monthFromEta(etaDate);
  const [browseMonth, setBrowseMonth] = useState(etaMonth);
  const [data, setData] = useState<HumiditySeasonal | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      fetchHumiditySeasonal(portCode, browseMonth, threshold, controller.signal)
        .then(result => { setData(result); setStatus("ready"); })
        .catch(error => { if (error.name !== "AbortError") setStatus("error"); });
    }, 200);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [portCode, browseMonth, threshold, retry]);

  const current = data?.port_code === portCode && data.month === browseMonth && data.rh_threshold === threshold ? data : null;
  const month = Number.isInteger(browseMonth) && browseMonth >= 1 && browseMonth <= 12 ? browseMonth : etaMonth;
  const { etaDay, showEta, windowStart, windowEnd } = chartSelection(etaDate, month, current?.daily.length ?? 31);
  const monthData = current?.monthly.map(bucket => ({ ...bucket, label: `${bucket.index}月` })) ?? [];
  const dayData = current?.daily.map(bucket => ({ ...bucket, label: `${bucket.index}日` })) ?? [];

  return <div className="port-humidity-charts">
    <section aria-label="全年高湿度时间分布">
      <h3>全年高湿度时间分布</h3>
      <p>2016—2025年 · RH≥{threshold}% · 按有效观测小时加权</p>
      {status === "error" ? <div className="port-humidity-chart-state" role="alert">历史图表加载失败。<button type="button" onClick={() => { setStatus("loading"); setRetry(value => value + 1); }}>重试</button></div>
        : !current ? <div className="port-humidity-chart-state" role="status">正在加载历史统计…</div>
        : current.monthly.every(bucket => bucket.valid_hours === 0) ? <div className="port-humidity-chart-state">暂无有效历史样本，无法计算月度占比。</div>
        : <div className="port-humidity-chart" role="img" aria-label={`全年高湿度时间分布，当前浏览${month}月`}>
          <ResponsiveContainer width="100%" height={166}>
            <BarChart data={monthData} margin={{ top: 8, right: 5, bottom: 0, left: -23 }}>
              <CartesianGrid vertical={false} stroke="#edf1f3" />
              <XAxis dataKey="label" tick={{ fontSize: 9 }} tickLine={false} axisLine={false} interval={0} />
              <YAxis domain={[0, 100]} tickFormatter={value => `${value}%`} tick={{ fontSize: 9 }} tickLine={false} axisLine={false} />
              <Tooltip cursor={{ fill: "#eff7f7" }} content={({ active, payload }) => active ? dateTooltip(payload?.[0]?.payload as HumiditySeasonalBucket | undefined,
                `${(payload?.[0]?.payload as HumiditySeasonalBucket | undefined)?.index}月`, threshold) : null} />
              <Bar dataKey="percentage" radius={[2, 2, 0, 0]} maxBarSize={21}
                onClick={(_, index) => setBrowseMonth(index + 1)}>
                {monthData.map(bucket => <Cell key={bucket.index} fill={bucket.index === month ? THEME : MUTED} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>}
      {current && current.monthly.some(bucket => bucket.valid_hours > 0 && bucket.valid_hours < bucket.expected_hours) &&
        <small className="port-humidity-chart-note">部分月份存在缺测；占比仅以有效观测小时计算。</small>}
      {month !== etaMonth && <div className="port-humidity-browse">正在查看{month}月历史数据 · ETA 仍为 {etaDate}
        <button type="button" onClick={() => setBrowseMonth(etaMonth)}>返回 ETA 月份</button></div>}
    </section>
    <section aria-label="当月每日历史高湿度频率">
      <h3>当月每日历史高湿度频率</h3>
      <p>{month}月 · 2016—2025年 · RH≥{threshold}%</p>
      {status === "error" ? <div className="port-humidity-chart-state">每日数据暂不可用。</div>
        : !current ? <div className="port-humidity-chart-state">正在加载每日数据…</div>
        : current.daily.every(bucket => bucket.valid_hours === 0) ? <div className="port-humidity-chart-state">{month}月暂无有效历史样本；无数据日期不按 0% 绘制。</div>
        : <div className="port-humidity-chart" role="img" aria-label={`${month}月每日历史高湿度频率${showEta ? `，ETA ${etaDay}日，同期窗口前后7天` : ""}`}>
          <ResponsiveContainer width="100%" height={194}>
            <AreaChart data={dayData} margin={{ top: 13, right: 12, bottom: 0, left: -23 }}>
              <defs><linearGradient id="humidityChartFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={THEME} stopOpacity={0.15} /><stop offset="100%" stopColor={THEME} stopOpacity={0} /></linearGradient></defs>
              <CartesianGrid vertical={false} stroke="#edf1f3" />
              <XAxis dataKey="index" type="number" domain={[0.5, dayData.length + 0.5]} ticks={[1, 5, 10, 15, 20, 25, dayData.length]}
                tickFormatter={value => `${value}日`} tick={{ fontSize: 9 }} tickLine={false} axisLine={false} />
              <YAxis domain={[0, 100]} tickFormatter={value => `${value}%`} tick={{ fontSize: 9 }} tickLine={false} axisLine={false} />
              {showEta && windowStart != null && windowEnd != null && <ReferenceArea x1={windowStart - 0.5} x2={windowEnd + 0.5} fill={THEME} fillOpacity={0.10} strokeOpacity={0} ifOverflow="hidden" />}
              {showEta && <ReferenceLine x={etaDay} stroke={THEME} strokeWidth={1.5} strokeDasharray="4 3"
                label={{ value: `ETA · ${month}月${etaDay}日`, position: "top", fill: THEME, fontSize: 9 }} />}
              <Tooltip content={({ active, payload }) => active ? dateTooltip(payload?.[0]?.payload as HumiditySeasonalBucket | undefined,
                `${month}月${(payload?.[0]?.payload as HumiditySeasonalBucket | undefined)?.index}日`, threshold) : null} />
              <Area type="monotone" dataKey="percentage" stroke={THEME} strokeWidth={2} fill="url(#humidityChartFill)"
                connectNulls={false} activeDot={{ r: 4, fill: THEME }} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>}
      {showEta && current && <small className="port-humidity-chart-note">ETA {month}月{etaDay}日 · 同期窗口 {month}月{windowStart}—{windowEnd}日（跨月部分不在本图显示）</small>}
      {current && current.daily.some(bucket => bucket.valid_hours === 0) && <small className="port-humidity-chart-note">空白日期表示暂无有效样本；2月29日仅统计闰年。</small>}
    </section>
  </div>;
}
