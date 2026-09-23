// Optional isolated PostgreSQL test. See README for the temporary PGlite install.
// No Supabase credentials or network/database writes are used by this test.
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

const enginePath = process.env.UKMTO_PGLITE_MODULE;
if (!enginePath) throw new Error('Set UKMTO_PGLITE_MODULE to the installed @electric-sql/pglite/dist/index.js');
const { PGlite } = await import(pathToFileURL(enginePath).href);
const db = new PGlite();
const directory = new URL('../supabase/migrations/', import.meta.url);
const migration = (await readdir(directory)).find(name => name.endsWith('_create_ukmto_incidents.sql'));
await db.exec('create role anon; create role authenticated; create role service_role bypassrls;');
await db.exec(await readFile(new URL(migration, directory), 'utf8'));

const base = {
  source: 'UKMTO', external_id: 'UKMTO-test-141', incident_number: 'test-141', incident_type: 'attack',
  title: 'Synthetic test', description: 'Synthetic body', source_url: 'https://www.ukmto.org/incident/test-141',
  content_hash: 'a'.repeat(64), latitude: null, longitude: null, location_precision: 'unknown',
  incident_time: null, published_at: '2026-09-22T08:00:00Z', raw_payload: { update_number: 0 },
};
async function save(payload, observed = '2026-09-22T09:00:00Z') {
  const { rows } = await db.query('select public.ingest_ukmto_incident($1::jsonb, $2::timestamptz) as action', [JSON.stringify(payload), observed]);
  return rows[0].action;
}
async function count(table) {
  return (await db.query(`select count(*)::int as count from public.${table}`)).rows[0].count;
}
try {
  await db.exec('set role service_role');
  assert.equal(await save(base), 'inserted');
  const original = (await db.query('select * from public.ukmto_incidents')).rows[0];
  assert.equal(await save(base, '2026-09-22T09:10:00Z'), 'unchanged');
  const repeated = (await db.query('select * from public.ukmto_incidents')).rows[0];
  assert.equal(repeated.updated_at.toISOString(), original.updated_at.toISOString());
  assert.notEqual(repeated.last_seen_at.toISOString(), original.last_seen_at.toISOString());
  assert.equal(repeated.incident_time, null);
  assert.equal(repeated.latitude, null);
  assert.equal(await count('ukmto_incidents'), 1);
  assert.equal(await count('ukmto_incident_updates'), 1);

  const update = { ...base, title: 'Update 001', content_hash: 'b'.repeat(64), raw_payload: { update_number: 1 } };
  assert.equal(await save(update, '2026-09-22T09:20:00Z'), 'updated');
  assert.equal(await count('ukmto_incident_updates'), 2);
  assert.equal(await save(base, '2026-09-22T09:30:00Z'), 'unchanged');
  assert.equal((await db.query('select title from public.ukmto_incidents')).rows[0].title, 'Update 001');
  const delayed = { ...update, content_hash: 'c'.repeat(64) };
  assert.equal(await save(delayed, '2026-09-22T09:00:00Z'), 'unchanged');
  assert.equal((await db.query('select content_hash from public.ukmto_incidents')).rows[0].content_hash, update.content_hash);
  assert.equal(await count('ukmto_incident_updates'), 3);

  // A failure after the main-row mutation must roll back the main row too.
  await db.exec('reset role');
  await db.exec("alter table public.ukmto_incident_updates add constraint test_fail check (title <> 'FAIL_HISTORY')");
  await db.exec('set role service_role');
  await assert.rejects(save({ ...update, title: 'FAIL_HISTORY', content_hash: 'd'.repeat(64) }, '2026-09-22T09:40:00Z'));
  await assert.rejects(save({ ...base, external_id: 'new-history-failure', title: 'FAIL_HISTORY' }));
  assert.equal((await db.query('select title from public.ukmto_incidents')).rows[0].title, 'Update 001');
  assert.equal(await count('ukmto_incident_updates'), 3);

  // Invalid coordinates cannot create partial records.
  await assert.rejects(save({ ...base, external_id: 'invalid', latitude: 91, longitude: 1 }));
  await assert.rejects(save({ ...base, external_id: 'invalid', latitude: 1 }));
  assert.equal(await count('ukmto_incidents'), 1);
  await assert.rejects(db.query("insert into public.ukmto_incidents (source, external_id, incident_type, source_url, content_hash) select source, external_id, incident_type, source_url, content_hash from public.ukmto_incidents"), /uk_ukmto_incidents_external_id/);
  await assert.rejects(db.query("insert into public.ukmto_incident_updates (incident_id, content_hash) select incident_id, content_hash from public.ukmto_incident_updates limit 1"), /uk_ukmto_incident_updates_hash/);
  await db.exec('reset role');
  const constraints = (await db.query("select conname from pg_constraint where conname in ('uk_ukmto_incidents_external_id', 'uk_ukmto_incident_updates_hash')")).rows;
  assert.equal(constraints.length, 2);
  const times = (await db.query("select data_type from information_schema.columns where table_name = 'ukmto_incidents' and column_name in ('incident_time', 'published_at', 'last_seen_at')")).rows;
  assert(times.every(row => row.data_type === 'timestamp with time zone'));
  const rls = (await db.query("select relrowsecurity from pg_class where relname in ('ukmto_incidents', 'ukmto_incident_updates')")).rows;
  assert.equal(rls.length, 2);
  assert(rls.every(row => row.relrowsecurity));
  for (const role of ['anon', 'authenticated']) {
    await db.exec(`set role ${role}`);
    await assert.rejects(save(base), /permission denied/);
    await assert.rejects(db.query('select * from public.ukmto_incidents'), /permission denied/);
    await db.exec('reset role');
  }
  // Optional actual parser output, e.g. the CLI's --dry-run JSON Lines file.
  if (process.argv[2]) {
    const lines = (await readFile(process.argv[2], 'utf8')).trim().split('\n');
    const records = lines.map(line => JSON.parse(line).incident);
    await db.exec('set role service_role');
    const before = await count('ukmto_incidents');
    const historyBefore = await count('ukmto_incident_updates');
    for (const record of records) assert.equal(await save(record, '2026-09-22T16:00:00Z'), 'inserted');
    for (const record of records) assert.equal(await save(record, '2026-09-22T16:10:00Z'), 'unchanged');
    assert.equal(await count('ukmto_incidents'), before + records.length);
    assert.equal(await count('ukmto_incident_updates'), historyBefore + records.length);
    console.log(`PASS: ${records.length} real parsed incidents inserted and repeated without duplicates (isolated PostgreSQL)`);
  }
  console.log('PASS: PostgreSQL migration, insert, repeat, update, stale reports, rollback, constraints, timestamps, RLS and grants');
} finally {
  await db.close();
}
