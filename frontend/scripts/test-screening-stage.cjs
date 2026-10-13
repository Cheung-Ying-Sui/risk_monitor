const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const ts=require('typescript');const path=require('node:path');
const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/components/sanctions-screening/declaration-screening-queue.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText;
function harness(stage) {
  const row={declaration_id:'fresh-id',declaration_number:'fresh-number',company_name:'Fresh company',status:'pending_review',stage,
    parties:[{shipment_id:'s',role:'insured_name',label:'被保险人',name:'Fresh subject',preliminary:{screened_at:'2026-01-01',results:[],suggestions:[]},evidence:{document_id:'e',url:null},review:{result:'no_match',reviewer:'R',note:'',reviewed_at:'2026-01-01'}}],
    report:{file_name:'report.docx',template_version:'sinochem-questionnaire-v1',sha256:'hash'},underwriting:{shipment_count:1,insured_value:100,currency:'USD'}};
  let cursor=0;const hooks=[];let stateNumber=0;let reread=0;
  const react={useState(initial){const i=cursor++;if(!(i in hooks)){const n=stateNumber++;hooks[i]=n===0?[row]:n===2?'fresh-id':initial;}return[hooks[i],v=>hooks[i]=typeof v==='function'?v(hooks[i]):v]},useRef(initial){const i=cursor++;return hooks[i]??(hooks[i]={current:initial})},useEffect(){},useCallback:fn=>fn};
  const jsx=(type,props)=>({type,props});function Modal(){}
  const context={exports:{},Error,URLSearchParams,window:{},require(name){if(name==='react')return react;if(name==='react/jsx-runtime')return {jsx,jsxs:jsx};if(name.includes('underwriting-confirmation-dialog'))return {UnderwritingConfirmationDialog:Modal};if(name==='@/services/sanctions')return {downloadDeclarationScreeningReport:async()=>new Blob(['report']),getDeclarationScreeningCase:async()=>{reread++;return {...row,stage:'pending_underwriting',report:{...row.report,downloaded_at:'2026-01-01'}}}};return {};}};
  vm.runInNewContext(code,context);
  function render(){cursor=0;return context.exports.DeclarationScreeningQueue()}
  function all(node){if(!node||typeof node!=='object')return [];return[node,...[node.props?.children].flat(Infinity).flatMap(all)]}
  return{render,all,Modal,get reread(){return reread}};
}
test('download completion rereads persisted phase then card opens dialog',async()=>{
  const h=harness('pending_report_download');
  const action=h.all(h.render()).find(n=>n.type==='button'&&n.props.children==='生成并下载筛查结果报告');
  action.props.onClick();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.reread,1);
  let tree=h.render();assert.ok(h.all(tree).some(n=>n.props?.children==='承保条件确认 · 点击打开'));
  h.all(tree).find(n=>n.type==='button'&&n.props.className==='selected').props.onClick();
  assert.ok(h.all(h.render()).some(n=>n.type===h.Modal));
});
test('fresh mount restores pending confirmation from server phase',()=>{
  const h=harness('pending_underwriting');
  assert.ok(h.all(h.render()).some(n=>n.props?.children==='承保条件确认 · 点击打开'));
});
