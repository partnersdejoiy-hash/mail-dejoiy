/* Independent Dejoiy Mail client for the server-side Zimbra adapter. */
(function(){
'use strict';
const Live={enabled:!!window.DEJOIY_LIVE,csrf:'',more:false,
  async request(path,data){
    const response=await fetch('/api/'+path,{method:data===undefined?'GET':'POST',credentials:'same-origin',headers:data===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':this.csrf},body:data===undefined?undefined:JSON.stringify(data)});
    const result=await response.json();
    if(!response.ok){ if(response.status===401&&!['login','session'].includes(path)) location.reload(); throw new Error(result.error||'Mail request failed'); }
    return result;
  },
  async sync(){const result=await this.request('mail'); Store.state.emails=result.emails; this.more=result.more; return {folder:'inbox',subject:'Mailbox refreshed'};},
  async boot(){
    if(!this.enabled)return;
    let prefs=Store.state.prefs;
    try { prefs=JSON.parse(localStorage.getItem('dejoiy-live-prefs')) || prefs; } catch (_) {}
    Store.state={version:1,user:{name:'',email:'',signature:''},emails:[],contacts:[],events:[],todos:[],notes:[],chats:{},filters:[],blocked:[],allowed:[],vacation:{on:false},prefs,admin:{org:'',users:[],domains:[]},poolIdx:0};
    Store.save=()=>{try{localStorage.setItem('dejoiy-live-prefs',JSON.stringify(Store.state.prefs));}catch(_){}}; Store.reset=()=>location.reload();
    let session;
    try{session=await this.request('session');}catch(_){session=await this.login();}
    this.csrf=session.csrf; Store.state.user=session.user;
    try{await this.sync();}catch(e){alert(e.message+' Use Refresh to retry.');}
    this.install();
  },
  async login(){
    const config=await this.request('config');
    return new Promise(resolve=>{
      const layer=document.createElement('div'); layer.className='live-login';
      layer.innerHTML=`<form class="card"><h1>Dmail</h1><p>Sign in to your business mailbox</p><label>Email<input name="email" type="email" autocomplete="username" required></label><label>Password<input name="password" type="password" autocomplete="current-password" required></label><p role="alert"></p><button class="btn primary" ${config.configured?'':'disabled'}>Sign in</button><small>${config.configured?'':'Mail server setup is pending. Ask your administrator to configure it.'}</small></form>`;
      document.body.appendChild(layer); const form=layer.querySelector('form');
      form.addEventListener('submit',async e=>{e.preventDefault(); const button=form.querySelector('button'); button.disabled=true;
        try{const result=await this.request('login',{email:form.elements.email.value,password:form.elements.password.value});form.reset();layer.remove();resolve(result);}
        catch(err){form.querySelector('[role=alert]').textContent=err.message;form.elements.password.value='';button.disabled=false;}
      });
    });
  },
  install(){
    App.NAV=App.NAV.filter(([route])=>['mail:inbox','settings'].includes(route));
    const local={}; for(const name of ['setRead','toggleStar','toggleImportant','moveTo','deleteForever'])local[name]=Mail[name].bind(Mail);
    let queue=Promise.resolve();
    const mutate=(data,apply)=>{const job=queue.then(async()=>{await this.request('action',data);apply();App.refreshNav();if(App.route==='mail')App.render();});queue=job.catch(()=>{});return job;};
    const ids=value=>Array.isArray(value)?value:[value];
    Mail.setRead=(id,value=true)=>Mail.get(id)?.read===(value!==false)?Promise.resolve():mutate({ids:[id],op:'read',value:value!==false},()=>local.setRead(id,value));
    Mail.toggleStar=id=>{const value=!Mail.get(id).starred;return mutate({ids:[id],op:'star',value},()=>{Mail.get(id).starred=value;});};
    Mail.toggleImportant=id=>{const value=!Mail.get(id).important;return mutate({ids:[id],op:'important',value},()=>{Mail.get(id).important=value;});};
    Mail.moveTo=(value,folder)=>mutate({ids:ids(value),op:'move',folder},()=>local.moveTo(value,folder));
    Mail.deleteForever=value=>mutate({ids:ids(value),op:'delete'},()=>local.deleteForever(value));
    Mail.emptyTrash=()=>{const selected=Store.state.emails.filter(e=>e.folder==='trash').map(e=>e.id);return selected.length?Mail.deleteForever(selected):Promise.resolve();};
    Mail.addLabel=()=>{throw new Error('Server labels are not connected yet.');};
    Mail.checkMail=async()=>{const result=await this.sync();App.render();if(this.more)App.toast('Showing the latest 50 messages; search and counts cover this loaded window.');return result;};
    Mail.send=async data=>{const result=await this.request('send',data);try{await this.sync();}catch(_){App.toast('Message accepted; refresh the mailbox to see it.');}return result;};
    Mail.saveDraft=async data=>{const result=await this.request('draft',data);try{await this.sync();}catch(_){App.toast('Draft accepted; refresh the mailbox to see it.');}return result;};
    Mail.storage=()=>({used:'—',total:'—',pct:0});
    const original=App.render.bind(App);
    App.render=function(){
      if(['admin','calendar','contacts','notes','chat','today'].includes(this.route)){
        document.getElementById('view').innerHTML='<div class="empty-note">This feature is not connected to your business mailbox yet. <a href="#/mail:inbox">Open Mail</a></div>';this.refreshNav();return;
      }original();
    };
    App.route='mail';location.hash='#/mail:inbox';
    window.addEventListener('unhandledrejection',e=>{e.preventDefault();App.toast(e.reason?.message||'Mail operation failed');});
    document.body.classList.add('live-mode');
    const note=document.createElement('div');note.className='live-note';note.textContent='Connected mailbox · latest 50 messages · text-only mail · attachment upload pending';document.getElementById('view').before(note);
  },
  async logout(){await this.request('logout',{});location.reload();}
};
window.Live=Live;
})();
