const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
const ts=require('typescript');const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');
function load(file,extra='',react=React) {
  const source=fs.readFileSync(path.join(__dirname,'../src',file),'utf8');
  const context={exports:{},Intl,require(name){
    if(name==='react')return react;
    if(name==='react/jsx-runtime')return require(name);
    return {};
  }};
  vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText+extra,context);
  return context.exports;
}
test('declaration detail preserves state/actions and groups real fields without invented values',()=>{
  const {Detail}=load('components/insurance/insurance-workbench.tsx','\nexports.Detail = DeclarationDetailDialog;');
  const detail={id:'arbitrary-id',declaration_number:'REAL-REFERENCE',status:'confirmed',company_name:'Enterprise',policy_name:'Framework',documents:[],
    shipments:[{id:'s',vessel_name:'A VERY LONG VESSEL NAME',imo_number:null,cargo_name:'Cargo',loading_port:'Origin',discharge_port:'天津、青岛',insured_value:100,insurance_rate:0,premium:0,currency:'CNY',extra_data:{}}]};
  const html=renderToStaticMarkup(React.createElement(Detail,{detail,busy:false,onClose(){},onVoid(){},onSubmitDraft(){}}));
  for(const label of ['REAL-REFERENCE','Enterprise','Framework','投保确认','船舶与运输','保险金额与费用','补充资料与跟踪状态','天津、青岛','CNY 100','0%','暂无附件']) assert.ok(html.includes(label),label);
  assert.ok(html.includes('insurance-declaration-detail'));
  assert.ok(!html.includes('USD'));
});
test('arrival list discloses declaration ETA and never reuses another port data',()=>{
  const data={port_code:'CN_TIANJIN',arrivals:[{vessel_name:'Ship',imo_number:'1234567',eta:'2026-10-14T00:00:00Z',discharge_port:'天津、青岛'}]};
  const fakeReact={...React,useEffect(){},useState(initial){return [initial===null?data:initial==='loading'?'ready':initial,()=>{}]}};
  const List=load('components/vessel-tracking/port-arrivals.tsx','',fakeReact).default;
  const html=renderToStaticMarkup(List({portCode:'CN_TIANJIN'}));
  for(const text of ['后续 5 个完整自然日','不一定是该港实际靠港时间','非 AIS 到港预测','非湿度风险结论','申报 ETA','天津、青岛'])assert.ok(html.includes(text),text);
  const other=renderToStaticMarkup(List({portCode:'CN_QINGDAO'}));
  assert.ok(!other.includes('1234567'));assert.ok(other.includes('正在加载'));
});
