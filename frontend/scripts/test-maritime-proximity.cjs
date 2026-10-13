/* eslint-disable @typescript-eslint/no-require-imports */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
function load(file, globals={}, imports={}) {
  const context = {exports:{}, Date, URLSearchParams, AbortSignal, process:{env:{}}, ...globals,
    require(name) { return imports[name] ?? (name==='react/jsx-runtime' ? require(name) : {}); }};
  const source=fs.readFileSync(path.join(__dirname,'../src',file),'utf8');
  vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText,context);
  return context.exports;
}
test('counts distinguish loading, error, stale, missing, zero and positive',()=>{
  const {vesselRiskLabel:label}=load('components/maritime-intelligence/vessel-risk-label.ts');
  const row={calculation_status:'ok',event_count:4};
  assert.match(label(row,'loading'),/正在计算/);
  assert.match(label(row,'error'),/暂不可用/);
  assert.match(label({...row,calculation_status:'position_stale'},'ready'),/位置过期/);
  assert.match(label(undefined,'ready'),/位置不可用/);
  assert.match(label({...row,event_count:0},'ready'),/当前筛选范围内未发现/);
  assert.match(label(row,'ready'),/500 海里内 4 条/);
});
test('one UTC snapshot used for event pagination and batch counts; no mock fallback',async()=>{
  const urls=[];
  const api=load('services/ukmto.ts',{fetch:async url=>{
    urls.push(new URL(url));
    if(url.includes('vessel-risk-counts'))return {ok:true,json:async()=>({items:[]})};
    const offset=urls.at(-1).searchParams.get('offset');
    return {ok:true,json:async()=>({items:[{external_id:'same-id',incident_type:'attack'}],has_more:offset==='0',next_offset:offset==='0'?1:null})};
  }});
  const query={category:'attack',timeRange:'7d',start:'',end:''};
  const snapshot=api.incidentQueryParams(query,Date.parse('2026-10-13T00:00:00Z'));
  const rows=await api.fetchUKMTOEvents(query,new AbortController().signal,snapshot);
  await api.fetchVesselRiskCounts(snapshot,new AbortController().signal);
  assert.equal(rows.length,1);
  for(const url of urls) {
    assert.equal(url.searchParams.get('from'),'2026-10-06T00:00:00.000Z');
    assert.equal(url.searchParams.get('to'),'2026-10-13T00:00:00.000Z');
    assert.equal(url.searchParams.get('incident_type'),'attack');
  }
  assert.equal(snapshot.has('offset'),false);
  const failed=load('services/ukmto.ts',{fetch:async()=>({ok:false,status:503})});
  await assert.rejects(failed.fetchVesselRiskCounts(snapshot,new AbortController().signal),/503/);
  await assert.rejects(failed.fetchUKMTOEvents(query,new AbortController().signal),/503/);
});
test('stable SVG category icons are distinct and both maps share directional body',()=>{
  const {CategoryIcon}=load('components/maritime-intelligence/category-icon.tsx');
  const html=['attack','suspicious_activity','hijack','advisory','military_interaction','unknown'].map(category=>renderToStaticMarkup(React.createElement(CategoryIcon,{category})));
  assert.equal(new Set(html).size,6);
  html.forEach(markup=>{assert.match(markup,/<svg/);assert.match(markup,/<path/);assert.match(markup,/aria-hidden="true"/);});
  const {vesselDirection}=load('lib/vessel-marker.ts');
  assert.equal(vesselDirection(90,180),90);
  assert.equal(vesselDirection(511,180),180);
  assert.equal(vesselDirection(null,null),0);
  const read=file=>fs.readFileSync(path.join(__dirname,'../src',file),'utf8');
  for(const file of ['app/maritime-map.tsx','components/maritime-intelligence/intelligence-map.tsx']) assert.match(read(file),/createVesselMarkerBody/);
  const map=read('components/maritime-intelligence/intelligence-map.tsx');
  assert.match(map,/querySelector\("summary"\)\?\.remove\(\)/);
  assert.doesNotMatch(map,/mock\/|demo/i);
  assert.match(map,/aria-pressed/);
  const css=read('app/maritime-intelligence/maritime-intelligence.css');
  assert.match(css,/\.intelligence-marker \{[^}]*border-radius: 0;/);
  assert.match(css,/\.intelligence-category-symbol \{[^}]*border-radius: 0;/);
  assert.doesNotMatch(css,/\.intelligence-marker.selected[^}]*transform:/);
});
test('filter changes do not render results from a previous request key',()=>{
  const source=fs.readFileSync(path.join(__dirname,'../src/components/maritime-intelligence/maritime-intelligence-workspace.tsx'),'utf8');
  assert.match(source,/riskResult.key === riskKey && !riskResult.error \? riskResult.rows : \[\]/);
  assert.match(source,/riskResult.key !== riskKey \? "loading"/);
  assert.match(source,/controller.signal.aborted/);
});
test('risk report appears in selected vessel popup, not sidebar',()=>{
  const read=file=>fs.readFileSync(path.join(__dirname,'../src/components/maritime-intelligence',file),'utf8');
  assert.doesNotMatch(read('intelligence-feed.tsx'),/vesselRiskLabel|riskCounts|filterLabel/);
  const map=read('intelligence-map.tsx');
  assert.match(map,/if \(!map \|\| !mapReady \|\| !selected\) return/);
  assert.match(map,/new maplibregl.Popup/);
  assert.match(map,/setDOMContent\(content\)/);
  assert.match(map,/popup.off\("close", close\); popup.remove\(\)/);
});
test('workspace renders loading instead of cached counts after changing category',()=>{
  const services=load('services/ukmto.ts');
  function render(category, cachedKey, failed=false) {
    let stateIndex=0;
    const react={...React,useMemo:fn=>fn(),useCallback:fn=>fn,useEffect(){},useState(initial){
      const index=stateIndex++;
      const value=index===0?category : index===8?{key:cachedKey,rows:[{event_count:99}],error:failed}:initial;
      return [value,()=>{}];
    }};
    const {MaritimeIntelligenceWorkspace:Workspace}=load('components/maritime-intelligence/maritime-intelligence-workspace.tsx',{}, {
      react,
      '@/services/ukmto':services,
      '@/hooks/use-insured-vessels':{useInsuredVessels:()=>({status:'ready',vessels:[],refresh(){}})},
      '@/hooks/use-live-vessels':{useLiveVessels:()=>({status:'ready',vessels:[],refresh(){}})},
      '@/lib/insured-vessels':{matchInsuredLiveVessels:()=>[]},
      './intelligence-feed':{IntelligenceFeed:'feed'},'./intelligence-map':{IntelligenceMap:'map'},
    });
    return Workspace().props.children[1].props;
  }
  const key=JSON.stringify([JSON.stringify(['attack','all','','',0]),[],[]]);
  const ready=render('attack',key);
  assert.equal(ready.riskStatus,'ready');assert.equal(ready.riskCounts[0].event_count,99);
  const changed=render('advisory',key);
  assert.equal(changed.riskStatus,'loading');assert.equal(changed.riskCounts.length,0);
  const failed=render('attack',key,true);
  assert.equal(failed.riskStatus,'error');assert.equal(failed.riskCounts.length,0);
});
