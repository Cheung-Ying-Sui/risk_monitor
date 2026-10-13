/* eslint-disable @typescript-eslint/no-require-imports */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const source = fs.readFileSync(path.join(__dirname, '../src/components/vessel-tracking/navigation-prediction-browser.tsx'), 'utf8');
const context = {exports:{}, require(name) {
  if (name === 'react/jsx-runtime') return require(name);
  return {formatObservedAt: value => value};
}};
vm.runInNewContext(ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS, jsx:ts.JsxEmit.ReactJSX}}).outputText, context);
const Browser = context.exports.NavigationPredictionBrowser;
const voyage = (id, extras={}) => ({shipment_id:id, declaration_number:`NEW-${id}`, vessel_id:'same-vessel', vessel_name:'Test vessel', status:'estimated', warnings:[], prediction:{}, progress:0.25, remaining_distance_nm:100, confidence:0.6, route_version:2, ...extras});
const render = (voyages, selectedShipmentId, extras={}) => renderToStaticMarkup(React.createElement(Browser, {voyages, selectedShipmentId, status:'ready', error:null, onSelectShipment(){}, onRetry(){}, ...extras}));
test('same vessel has independently selectable shipments and real declaration labels', () => {
  const html = render([voyage('first'), voyage('next')], 'next');
  assert.match(html, /value="first"/);
  assert.match(html, /value="next" selected/);
  assert.match(html, /NEW-next/);
  assert.match(html, /25.0%/);
});
test('completed selection disappears, new shipment never inherits its metrics', () => {
  const html = render([voyage('new')], 'completed');
  assert.doesNotMatch(html, /航程进度|25.0%/);
  assert.match(html, /NEW-new/);
});
test('unavailable, stale, mismatch and pending cannot expose old ETA or zero progress', () => {
  for (const status of ['position_unavailable','ais_stale','destination_mismatch','destination_unresolved','ambiguous_active_shipments','route_pending','needs_review']) {
    const html = render([voyage('a', {status, eta:'OLD-ETA'})], 'a');
    assert.doesNotMatch(html, /OLD-ETA|航程进度|预计到达|25.0%/);
  }
});
test('request loading or failure cannot display cached prediction', () => {
  for (const status of ['loading','error']) {
    const html = render([voyage('a')], 'a', {status, error:'network unavailable'});
    assert.doesNotMatch(html, /25.0%|航程进度/);
    assert.match(html, status === 'error' ? /network unavailable/ : /正在核验/);
  }
});
test('AIS fallback is explicitly presented as an estimate needing verification', () => {
  assert.match(render([voyage('a', {destination_source:'ais_fallback'})], 'a'), /按 AIS 目的地估算，待核实/);
});
