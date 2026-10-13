const {test} = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../src/components/sanctions-screening/underwriting-confirmation-dialog.tsx'),'utf8');
function harness(complete) {
  let cursor=0; const hooks=[]; const confirmed=[];
  const react={useState(initial){const i=cursor++;if(!(i in hooks))hooks[i]=initial;return [hooks[i],v=>{hooks[i]=v}];},
    useRef(initial){const i=cursor++;return hooks[i]??(hooks[i]={current:initial})},useEffect(){}};
  const jsx=(type,props)=>({type,props});
  const context={exports:{},Error,require(name){if(name==='react')return react;if(name==='react/jsx-runtime')return {jsx,jsxs:jsx};return {completeUnderwriting:complete};}};
  vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText,context);
  const declaration={declaration_id:'arbitrary-new-id',declaration_number:'generic-number',company_name:'Another Company',underwriting:{shipment_count:1,insured_value:10000,currency:'USD',cargo_name:'Cargo'}};
  function render(){cursor=0;return context.exports.UnderwritingConfirmationDialog({declaration,onClose(){},onConfirmed:d=>confirmed.push(d)});}
  function all(node){if(!node||typeof node!=='object')return [];return [node,...[node.props?.children].flat(Infinity).flatMap(all)];}
  return {render,find:(tree,type)=>all(tree).find(n=>n.type===type),all,confirmed};
}
test('server failure preserves rate and displays error without confirming',async()=>{
  const h=harness(async()=>{throw Error('报告已过期，请重新下载')});
  h.find(h.render(),'input').props.onChange({target:{value:'0.15'}});
  await h.find(h.render(),'form').props.onSubmit({preventDefault(){}});
  const tree=h.render();
  assert.equal(h.find(tree,'input').props.value,'0.15');
  assert.equal(h.confirmed.length,0);
  assert.match(h.all(tree).find(n=>n.props?.role==='alert').props.children,/报告已过期/);
});
test('valid confirmation uses supplied id and blocks concurrent double submit',async()=>{
  let resolve;let calls=0;
  const h=harness((id,rate)=>{calls++;assert.equal(id,'arbitrary-new-id');assert.equal(rate,0.15);return new Promise(r=>resolve=r)});
  h.find(h.render(),'input').props.onChange({target:{value:'0.15'}});
  const submit=h.find(h.render(),'form').props.onSubmit;
  const first=submit({preventDefault(){}});await submit({preventDefault(){}});
  assert.equal(calls,1);resolve({id:'arbitrary-new-id',status:'confirmed'});await first;
  assert.equal(h.confirmed.length,1);
});
test('invalid rate never calls server',async()=>{
  const h=harness(()=>assert.fail('server should not be called'));
  for(const value of ['', '-1', '101', 'NaN']) {
    h.find(h.render(),'input').props.onChange({target:{value}});
    await h.find(h.render(),'form').props.onSubmit({preventDefault(){}});
    assert.equal(h.confirmed.length,0);
  }
});
