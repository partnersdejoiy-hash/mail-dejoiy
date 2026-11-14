// android-links.js: inside the Android app, links to the other Dejoiy site go to Android. Run: node --test tests/test_android_links.cjs
const test=require('node:test');const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');const path=require('node:path');
function load(href, referrer=''){
  const store={}, listeners=[], loc=new URL(href);
  const context={URL,URLSearchParams,encodeURIComponent,window:{},location:{search:loc.search,href:loc.href,host:loc.host},
    document:{referrer,addEventListener:(t,f)=>listeners.push(f)},sessionStorage:{getItem:k=>store[k]??null,setItem:(k,v)=>{store[k]=String(v);}}};
  vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/js/android-links.js'),'utf8'),context);
  const click=href=>{ let stopped=false; const a={href:new URL(href,loc.href).href}; const e={target:{closest:()=>a},preventDefault(){stopped=true;},stopPropagation(){}}; listeners.forEach(f=>f(e)); return stopped; };
  return {links:context.window.DejoiyLinks, location:context.location, click, listeners};
}
test('in a normal browser nothing changes',()=>{
  const c=load('https://admin-mail.dejoiy.com/admin');
  assert.equal(c.links.inApp(),false); assert.equal(c.listeners.length,0); assert.equal(c.links.open('https://mail.dejoiy.com/'),false);
});
test('the admin app hands mail links to Android, keeping the page and the fallback',()=>{
  const c=load('https://admin-mail.dejoiy.com/admin?source=android');
  assert.equal(c.links.inApp(),true);
  assert.equal(c.click('https://mail.dejoiy.com/#/desk:T-0007'),true);
  assert.equal(c.location.href,'intent://mail.dejoiy.com/#/desk:T-0007#Intent;scheme=https;S.browser_fallback_url='+encodeURIComponent('https://mail.dejoiy.com/#/desk:T-0007')+';end');
});
test('links on its own site and to other sites are left alone',()=>{
  const c=load('https://mail.dejoiy.com/','android-app://com.dejoiy.mail/');
  assert.equal(c.links.inApp(),true);
  assert.equal(c.click('/help/user-guide.html'),false); assert.equal(c.click('https://example.com/'),false); assert.equal(c.click('http://admin-mail.dejoiy.com/admin'),false);
  assert.equal(c.links.open('https://admin-mail.dejoiy.com/admin'),true); assert.match(c.location.href,/^intent:\/\/admin-mail\.dejoiy\.com\/admin#Intent;scheme=https;/);
});
