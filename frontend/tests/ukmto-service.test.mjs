import test from "node:test";
import assert from "node:assert/strict";
import { fetchUKMTOEvents, hasCoordinates, incidentToEvent } from "../src/services/ukmto.ts";

const query = { category: "all", timeRange: "all", start: "", end: "" };
const row = { external_id: "report-1", incident_type: "attack", title: "Report", description: "Original report", latitude: 0, longitude: 0, incident_time: null, source_url: "https://www.ukmto.org/" };
const signal = () => new AbortController().signal;

test("retains original text and missing dates without inventing coordinates or severity", () => {
  const event = incidentToEvent(row);
  assert.equal(event.summary, row.description);
  assert.equal(event.occurredAt, null);
  assert.equal(event.severity, "unknown");
  assert.equal(hasCoordinates(event), true);
  for (const latitude of [null, undefined, NaN, 91]) {
    assert.equal(hasCoordinates(incidentToEvent({ ...row, latitude })), false);
  }
});

test("loads subsequent pages and deduplicates reports", async (t) => {
  const urls = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    urls.push(new URL(url));
    return Response.json(urls.length === 1
      ? { items: [row], has_more: true, next_offset: 1 }
      : { items: [row, { ...row, external_id: "report-2" }], has_more: false, next_offset: null });
  });
  const events = await fetchUKMTOEvents(query, signal());
  assert.deepEqual(events.map((event) => event.id), ["report-1", "report-2"]);
  assert.deepEqual(urls.map((url) => url.searchParams.get("offset")), ["0", "1"]);
  assert.equal(urls[0].searchParams.has("from"), false);
});

test("sends category and inclusive UTC date boundaries", async (t) => {
  t.mock.method(globalThis, "fetch", async (url) => {
    const params = new URL(url).searchParams;
    assert.equal(params.get("incident_type"), "attack");
    assert.equal(params.get("from"), "2026-09-01T00:00:00Z");
    assert.equal(params.get("to"), "2026-09-23T23:59:59.999Z");
    return Response.json({ items: [], has_more: false });
  });
  assert.deepEqual(await fetchUKMTOEvents({ category: "attack", timeRange: "custom", start: "2026-09-01", end: "2026-09-23" }, signal()), []);
});

test("rejects HTTP failures rather than returning demonstration events", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response("unavailable", { status: 503 }));
  await assert.rejects(fetchUKMTOEvents(query, signal()), /503/);
});

test("rejects broken pagination rather than looping", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ items: [row], has_more: true }));
  await assert.rejects(fetchUKMTOEvents(query, signal()), /分页异常/);
});
