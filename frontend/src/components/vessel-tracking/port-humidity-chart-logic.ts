/** ETA is an annotation, never a side effect of browsing a historical month. */
export function chartSelection(etaDate: string, browseMonth: number, daysInMonth: number) {
  const etaMonth = Number(etaDate.slice(5, 7));
  const etaDay = Number(etaDate.slice(8, 10));
  const showEta = browseMonth === etaMonth && etaDay >= 1 && etaDay <= daysInMonth;
  return {
    etaMonth,
    etaDay,
    showEta,
    windowStart: showEta ? Math.max(1, etaDay - 7) : null,
    windowEnd: showEta ? Math.min(daysInMonth, etaDay + 7) : null,
  };
}
