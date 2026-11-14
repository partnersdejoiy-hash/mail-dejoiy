const test=require('node:test');const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');const path=require('node:path');
function setup(){
 const context={window:{DEJOIY_LIVE:true,addEventListener(){}},document:{body:{classList:{add(){}}},createElement(){return {querySelector(){return {addEventListener(){}}}}},getElementById(){return {before(){}}}},location:{pathname:'/',hash:'',reload(){context.reloaded=true}},Store:{state:{emails:[]}},Mail:{get(){return {read:false,starred:false}},setRead(){context.changed=true},toggleStar(){},toggleImportant(){},moveTo(){context.changed=true},deleteForever(){context.changed=true},addLabel(){context.changed=true}},App:{NAV:[['mail:inbox'],['settings'],['admin']],route:'compose',render(){},refreshNav(){},toast(){}},fetch:async()=>({ok:true,status:200,json:async()=>({ok:true})})};
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
/* A forgiving fake DOM for tests that need Live.install(): every element method exists and returns another fake. */
function anyNode(){ const f=function(){ return anyNode(); }; return new Proxy(f,{get:(t,k)=>k===Symbol.toPrimitive?(()=>''):k==='then'?undefined:anyNode(),apply:()=>anyNode(),set:()=>true}); }
function installed(){ const c=setup(); c.document.getElementById=()=>anyNode(); c.document.querySelector=()=>anyNode(); c.document.createElement=()=>anyNode(); c.live.install(); return c; }
test('an nginx HTML error page on send gives a clear message, not a JSON parse error',async()=>{
 const c=installed();
 c.fetch=async()=>({ok:false,status:413,json:async()=>{throw new SyntaxError("Unexpected token '<'");}});
 await assert.rejects(c.Mail.send({to:'a@b.com'}),e=>/too large to send/.test(e.message)&&!/Unexpected token/.test(e.message)&&e.status===413);
 c.fetch=async()=>({ok:false,status:504,json:async()=>{throw new SyntaxError("Unexpected token '<'");}});
 await assert.rejects(c.Mail.send({to:'a@b.com'}),/Check Sent before sending it again/);
});
test('a refused send carries the Drafts copy and refreshes the mailbox so it shows in Drafts',async()=>{
 const c=installed();const calls=[];
 c.fetch=async(url)=>{calls.push(url);return url==='/api/send'?{ok:false,status:502,json:async()=>({error:'Too big. Your message is saved in Drafts and was not sent.',draftId:'77',notSent:true})}
   :{ok:true,status:200,json:async()=>({emails:[],more:false,nextOffset:0})};};
 await assert.rejects(c.Mail.send({to:'a@b.com'}),e=>e.draftId==='77'&&e.notSent===true&&/saved in Drafts/.test(e.message));
 assert.deepEqual(calls,['/api/send','/api/mail']);
});
test('a refused send without a Drafts copy does not pretend to refresh',async()=>{
 const c=installed();const calls=[];
 c.fetch=async(url)=>{calls.push(url);return {ok:false,status:502,json:async()=>({error:'Mail server rejected this operation'})};};
 await assert.rejects(c.Mail.send({to:'a@b.com'}),/rejected/);assert.deepEqual(calls,['/api/send']);
});
