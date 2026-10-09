/* Independent Dejoiy Mail client for the server-side mail adapter. */
(function(){
'use strict';
const Live={enabled:!!window.DEJOIY_LIVE,csrf:'',more:false,avatars:{},
  async request(path,data){
    const response=await fetch('/api/'+path,{method:data===undefined?'GET':'POST',credentials:'same-origin',headers:data===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':this.csrf},body:data===undefined?undefined:JSON.stringify(data)});
    const result=await response.json();
    if(!response.ok){ if(response.status===401&&!['login','session'].includes(path)&&!path.startsWith('admin')) location.reload(); throw new Error(result.error||'Mail request failed'); }
    return result;
  },
  async sync(offset=0){
    const result=await this.request(offset?'mail?offset='+offset:'mail');
    Store.state.emails=offset?[...new Map([...Store.state.emails,...result.emails].map(m=>[m.id,m])).values()]:result.emails;
    this.more=result.more;this.nextOffset=result.nextOffset;
    if(this.note){this.note.querySelector('span').textContent=`Connected mailbox · ${Store.state.emails.length} messages loaded`;this.note.querySelector('button').hidden=!this.more;}
    return {folder:'inbox',subject:'Mailbox refreshed'};
  },
  async boot(){
    if(!this.enabled)return;
    let prefs=Store.state.prefs;
    try { prefs=JSON.parse(localStorage.getItem('dejoiy-live-prefs')) || prefs; } catch (_) {}
    if(!prefs.mailUiVersion)prefs={...prefs,brightness:prefs.theme==='aol'&&!prefs.customBg?'light':prefs.brightness,messageLayout:'list',inboxSpacing:'comfortable',messageTabs:false,largeText:false,mailUiVersion:2,mailSort:'dateDesc'};
    if(!prefs.designVersion){if(prefs.theme==='aol'&&!prefs.customBg)prefs={...prefs,theme:'pearl',brightness:'light'};prefs.designVersion=3;}
    Store.state={version:1,user:{name:'',email:'',signature:''},emails:[],contacts:[],events:[],todos:[],notes:[],chats:{},filters:[],blocked:[],allowed:[],vacation:{on:false},prefs,admin:{org:'',users:[],domains:[]},poolIdx:0};
    Store.save=()=>{try{localStorage.setItem('dejoiy-live-prefs',JSON.stringify(Store.state.prefs));}catch(_){}}; Store.reset=()=>location.reload();
    let session;
    try{session=await this.request('session');}catch(_){session=await this.login();}
    this.csrf=session.csrf; Store.state.user=session.user;
    if(new URLSearchParams(location.search).get('next')==='admin'){ if(session.user.isAdmin===true){location.replace('/admin');return;} history.replaceState(null,'','/'); }
    await this.loadAppearance();
    try{const prefs=await this.request('preferences');Store.state.user.name=prefs.name||Store.state.user.name;Store.state.user.signature=prefs.signature;Store.state.user.signatureHtml=prefs.signatureHtml||'';Store.state.vacation=prefs.vacation;}catch(e){alert(e.message+' Account preferences could not be loaded.');}
    try{this.avatars=(await this.request('avatars')).avatars||{};}catch(_){this.avatars={};}
    await Settings.load();
    try{await this.sync();}catch(e){alert(e.message+' Use Refresh to retry.');}
    this.install();
  },
  async login(){
    const config=await this.request('config');
    return new Promise(resolve=>{
      const layer=document.createElement('div'); layer.className='live-login';
      layer.innerHTML=`<section class="login-story"><a class="login-wordmark" href="/">dmail<span>.</span></a><div><span class="login-kicker">A LITTLE LESS NOISE. A LOT MORE SPACE.</span><h2>Make room for<br>what matters.</h2><p>Your conversations, ideas and next big thing.<br>All beautifully together.</p><div class="login-illustration" aria-hidden="true"><div class="letter letter-back"></div><div class="letter letter-front"><span>Good things are coming.</span><i></i><i></i><i></i><b>✦</b></div><span class="letter-seal">d.</span></div></div><small>DEJOIY · YOUR WORK, CONNECTED.</small></section><form class="card"><span class="login-kicker">WELCOME BACK</span><h1>${location.pathname.startsWith('/admin')?'Administration':'Your inbox awaits.'}</h1><p>Sign in to your Dmail account</p><label>Email<input name="email" type="email" autocomplete="username" required></label><label>Password<input name="password" type="password" autocomplete="current-password" required></label><p role="alert"></p><button class="btn primary" ${config.configured?'':'disabled'}>Sign in</button><small>${config.configured?'':'Mail server setup is pending. Ask your administrator to configure it.'}</small><p class="login-signup">New company? <a href="/signup">Create business email</a></p></form>`;
      Themes.apply();
    document.body.appendChild(layer); const form=layer.querySelector('form');
      form.addEventListener('submit',async e=>{e.preventDefault(); const button=form.querySelector('button'); button.disabled=true;
        try{const result=await this.request('login',{email:form.elements.email.value,password:form.elements.password.value});form.reset();layer.remove();resolve(result);}
        catch(err){form.querySelector('[role=alert]').textContent=err.message;form.elements.password.value='';button.disabled=false;}
      });
    });
  },
  install(){
    App.NAV=App.NAV.filter(([route])=>['mail:inbox','contacts','admin','settings'].includes(route) && (route!=='admin'||Store.state.user?.isAdmin===true));
    const local={}; for(const name of ['setRead','toggleStar','toggleImportant','moveTo','deleteForever','addLabel'])local[name]=Mail[name].bind(Mail);
    let queue=Promise.resolve();
    const mutate=(data,apply)=>{const job=queue.then(async()=>{await this.request('action',data);apply();App.refreshNav();if(App.route==='mail')App.render();});queue=job.catch(()=>{});return job;};
    const ids=value=>Array.isArray(value)?value:[value];
    Mail.setRead=(id,value=true)=>{const messageIds=(Array.isArray(id)?id:[id]).filter(messageId=>Mail.get(messageId));const next=value!==false;if(!messageIds.length||messageIds.every(messageId=>Mail.get(messageId).read===next))return Promise.resolve();return mutate({ids:messageIds,op:'read',value:next},()=>local.setRead(messageIds,next));};
    Mail.toggleStar=id=>{const value=!Mail.get(id).starred;return mutate({ids:[id],op:'star',value},()=>{Mail.get(id).starred=value;});};
    Mail.toggleImportant=id=>{const value=!Mail.get(id).important;return mutate({ids:[id],op:'important',value},()=>{Mail.get(id).important=value;});};
    Mail.moveTo=(value,folder)=>mutate({ids:ids(value),op:'move',folder},()=>local.moveTo(value,folder));
    Mail.deleteForever=value=>mutate({ids:ids(value),op:'delete'},()=>local.deleteForever(value));
    Mail.emptyTrash=()=>mutate({op:'empty_trash'},()=>{Store.state.emails=Store.state.emails.filter(e=>e.folder!=='trash');});
    Mail.addLabel=(value,label)=>mutate({ids:ids(value),op:'label',label},()=>local.addLabel(value,label));
    Mail.checkMail=async()=>{const result=await this.sync();App.render();if(this.more)App.toast('More messages are available. Use Load more to include them in search and counts.');return result;};
    Mail.send=async data=>{const result=await this.request('send',data);try{await this.sync();}catch(_){App.toast('Message accepted; refresh the mailbox to see it.');}return result;};
    Mail.saveDraft=async data=>{const result=await this.request('draft',data);try{await this.sync();}catch(_){App.toast('Draft accepted; refresh the mailbox to see it.');}return result;};
    Mail.storage=()=>{const a=Settings.account;if(!a||!a.quota)return {used:a?(a.used/1048576).toFixed(1):'—',total:0,pct:0};const mb=a.used/1048576;return {used:mb.toFixed(1),total:a.quota/1048576,pct:Math.min(100,Math.round(a.used/a.quota*1000)/10)};};
    const original=App.render.bind(App);
    App.render=function(){
      if(this.route==='admin'&&Store.state.user?.isAdmin===true){location.assign('/admin');return;}
      if(this.route==='admin'&&Store.state.user?.isAdmin!==true){document.getElementById('view').innerHTML='<div class="empty-note"><h1>Administrator access required</h1><p>This mailbox does not have administration permissions.</p><a href="#/mail:inbox">Return to your inbox</a></div>';this.refreshNav();return;}
      if(['calendar','notes','chat','today'].includes(this.route)){
        document.getElementById('view').innerHTML='<div class="empty-note">This feature is not connected to your business mailbox yet. <a href="#/mail:inbox">Open Mail</a></div>';this.refreshNav();return;
      }original();
    };
    const adminRoute=location.pathname.startsWith('/admin') || location.hash==='#/admin';
    App.route=adminRoute?'admin':'mail';location.hash=adminRoute?'#/admin':'#/mail:inbox';
    window.addEventListener('unhandledrejection',e=>{e.preventDefault();App.toast(e.reason?.message||'Mail operation failed');});
    document.body.classList.add('live-mode');
    const note=document.createElement('div');note.className='live-note';
    note.innerHTML=`<span>Connected mailbox · ${Store.state.emails.length} messages loaded</span> <button class="btn sm" ${this.more?'':'hidden'}>Load more</button>`;
    this.note=note;
    note.querySelector('button').addEventListener('click',async event=>{const button=event.currentTarget;button.disabled=true;try{await this.sync(this.nextOffset);App.refreshNav();if(App.route==='mail'||App.route==='search')App.render();}catch(e){App.toast(e.message);}finally{button.disabled=false;}});
    document.getElementById('mail-status').appendChild(note);
  },
  /* The mailbox's saved look wins over whatever this browser last showed. The first time a
     mailbox has nothing saved, the look already on this device is adopted and stored for it. */
  async loadAppearance(){
    let saved={};
    try{saved=await this.request('appearance');}catch(_){return;}
    if(saved&&saved.theme){const p=Store.state.prefs;Object.assign(p,{theme:saved.theme,brightness:saved.brightness,glass:saved.glass||{},customBg:saved.customBg||''});Store.save();Themes.apply();}
    else this.saveAppearance(true);
  },
  saveAppearance(now){
    clearTimeout(this.appearanceTimer);
    const send=()=>{const p=Store.state.prefs;this.request('appearance',{theme:p.theme,brightness:p.brightness,glass:p.glass||{},customBg:p.customBg||''}).catch(e=>App.toast(e.message+' Your theme is kept on this device only.'));};
    if(now)send();else this.appearanceTimer=setTimeout(send,500);
  },
  async logout(){await this.request('logout',{});location.reload();}
};
window.Live=Live;
})();
