// Help desk page: the queue tab names what is in it. Run: node --test tests/test_tickets_ui.cjs
const test=require('node:test');const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');const path=require('node:path');

async function queueTab(meta){
  const el={innerHTML:'',querySelectorAll(){return [];},querySelector(){return {addEventListener(){}};}};
  const context={window:{Live:{enabled:true}},Views:{},App:{route:'desk',toast(){}},Icons:{get(){return '';}},
    esc:s=>String(s),console,
    Live:{enabled:true,request:async p=>p==='tickets/meta'?meta:{tickets:[]}}};
  context.window.Live=context.Live;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/js/view-tickets.js'),'utf8'),context);
  await context.Views.desk(el);
  return [...el.innerHTML.matchAll(/data-view="(\w+)">([^<]*)</g)].map(m=>[m[1],m[2]]);
}

test('a company admin with no department sees the Company admin queue',async()=>{
  const tabs=await queueTab({department:'',manage:true,platform:false,waiting:0});
  assert.deepEqual(tabs.find(t=>t[0]==='team'),['team','Company admin queue']);
});
test('a company admin in a department sees both in the tab name',async()=>{
  const tabs=await queueTab({department:'IT',manage:true,platform:false,waiting:2});
  assert.deepEqual(tabs.find(t=>t[0]==='team'),['team','IT + Company admin queue · 2']);
});
test('an employee in a department sees only their department queue',async()=>{
  const tabs=await queueTab({department:'HR',manage:false,platform:false,waiting:0});
  assert.deepEqual(tabs.map(t=>t[0]),['mine','team']);
  assert.equal(tabs[1][1],'HR queue');
});
test('an employee with no department has only My tickets',async()=>{
  const tabs=await queueTab({department:'',manage:false,platform:false,waiting:0});
  assert.deepEqual(tabs.map(t=>t[0]),['mine']);
});
