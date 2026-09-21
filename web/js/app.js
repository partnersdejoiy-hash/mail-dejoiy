/* ============ Dejoiy Mail — app.js : router, dialogs, nav, shortcuts, sounds ============ */
(function(){
"use strict";

const viewEl = ()=> document.getElementById("view");

const App = {
  route: "today", arg: null,
  ui: { folder:"inbox", search:"", sel:new Set(), tabs:[], activeTab:null },

  /* ---------------- routing ---------------- */
  go(route){
    location.hash = "#/" + route;
  },
  parse(){
    const h = (location.hash||"#/today").replace(/^#\//,"");
    const i = h.indexOf(":");
    this.route = i<0 ? h : h.slice(0,i);
    this.arg = i<0 ? null : h.slice(i+1);
    this.render();
  },
  render(){
    document.body.classList.remove("nav-open","reader-open","chat-open");
    const el = viewEl(), r = this.route, a = this.arg;
    window.scrollTo(0,0); el.scrollTop = 0;
    document.getElementById("global-search").value = this.ui.search || "";
    try{
      if(r==="today") Views.today(el);
      else if(r==="mail") Views.mail(el, a||undefined);
      else if(r==="compose") Views.compose(el, a||"new");
      else if(r==="calendar") Views.calendar(el);
      else if(r==="contacts") Views.contacts(el);
      else if(r==="notes") Views.notes(el);
      else if(r==="chat") Views.chat(el, a||undefined);
      else if(r==="admin") Views.admin(el);
      else if(r==="settings") Views.settings(el, a||undefined);
      else if(r==="search") this.renderSearch(el, a);
      else Views.today(el);
    }catch(err){ console.error(err); el.innerHTML = `<div class="empty-note">Something went wrong rendering this view. (${esc(err.message)})</div>`; }
    this.refreshNav();
    this.applyTilt();
  },

  /* ---------- 3D tilt (v0.2) ---------- */
  tiltInit(){
    let cur=null;
    document.addEventListener("pointermove", e=>{
      const t = (e.target && e.target.closest) ? e.target.closest(".tilt-3d") : null;
      if(t!==cur){ if(cur) cur.style.transform=""; cur=t; }
      if(cur){
        const r=cur.getBoundingClientRect();
        const x=(e.clientX-r.left)/r.width-.5, y=(e.clientY-r.top)/r.height-.5;
        cur.style.transform=`perspective(900px) rotateX(${(-y*7).toFixed(2)}deg) rotateY(${(x*9).toFixed(2)}deg) translateZ(6px)`;
      }
    }, {passive:true});
    document.addEventListener("pointerout", ()=>{ if(cur){ cur.style.transform=""; cur=null; } }, true);
  },
  applyTilt(){
    try{ viewEl().querySelectorAll(".card").forEach(c=>c.classList.add("tilt-3d")); }catch(_){}
  },
  /* brand logo uploaded from settings (v0.2) */
  applyLogo(){
    const mark=document.querySelector(".brand-mark"); if(!mark) return;
    const logo=Store.state.prefs.customLogo;
    if(logo){ if(!mark.dataset.logoApplied){ mark.dataset.logoApplied="1"; mark.innerHTML=`<img class="brand-logo" src="${logo}" alt="Dejoiy Mail logo">`; } }
    else if(mark.dataset.logoApplied){ delete mark.dataset.logoApplied; mark.textContent="✉"; }
  },

  renderSearch(el, q){
    const results = Mail.advancedSearch({has:q});
    el.innerHTML = `<div class="view-head"><h1>🔎 Search</h1><span class="sub">${results.length} result${results.length===1?"":"s"} for “${esc(q)}”</span></div>
      ${results.length ? `<div class="card" style="padding:6px">`+results.map(e=>`
        <div class="msg-row ${e.read?"":"unread"}" data-sr="${e.id}" role="button" tabindex="0">
          <div class="m-main"><div class="m-top"><span class="m-from">${esc(e.from.name)}</span><span class="m-date">${fmtDate(e.date)}</span></div>
          <div class="m-subj">${esc(e.subject)}</div><div class="m-snip">${esc(Mail.folderName(e.folder))}</div></div></div>`).join("")+`</div>`
      : `<div class="empty-note">No messages matched “${esc(q)}”.</div>`}`;
    el.querySelectorAll("[data-sr]").forEach(r2=> r2.addEventListener("click", ()=>{
      const e = Mail.get(r2.dataset.sr);
      this.ui.folder = e.folder; this.go("mail:"+e.folder);
      setTimeout(()=>{ const ui=this.ui; if(ui._mail) ui._mail.openTab(e.id); }, 80);
    }));
  },

  /* ---------------- navigation chrome ---------------- */
  NAV: [
    ["today","🏠","Today"],["mail:inbox","📥","Inbox"],["calendar","📅","Calendar"],
    ["contacts","👥","Contacts"],["notes","📝","Notes"],["chat","💬","Chat"],
    ["admin","🛡️","Admin"],["settings","⚙️","Settings"]
  ],
  refreshNav(){
    const c = Mail.counts(), nav = document.getElementById("main-nav");
    nav.innerHTML = this.NAV.map(([r,ico,label])=>{
      const active = this.route===(r.includes(":")?r.split(":")[0]:r) && (!r.includes(":") || this.ui.folder===r.split(":")[1]);
      const badge = r==="mail:inbox" && c.unread ? `<span class="n-count">${c.unread}</span>` : "";
      return `<button class="nav-item ${active?"active":""}" data-nav="${r}"><span class="n-ico">${ico}</span>${label}${badge}</button>`;
    }).join("");
    nav.querySelectorAll("[data-nav]").forEach(b=> b.addEventListener("click", ()=>{
      this.ui.search=""; document.getElementById("global-search").value="";
      this.go(b.dataset.nav); document.body.classList.remove("nav-open");
    }));
    const bn = document.getElementById("bottomnav");
    const items = [["today","🏠","Today"],["mail:inbox","📥","Mail"],["compose:new","✎","Compose"],["calendar","📅","Cal"],["chat","💬","Chat"]];
    bn.innerHTML = items.map(([r,ico,label])=>{
      const active = this.route===(r.includes(":")?r.split(":")[0]:r);
      return `<button data-nav="${r}" class="${active?"active":""}"><span class="b-ico">${ico}</span>${label}</button>`;
    }).join("");
    bn.querySelectorAll("[data-nav]").forEach(b=> b.addEventListener("click", ()=>{ this.go(b.dataset.nav); }));
    const st = Mail.storage();
    document.getElementById("storage-fill").style.width = st.pct+"%";
    document.getElementById("storage-label").textContent = `${st.used} MB of ${(st.total/1024).toFixed(0)} GB used`;
    document.getElementById("account-btn").textContent = initials(Store.state.user.name);
  },

  /* ---------------- dialogs ---------------- */
  dialog({title, body, actions, wide}){
    const root = document.getElementById("dialog-root");
    root.innerHTML = `<div class="dlg-back"><div class="dlg ${wide?"wide":""}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
      <div class="dlg-head"><h2>${esc(title)}</h2><button class="icon-btn sm" id="dlg-x" aria-label="Close">×</button></div>
      <div class="dlg-body">${body}</div>
      ${actions&&actions.length?`<div class="dlg-foot">${actions.map((a,i)=>`<button class="btn ${a.primary?"primary":""}" data-act="${i}">${esc(a.label)}</button>`).join("")}</div>`:""}
    </div></div>`;
    const close = ()=>{ root.innerHTML=""; document.removeEventListener("keydown", escHandler); };
    const escHandler = e=>{ if(e.key==="Escape") close(); };
    document.addEventListener("keydown", escHandler);
    root.querySelector(".dlg-back").addEventListener("click", e=>{ if(e.target.classList.contains("dlg-back")) close(); });
    root.querySelector("#dlg-x").addEventListener("click", close);
    (actions||[]).forEach((a,i)=> root.querySelector(`[data-act="${i}"]`).addEventListener("click", ()=>{
      const r = a.fn && a.fn(); if(r!==false) close();
    }));
    this.closeDialog = close;
    const first = root.querySelector("input,textarea,select"); if(first) setTimeout(()=>first.focus(), 50);
  },
  closeDialog(){ document.getElementById("dialog-root").innerHTML=""; },
  confirm(msg, fn){
    this.dialog({title:"Please confirm", body:`<p>${esc(msg)}</p>`,
      actions:[{label:"Cancel"},{label:"Yes, do it", primary:true, fn}]});
  },
  promptDialog(title, label, initial, fn){
    this.dialog({title, body:`<div class="field"><label>${esc(label)}</label><input type="text" id="pd-inp" value="${esc(initial||"")}"></div>`,
      actions:[{label:"Cancel"},{label:"OK", primary:true, fn:()=>{ fn(document.getElementById("pd-inp").value); }}]});
    document.getElementById("pd-inp").addEventListener("keydown", e=>{
      if(e.key==="Enter"){ fn(e.target.value); this.closeDialog(); } });
  },
  menu(anchor, items){
    document.querySelectorAll(".menu").forEach(m=>m.remove());
    const r = anchor.getBoundingClientRect();
    const m = document.createElement("div"); m.className="menu";
    m.innerHTML = items.map((it,i)=> it.sep?`<div class="m-sep"></div>`:`<button data-mi="${i}">${esc(it.label)}</button>`).join("");
    m.style.top = Math.min(innerHeight-220, r.bottom+6)+"px";
    m.style.left = Math.max(8, Math.min(innerWidth-220, r.left))+"px";
    document.body.appendChild(m);
    m.querySelectorAll("[data-mi]").forEach(b=> b.addEventListener("click", ()=>{ m.remove(); items[+b.dataset.mi].fn(); }));
    const away = e=>{ if(!m.contains(e.target)){ m.remove(); document.removeEventListener("click", away); } };
    setTimeout(()=>document.addEventListener("click", away), 10);
  },

  /* ---------------- toast + sound ---------------- */
  toast(msg){
    const t = document.createElement("div"); t.className="toast"; t.textContent = msg;
    const root = document.getElementById("toast-root"); root.appendChild(t);
    setTimeout(()=>{ t.style.opacity="0"; t.style.transition="opacity .3s"; setTimeout(()=>t.remove(), 320); }, 2600);
  },
  sound(kind){
    if(!Store.state.prefs.sounds) return;
    try{
      const ctx = new (window.AudioContext||window.webkitAudioContext)();
      const notes = kind==="sent" ? [523,659,784] : [784,988];
      notes.forEach((f,i)=>{
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.type="sine"; o.frequency.value=f; g.gain.value=.12;
        o.connect(g); g.connect(ctx.destination);
        const t = ctx.currentTime + i*.12;
        o.start(t); g.gain.exponentialRampToValueAtTime(.001, t+.35); o.stop(t+.4);
      });
    }catch(e){}
  },

  /* ---------------- advanced search ---------------- */
  advSearch(){
    this.dialog({title:"Advanced search", wide:true, body:`
      <div class="grid c2">
        <div class="field"><label>From</label><input type="text" id="as-from"></div>
        <div class="field"><label>To</label><input type="text" id="as-to"></div>
        <div class="field"><label>Subject</label><input type="text" id="as-subj"></div>
        <div class="field"><label>Includes words</label><input type="text" id="as-has"></div>
        <div class="field"><label>Excludes words</label><input type="text" id="as-hasnt"></div>
        <div class="field"><label>Has attachment</label><select id="as-att"><option value="">Any</option><option value="1">Yes</option></select></div>
        <div class="field"><label>After</label><input type="date" id="as-after"></div>
        <div class="field"><label>Before</label><input type="date" id="as-before"></div>
      </div>`,
      actions:[{label:"Close"},
        {label:"Create filter from this", fn:()=>{
          const f = Filters.blank();
          f.name = "Search-based filter";
          ["from","to","subject"].forEach(k=> f.criteria[k]=document.getElementById("as-"+k).value.trim());
          f.criteria.hasWords = document.getElementById("as-has").value.trim();
          f.criteria.noWords = document.getElementById("as-hasnt").value.trim();
          f.criteria.hasAttachment = !!document.getElementById("as-att").value;
          f.criteria.after = document.getElementById("as-after").value;
          f.criteria.before = document.getElementById("as-before").value;
          Store.state.filters.push(f); Store.save(); this.closeDialog();
          this.go("settings:filters"); this.toast("Filter created — edit its actions, then save.");
        }},
        {label:"Search", primary:true, fn:()=>{
          const v = id=>document.getElementById("as-"+id).value.trim();
          const results = Mail.advancedSearch({from:v("from"),to:v("to"),subject:v("subj"),has:v("has"),hasnt:v("hasnt"),
            attach:!!v("att"), after:v("after"), before:v("before")});
          this.closeDialog(); this.showResults(results, "Advanced search");
        }}]});
  },
  showResults(results, title){
    const el = viewEl();
    el.innerHTML = `<div class="view-head"><h1>🔎 ${esc(title)}</h1><span class="sub">${results.length} result${results.length===1?"":"s"}</span></div>
      ${results.length ? `<div class="card" style="padding:6px">`+results.map(e=>`
        <div class="msg-row ${e.read?"":"unread"}" data-sr="${e.id}" role="button" tabindex="0">
          <div class="m-main"><div class="m-top"><span class="m-from">${esc(e.from.name)}</span><span class="m-date">${fmtDate(e.date)}</span></div>
          <div class="m-subj">${esc(e.subject)}</div><div class="m-snip">${esc(Mail.folderName(e.folder))}</div></div></div>`).join("")+`</div>`
      : `<div class="empty-note">No messages matched.</div>`}`;
    el.querySelectorAll("[data-sr]").forEach(r2=> r2.addEventListener("click", ()=>{
      const e = Mail.get(r2.dataset.sr);
      this.ui.folder = e.folder; this.go("mail:"+e.folder);
      setTimeout(()=>{ if(this.ui._mail) this.ui._mail.openTab(e.id); }, 80);
    }));
    this.refreshNav();
  },

  /* ---------------- keyboard ---------------- */
  bindKeys(){
    document.addEventListener("keydown", e=>{
      const t = e.target, typing = t && (t.tagName==="INPUT"||t.tagName==="TEXTAREA"||t.isContentEditable);
      if(e.key==="Escape"){ this.closeDialog(); return; }
      if(typing) return;
      if(e.metaKey||e.ctrlKey||e.altKey) return;
      const k = e.key.toLowerCase();
      const ui = this.ui;
      if(k==="/"){ e.preventDefault(); document.getElementById("global-search").focus(); }
      else if(k==="c"){ this.go("compose:new"); }
      else if(k==="?"){ this.go("settings:shortcuts"); }
      else if(this.route==="mail" && ui._mail){
        if(k==="j") ui._mail.moveSel(1);
        else if(k==="k") ui._mail.moveSel(-1);
        else if(k==="x" && ui.activeTab){ const id=ui.activeTab; ui.sel.has(id)?ui.sel.delete(id):ui.sel.add(id); ui._mail.renderList(); }
        else if(k==="s" && ui.activeTab){ Mail.toggleStar(ui.activeTab); ui._mail.renderList(); this.refreshNav(); }
        else if(k==="e" && ui.activeTab){ Mail.archive(ui.activeTab); ui._mail.closeTab(ui.activeTab); ui._mail.renderList(); this.refreshNav(); }
        else if(k==="#" && ui.activeTab){ Mail.trash(ui.activeTab); ui._mail.closeTab(ui.activeTab); ui._mail.renderList(); this.refreshNav(); }
        else if(k==="r" && ui.activeTab){ this.go("compose:reply:"+ui.activeTab); }
        else if(k==="f" && ui.activeTab){ this.go("compose:forward:"+ui.activeTab); }
      }
    });
    const gs = document.getElementById("global-search");
    gs.addEventListener("input", ()=>{ this.ui.search = gs.value;
      if(this.route==="mail" && this.ui._mail) this.ui._mail.renderList(); });
    gs.addEventListener("keydown", e=>{
      if(e.key==="Enter"){ const q = gs.value.trim(); if(q) this.go("search:"+encodeURIComponent(q)); }
    });
  },

  /* ---------------- init ---------------- */
  init(){
    Themes.apply();
    document.getElementById("compose-btn").addEventListener("click", ()=> this.go("compose:new"));
    document.getElementById("check-mail-btn").addEventListener("click", ()=>{
      const em = Mail.checkMail(); this.refreshNav();
      if(this.route==="mail" && this.ui._mail) this.ui._mail.renderList();
      this.toast(em.folder==="inbox" ? "📬 New mail: "+em.subject : "New mail arrived (filtered).");
    });
    document.getElementById("theme-btn").addEventListener("click", ()=> Themes.openPicker());
    document.getElementById("settings-btn").addEventListener("click", ()=> this.go("settings"));
    document.getElementById("shortcuts-btn").addEventListener("click", ()=> this.go("settings:shortcuts"));
    document.getElementById("adv-search-btn").addEventListener("click", ()=> this.advSearch());
    document.getElementById("menu-btn").addEventListener("click", ()=> document.body.classList.toggle("nav-open"));
    document.getElementById("side-scrim").addEventListener("click", ()=> document.body.classList.remove("nav-open"));
    document.getElementById("brand-home").addEventListener("click", ()=> this.go("today"));
    document.getElementById("account-btn").addEventListener("click", ev=>{
      const u = Store.state.user;
      this.menu(ev.currentTarget, [
        {label:`👤 ${u.name} — ${u.email}`, fn:()=>this.go("settings:general")},
        {label:"🎨 Themes", fn:()=>Themes.openPicker()},
        {label:"⚙️ Settings", fn:()=>this.go("settings")},
        {sep:true},
        {label:"↩ Sign out (demo)", fn:()=>this.toast("Demo build — there is no server session to sign out of.")}
      ]);
    });
    window.addEventListener("hashchange", ()=> this.parse());
    this.bindKeys();
    this.tiltInit();
    this.applyLogo();
    this.parse();
  }
};

window.App = App;
document.addEventListener("DOMContentLoaded", ()=> App.init());
})();
