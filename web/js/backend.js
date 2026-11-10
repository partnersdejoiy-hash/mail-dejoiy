/* Independent Dejoiy Mail client for the server-side mail adapter. */
/* The admin console lives on its own site (admin-mail.…); local and test hosts keep /admin. */
const ADMIN_URL=(String(location.hostname||'').startsWith('mail.')?location.protocol+'//admin-'+location.host:'')+'/admin';
(function(){
'use strict';
const LOGIN_SLIDES=[
  ['Email on your own domain','Give the whole team addresses like you@yourcompany.com.',
   `<rect x="60" y="40" width="200" height="140" rx="16" style="fill:var(--lg-tone)"/><g class="lg-a-rise"><rect x="80" y="54" width="160" height="104" rx="10" fill="#fff"/><g class="lg-a-type"><rect x="86" y="72" width="148" height="26" rx="13" fill="#121212"/><text x="160" y="89" text-anchor="middle" font-size="10.5" font-weight="700" fill="#fff">you@yourcompany.com</text></g><rect x="96" y="110" width="96" height="6" rx="3" fill="#EDE8EB"/><rect x="96" y="123" width="64" height="6" rx="3" fill="#EDE8EB"/></g><path d="M60 112L160 166L260 112V164A16 16 0 0 1 244 180H76A16 16 0 0 1 60 164Z" style="fill:var(--lg-pink)"/>`],
  ['Mail that lands in the inbox','SPF, DKIM and DMARC records keep your messages trusted, not marked as spam.',
   `<path class="lg-a-pop" d="M160 30L224 54V110C224 148 196 176 160 190C124 176 96 148 96 110V54Z" style="fill:var(--lg-pink)"/><path class="lg-a-draw" pathLength="100" d="M132 110L152 130L190 90" fill="none" stroke="#fff" stroke-width="13" stroke-linecap="round" stroke-linejoin="round"/><g class="lg-a-chip" style="--d:.35s"><rect x="22" y="62" width="62" height="26" rx="13" fill="#121212"/><text x="53" y="79.5" text-anchor="middle" font-size="11" font-weight="700" fill="#fff">SPF</text></g><g class="lg-a-chip" style="--d:.5s"><rect x="236" y="92" width="66" height="26" rx="13" fill="#121212"/><text x="269" y="109.5" text-anchor="middle" font-size="11" font-weight="700" fill="#fff">DKIM</text></g><g class="lg-a-chip" style="--d:.65s"><rect x="26" y="146" width="74" height="26" rx="13" fill="#1F6BFF"/><text x="63" y="163.5" text-anchor="middle" font-size="11" font-weight="700" fill="#fff">DMARC</text></g>`],
  ['24 themes, one tap','Pick a colour or a scene and the whole app follows.',
   `<g class="lg-a-fan" style="--r:-14deg"><rect x="85" y="50" width="150" height="112" rx="12" fill="#1F6BFF"/><rect x="99" y="66" width="60" height="7" rx="3.5" fill="#fff" opacity=".8"/></g><g class="lg-a-fan" style="--r:14deg"><rect x="85" y="50" width="150" height="112" rx="12" style="fill:var(--lg-pink)"/><rect x="99" y="66" width="60" height="7" rx="3.5" fill="#fff" opacity=".8"/></g><g class="lg-a-fan" style="--r:0deg"><rect x="85" y="50" width="150" height="112" rx="12" fill="#121212"/><rect x="99" y="66" width="70" height="7" rx="3.5" fill="#fff"/><rect x="99" y="86" width="122" height="6" rx="3" fill="#fff" opacity=".35"/><rect x="99" y="100" width="100" height="6" rx="3" fill="#fff" opacity=".35"/><rect x="99" y="114" width="110" height="6" rx="3" fill="#fff" opacity=".35"/><rect x="99" y="136" width="44" height="14" rx="7" style="fill:var(--lg-pink)"/></g>`],
  ['Your inbox on every screen','Phone, tablet or desktop. Install it like an app.',
   `<rect x="44" y="44" width="184" height="118" rx="10" fill="#121212"/><rect x="54" y="54" width="164" height="98" rx="4" fill="#fff"/><rect x="54" y="54" width="42" height="98" style="fill:var(--lg-tone)"/><rect x="104" y="66" width="90" height="6" rx="3" fill="#EDE8EB"/><rect x="104" y="82" width="104" height="6" rx="3" fill="#EDE8EB"/><rect x="104" y="98" width="80" height="6" rx="3" fill="#EDE8EB"/><rect x="104" y="114" width="96" height="6" rx="3" fill="#EDE8EB"/><rect x="28" y="162" width="216" height="12" rx="6" fill="#DAD4D8"/><g class="lg-a-slide"><rect x="232" y="76" width="64" height="118" rx="14" style="fill:var(--lg-pink)"/><rect x="239" y="90" width="50" height="94" rx="6" fill="#fff"/><rect x="245" y="100" width="38" height="5" rx="2.5" fill="#EDE8EB"/><rect x="245" y="112" width="30" height="5" rx="2.5" fill="#EDE8EB"/><rect x="245" y="124" width="34" height="5" rx="2.5" fill="#EDE8EB"/><circle cx="276" cy="170" r="7" fill="#121212"/></g>`]
];
function loginMarkup(admin,configured){
  const slides=LOGIN_SLIDES.map(([title,text,art])=>`<figure class="lg-slide"><svg viewBox="0 0 320 220" aria-hidden="true">${art}</svg><figcaption><h2>${title}</h2><p>${text}</p></figcaption></figure>`).join('');
  const eye='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>';
  return `<div class="lg-bg" aria-hidden="true"><i></i><i></i><i></i></div>
  <main class="lg-card">
    <section class="lg-pane">
      <a class="lg-brand" href="/"><img class="login-lockup on-light" src="assets/brand/dejoiy-mail.svg?v=20261110a" alt="Dejoiy Mail"><img class="login-lockup on-dark" src="assets/brand/dejoiy-mail-on-dark.svg?v=20261110a" alt=""></a>
      <form novalidate data-step="email">
        <h1>${admin?'Sign in to Admin':'Sign in'}</h1>
        <p class="lg-sub">${admin?'to manage your company’s mail':'to open your Dejoiy Mail inbox'}</p>
        <div class="lg-steps">
          <div class="lg-step" data-step="email">
            <label class="lg-field"><span>Email address</span><input name="email" type="email" autocomplete="username" inputmode="email" autocapitalize="off" spellcheck="false" placeholder="you@company.com"></label>
          </div>
          <div class="lg-step" data-step="password">
            <div class="lg-who"><span class="lg-avatar" aria-hidden="true"></span><span class="lg-email"></span><button class="lg-change" type="button">Change</button></div>
            <label class="lg-field"><span>Password</span><span class="lg-pass"><input name="password" type="password" autocomplete="current-password"><button class="lg-eye" type="button" aria-label="Show password" aria-pressed="false">${eye}</button></span></label>
            <p class="lg-hint">Forgot it? Your company administrator can reset it.</p>
          </div>
        </div>
        <p class="lg-alert" role="alert"></p>
        <button class="lg-btn" ${configured?'':'disabled'}><span>Next</span><i aria-hidden="true"></i></button>
        ${configured?'':'<p class="lg-hint">Mail server setup is pending. Ask your administrator to configure it.</p>'}
      </form>
      <p class="lg-signup">New company? <a href="/signup">Create business email</a></p>
    </section>
    <aside class="lg-story" aria-label="About Dejoiy Mail"><div class="lg-slides">${slides}</div>
      <div class="lg-dots">${LOGIN_SLIDES.map(([t],k)=>`<button type="button" aria-label="${t}"></button>`).join('')}</div></aside>
  </main>
  <p class="lg-foot">© ${new Date().getFullYear()} Dejoiy India Private Limited</p>`;
}
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
    const onAdminSite=String(location.hostname||'').startsWith('admin-');
    if(new URLSearchParams(location.search).get('next')==='admin'||onAdminSite){ if(session.user.isAdmin===true){location.replace(ADMIN_URL);return new Promise(()=>{});} if(onAdminSite){location.replace(location.protocol+'//'+location.host.replace(/^admin-/,'')+'/');return new Promise(()=>{});} history.replaceState(null,'','/'); }
    await this.loadAppearance();
    try{const prefs=await this.request('preferences');Store.state.user.name=prefs.name||Store.state.user.name;Store.state.user.signature=prefs.signature;Store.state.user.signatureHtml=prefs.signatureHtml||'';Store.state.vacation=prefs.vacation;}catch(e){alert(e.message+' Account preferences could not be loaded.');}
    try{this.avatars=(await this.request('avatars')).avatars||{};}catch(_){this.avatars={};}
    await Settings.load();
    try{await this.sync();}catch(e){alert(e.message+' Use Refresh to retry.');}
    this.install();
    // The company box is named by its admins; show that name in the menu.
    this.request('updates').then(v=>{App.companyName=v.company?.name;App.refreshNav();}).catch(()=>{});
  },
  async login(){
    // First visit on this device: show the landing page; "Sign in" there comes back with ?signin.
    if(location.pathname==='/'&&!/[?&](signin|next)\b/.test(location.search)){
      let known=false; try{known=localStorage.getItem('dm-signed-in')==='1';}catch(_){}
      if(!known){location.replace('/home');return new Promise(()=>{});}
    }
    const config=await this.request('config');
    const admin=location.pathname.startsWith('/admin')||/[?&]next=admin\b/.test(location.search);
    return new Promise(resolve=>{
      const layer=document.createElement('div'); layer.className='lg-root';
      layer.innerHTML=loginMarkup(admin,config.configured);
      Themes.apply();
      document.body.appendChild(layer); if(window.DmSplash)DmSplash.hide(); if(window.DejoiyAccent)DejoiyAccent.recolour(layer);
      const form=layer.querySelector('form'),email=form.elements.email,pass=form.elements.password,btn=form.querySelector('.lg-btn'),
        label=btn.querySelector('span'),alert=form.querySelector('[role=alert]'),card=layer.querySelector('.lg-card');
      let step='email';
      const shake=()=>{card.classList.remove('lg-shake');void card.offsetWidth;card.classList.add('lg-shake');};
      const go=next=>{step=next;form.dataset.step=next;alert.textContent='';
        form.querySelectorAll('.lg-step').forEach(s=>{s.inert=s.dataset.step!==next;});
        label.textContent=next==='email'?'Next':'Sign in';(next==='email'?email:pass).focus({preventScroll:true});};
      form.querySelector('.lg-change').addEventListener('click',()=>{pass.value='';go('email');});
      form.querySelector('.lg-eye').addEventListener('click',e=>{const show=pass.type==='password';pass.type=show?'text':'password';
        e.currentTarget.setAttribute('aria-pressed',show);e.currentTarget.setAttribute('aria-label',show?'Hide password':'Show password');});
      form.addEventListener('submit',async e=>{e.preventDefault();
        if(step==='email'){
          email.value=email.value.trim();
          if(!email.value||!email.checkValidity()){alert.textContent='Enter your full email address, like you@company.com.';shake();email.focus();return;}
          form.querySelector('.lg-email').textContent=email.value;form.querySelector('.lg-avatar').textContent=email.value[0].toUpperCase();
          return go('password');
        }
        if(!pass.value){alert.textContent='Enter your password.';shake();return;}
        btn.disabled=true;form.classList.add('is-busy');
        try{
          const result=await this.request('login',{email:email.value,password:pass.value});
          const address=email.value;form.reset();clearInterval(timer);try{localStorage.setItem('dm-signed-in','1');}catch(_){}
          if(window.DmSplash)DmSplash.show('Loading… '+address);
          layer.classList.add('lg-out');setTimeout(()=>layer.remove(),450);resolve(result);
        }catch(err){alert.textContent=err.message;pass.value='';btn.disabled=!config.configured;form.classList.remove('is-busy');shake();pass.focus();}
      });
      go('email');
      // Story carousel: advances on its own unless the visitor is pointing at it or prefers less motion.
      const story=layer.querySelector('.lg-story'),slides=[...layer.querySelectorAll('.lg-slide')],dots=[...layer.querySelectorAll('.lg-dots button')];
      let at=0;
      const show=i=>{at=(i+slides.length)%slides.length;slides.forEach((s,k)=>{s.classList.toggle('is-on',k===at);s.setAttribute('aria-hidden',k!==at);});
        dots.forEach((d,k)=>d.setAttribute('aria-current',k===at));};
      dots.forEach((d,k)=>d.addEventListener('click',()=>show(k)));show(0);
      const timer=matchMedia('(prefers-reduced-motion: reduce)').matches?0:setInterval(()=>{if(!story.matches(':hover,:focus-within'))show(at+1);},5200);
    });
  },
  install(){
    App.NAV=App.NAV.filter(([route])=>['mail:inbox','news','company','contacts','admin','settings'].includes(route) && (route!=='admin'||Store.state.user?.isAdmin===true));
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
      if(this.route==='admin'&&Store.state.user?.isAdmin===true){location.assign(ADMIN_URL);return;}
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
    if(saved&&saved.theme){const p=Store.state.prefs;Object.assign(p,{theme:saved.theme,brightness:saved.brightness,glass:saved.glass||{},customBg:saved.customBg||'',accent:saved.accent||''});Store.save();Themes.apply();}
    else this.saveAppearance(true);
  },
  saveAppearance(now){
    clearTimeout(this.appearanceTimer);
    const send=()=>{const p=Store.state.prefs;this.request('appearance',{theme:p.theme,brightness:p.brightness,glass:p.glass||{},customBg:p.customBg||'',accent:p.accent||''}).catch(e=>App.toast(e.message+' Your theme is kept on this device only.'));};
    if(now)send();else this.appearanceTimer=setTimeout(send,500);
  },
  async logout(){await this.request('logout',{});location.reload();}
};
window.Live=Live;
})();
