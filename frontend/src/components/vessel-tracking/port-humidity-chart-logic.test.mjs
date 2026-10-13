import assert from "node:assert/strict";
import test from "node:test";
import { chartSelection } from "./port-humidity-chart-logic.ts";

test("ETA month selection and ±7-day window", () => {
  assert.deepEqual(chartSelection("2026-09-15", 9, 30), {
    etaMonth: 9, etaDay: 15, showEta: true, windowStart: 8, windowEnd: 22,
  });
  assert.deepEqual(chartSelection("2026-10-20", 10, 31), {
    etaMonth: 10, etaDay: 20, showEta: true, windowStart: 13, windowEnd: 27,
  });
  assert.deepEqual(chartSelection("2026-10-10", 10, 31), {
    etaMonth: 10, etaDay: 10, showEta: true, windowStart: 3, windowEnd: 17,
  });
});

test("cross-month window clips only its display; browsing does not change ETA", () => {
  assert.deepEqual(chartSelection("2026-10-29", 10, 31), {
    etaMonth: 10, etaDay: 29, showEta: true, windowStart: 22, windowEnd: 31,
  });
  assert.deepEqual(chartSelection("2026-10-20", 8, 31), {
    etaMonth: 10, etaDay: 20, showEta: false, windowStart: null, windowEnd: null,
  });
});
