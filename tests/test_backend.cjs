const test=require('node:test');const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');const path=require('node:path');
function setup(){
 const context={window:{DEJOIY_LIVE:true,addEventListener(){}},document:{body:{classList:{add(){}}},createElement(){return {querySelector(){return {addEventListener(){}}}}},getElementById(){return {before(){}}}},location:{pathname:'/',hash:'',reload(){context.reloaded=true}},Store:{state:{emails:[]}},Mail:{get(){return {read:false,starred:false}},setRead(){context.changed=true},toggleStar(){},toggleImportant(){},moveTo(){context.changed=true},deleteForever(){context.changed=true}},App:{NAV:[['mail:inbox'],['settings'],['admin']],route:'compose',render(){},refreshNav(){},toast(){}},fetch:async()=>({ok:true,status:200,json:async()=>({ok:true})})};
 vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/js/backend.js'),'utf8'),context);context.live=context.window.Live;return context;
}
test('missing initial session opens login instead of reloading forever',async()=>{
 const c=setup();c.fetch=async()=>({ok:false,status:401,json:async()=>({error:'Sign in'})});
 await assert.rejects(c.live.request('session'),/Sign in/);assert.equal(c.reloaded,undefined);
});
test('failed server action does not mutate local mail',async()=>{
 const c=setup();c.live.install();c.fetch=async()=>({ok:false,status:502,json:async()=>({error:'Rejected'})});
 await assert.rejects(c.Mail.moveTo(['12'],'trash'),/Rejected/);assert.equal(c.changed,undefined);
});
test('mutation carries the CSRF token and changes state only after success',async()=>{
 const c=setup();c.live.csrf='csrf-token';c.live.install();let headers;
 c.fetch=async(url,options)=>{headers=options.headers;assert.equal(c.changed,undefined);return {ok:true,status:200,json:async()=>({ok:true})};};
 await c.Mail.moveTo(['12'],'trash');assert.equal(headers['X-CSRF-Token'],'csrf-token');assert.equal(c.changed,true);
});
test('send failure propagates instead of reporting success',async()=>{
 const c=setup();c.live.install();c.fetch=async()=>({ok:false,status:502,json:async()=>({error:'Send failed'})});
 await assert.rejects(c.Mail.send({to:'a@b.com'}),/Send failed/);
});
test('administrator login rejection does not reload the mailbox session',async()=>{
 const c=setup();c.fetch=async()=>({ok:false,status:401,json:async()=>({error:'Administrator sign-in failed'})});
 await assert.rejects(c.live.request('admin/login',{password:'bad'}),/Administrator/);assert.equal(c.reloaded,undefined);
});
