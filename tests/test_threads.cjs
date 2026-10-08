const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
function setup(emails){
 const context={Store:{save(){},state:{emails,prefs:{mailSort:'dateDesc'},user:{name:'Deepak',email:'deepak@example.com'}}},App:{ui:{search:''}},document:{createElement(){return {set innerHTML(value){this._html=value},get textContent(){return this._html?.replace(/<[^>]*>/g,'')||''}}}},window:{}};
 vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/js/mail.js'),'utf8'),context);return context.window.Mail;
}
const message=(id,conversationId,from,date,extra={})=>({id,conversationId,from:{name:from,email:from.toLowerCase().replaceAll(' ','')+'@example.com'},subject:'Project update',body:'message',folder:'inbox',read:true,starred:false,date,to:['deepak@example.com'],labels:[],hasAttachment:false,...extra});
test('messages in one server conversation render as one row, with chronological history',()=>{
 const mail=setup([message('m1','c42','Deepak Sharma',100),message('m2','c42','Asha Rao',200),message('m3','c99','Asha Rao',300)]);
 const rows=mail.threadList('inbox');assert.equal(rows.length,2);const thread=mail.getThread('c42');assert.equal(thread.count,2);assert.deepEqual(thread.ids,['m1','m2']);assert.equal(thread.from.name,'Deepak Sharma, Asha Rao');assert.equal(thread.latest.id,'m2');
});
test('same-subject emails with different conversation IDs remain separate',()=>{
 const mail=setup([message('m1','c1','Asha Rao',100),message('m2','c2','Asha Rao',200)]);assert.equal(mail.threadList('inbox').length,2);
});
test('opening a thread can mark every conversation message read',()=>{
 const mail=setup([message('m1','c42','Asha Rao',100),message('m2','c42','Deepak Sharma',200,{read:false})]);mail.setRead(mail.getThread('c42').ids,true);assert.equal(mail.getThread('c42').unreadCount,0);
});
