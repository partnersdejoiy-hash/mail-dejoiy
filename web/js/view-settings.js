/* ============ Dejoiy Mail — view-settings.js : all settings incl. working filters ============ */
(function(){
"use strict";

const TABS = [
  ["general","⚙️ General"],["themes","🎨 Themes"],["filters","🧹 Filters"],
  ["vacation","🏖️ Vacation"],["lists","🚫 Blocked & allowed"],["shortcuts","⌨️ Shortcuts"],["data","💾 Sounds & data"]
];

Views.settings = function(el, tab){
  tab = tab || "general";
  const s = Store.state;
  el.innerHTML = `
    <div class="view-head"><h1>Settings</h1></div>
    <div class="set-layout">
      <div class="set-tabs">${TABS.map(([id,l])=>`<button data-stab="${id}" class="${tab===id?"on":""}">${l}</button>`).join("")}</div>
      <div class="set-body" id="set-body"></div>
    </div>`;
  el.querySelectorAll("[data-stab]").forEach(b=> b.addEventListener("click", ()=> Views.settings(el, b.dataset.stab)));
  const body = el.querySelector("#set-body");
  ({general:renderGeneral, themes:renderThemes, filters:renderFilters, vacation:renderVacation,
    lists:renderLists, shortcuts:renderShortcuts, data:renderData})[tab](body);
};

/* ---------- general ---------- */
function renderGeneral(body){
  const u = Store.state.user;
  body.innerHTML = `<div class="card"><h3>⚙️ General</h3>
    <div class="grid c2">
      <div class="field"><label>Display name</label><input type="text" id="sg-name" value="${esc(u.name)}"></div>
      <div class="field"><label>Email address</label><input type="email" id="sg-email" value="${esc(u.email)}"></div>
    </div>
    <div class="field"><label>Signature (added to new messages)</label><textarea id="sg-sig" rows="4">${esc(u.signature)}</textarea></div>
    <div class="btn-row"><button class="btn primary" id="sg-save">Save changes</button></div></div>`;
  body.querySelector("#sg-save").addEventListener("click", ()=>{
    u.name = body.querySelector("#sg-name").value.trim() || u.name;
    u.email = body.querySelector("#sg-email").value.trim() || u.email;
    u.signature = body.querySelector("#sg-sig").value;
    Store.save(); App.refreshNav(); App.toast("Settings saved ✓");
  });
}

/* ---------- themes ---------- */
function renderThemes(body){
  const p = Store.state.prefs;
  const cell = t => `<div class="theme-cell ${p.theme===t.id&&!p.customBg?"sel":""}" data-pick="${t.id}" role="button" tabindex="0">
    <div class="theme-sw" style="background:${Themes.ALL.indexOf(t)>=0?themeSwatch(t.id):"#333"}"></div>
    <div class="theme-nm">${esc(t.name)} ${p.theme===t.id&&!p.customBg?"✓":""}</div></div>`;
  body.innerHTML = `<div class="card"><h3>🎨 Themes</h3>
    <div class="field"><label>Brightness — independent of theme</label>
      <div class="seg">${["light","medium","dark"].map(b=>`<button data-b="${b}" class="${p.brightness===b?"on":""}">${b[0].toUpperCase()+b.slice(1)}</button>`).join("")}</div></div>
    <div class="theme-sec">Colour themes</div><div class="theme-grid">${Themes.ALL.filter(t=>t.kind==="color").map(cell).join("")}</div>
    <div class="theme-sec">Scenic themes</div><div class="theme-grid">${Themes.ALL.filter(t=>t.kind==="scenic").map(cell).join("")}</div>
    <div class="theme-sec">Your photo</div>
    <div class="btn-row"><label class="btn sm" style="cursor:pointer">Upload background<input type="file" id="st-upload" accept="image/*" class="sr"></label>
    ${p.customBg?`<button class="btn sm ghost" id="st-clear">Remove photo</button>`:""}
    ${p.customBg?`<span class="chip">✓ custom photo active</span>`:""}</div>
    <div class="theme-sec">Brand logo</div>
    <div class="btn-row"><label class="btn sm" style="cursor:pointer">Upload logo<input type="file" id="st-logo" accept="image/*" class="sr"></label>
    ${p.customLogo?`<button class="btn sm ghost" id="st-logo-clear">Remove logo</button>`:""}
    ${p.customLogo?`<img src="${p.customLogo}" alt="logo preview" style="height:28px;border-radius:6px;border:1px solid var(--line)">`:""}</div>
    <p class="hint" style="margin-top:10px;font-size:12px;color:var(--ink-3)">Themes apply instantly — no save button needed. Your choice is remembered on this device.</p></div>`;
  body.querySelectorAll("[data-b]").forEach(b=> b.addEventListener("click", ()=>{ Themes.setBrightness(b.dataset.b); renderThemes(body); }));
  body.querySelectorAll("[data-pick]").forEach(c2=> c2.addEventListener("click", ()=>{ Themes.set(c2.dataset.pick); renderThemes(body); }));
  body.querySelector("#st-upload").addEventListener("change", ev=>{
    const f = ev.target.files[0]; if(!f) return;
    const r = new FileReader(); r.onload = ()=>{ Themes.setCustom(r.result); renderThemes(body); }; r.readAsDataURL(f);
  });
  const clr = body.querySelector("#st-clear");
  if(clr) clr.addEventListener("click", ()=>{ Themes.clearCustom(); renderThemes(body); });
  body.querySelector("#st-logo").addEventListener("change", ev=>{
    const f = ev.target.files[0]; if(!f) return;
    const r = new FileReader(); r.onload = ()=>{ p.customLogo=r.result; Store.save(); App.applyLogo(); renderThemes(body); }; r.readAsDataURL(f);
  });
  const clrL = body.querySelector("#st-logo-clear");
  if(clrL) clrL.addEventListener("click", ()=>{ p.customLogo=""; Store.save(); App.applyLogo(); renderThemes(body); });
}
function themeSwatch(id){
  const m = {aol:"#2f7cf6",yellow:"#f7b733",highcontrast:"#111",simple:"#c9d2e2",aim:"#e33d2e",aoldotcom:"#00a9e0",
    purple:"#9b5cf6",sunrise:"#ff9a56",aquagreen:"#34d399",aquablue:"#38bdf8",deeppurple:"#6d28d9",
    bluenight:"#1e3a8a",darkgrey:"#6b7280",nightlandscape:"linear-gradient(135deg,#3b4a6b,#05080f)",
    roadtrip:"linear-gradient(135deg,#7c3f16,#120903)",sunsetaussie:"linear-gradient(135deg,#93386b,#f7b733)",
    lighthouse:"linear-gradient(135deg,#155e86,#0a1622)",spring:"linear-gradient(135deg,#3f7d4e,#0b1a10)",
    winter:"linear-gradient(135deg,#d7e3ef,#9db4c8)",summer:"linear-gradient(135deg,#a3d65c,#2c7a4b)",
    galaxy:"linear-gradient(135deg,#4c1d95,#050310)",fall:"linear-gradient(135deg,#c2410c,#451a03)",
    western:"linear-gradient(135deg,#eab308,#290e03)",sunset:"linear-gradient(135deg,#9d3c6e,#f97316)"};
  return m[id]||"#333";
}

/* ---------- filters ---------- */
function renderFilters(body){
  const s = Store.state;
  body.innerHTML = `<div class="card"><h3>🧹 Filters</h3>
    <p class="hint" style="margin-bottom:12px;font-size:12.5px;color:var(--ink-2)">Filters match incoming mail and act on it automatically. Use <b>Run filters now</b> to apply them to your inbox immediately.</p>
    <div class="btn-row" style="margin-bottom:12px">
      <button class="btn sm primary" id="sf-new">+ Create filter</button>
      <button class="btn sm" id="sf-run">▶ Run filters now</button></div>
    <div id="sf-list">${s.filters.map(f=>`
      <div class="todo"><button class="pill-toggle" role="switch" aria-checked="${f.on}" data-fon="${f.id}"></button>
        <span><b>${esc(f.name)}</b><br><span style="font-size:12px;color:var(--ink-3)">${esc(describeFilter(f))}</span></span>
        <span style="margin-left:auto;display:flex;gap:4px">
          <button class="btn sm ghost" data-fedit="${f.id}">Edit</button>
          <button class="btn sm ghost" data-fdel="${f.id}">×</button></span></div>`).join("")
      || `<div class="empty-note">No filters yet — create one above.</div>`}</div></div>`;
  body.querySelector("#sf-new").addEventListener("click", ()=> filterDialog(null, ()=>renderFilters(body)));
  body.querySelector("#sf-run").addEventListener("click", ()=>{
    const r = Filters.runAll(); App.refreshNav();
    App.toast(r.matched ? `Filters matched ${r.matched} message${r.matched>1?"s":""} ✓` : "Filters ran — nothing matched.");
    renderFilters(body);
  });
  body.querySelectorAll("[data-fon]").forEach(t=> t.addEventListener("click", ()=>{
    const f = s.filters.find(x=>x.id===t.dataset.fon); f.on = !f.on; Store.save(); renderFilters(body);
  }));
  body.querySelectorAll("[data-fedit]").forEach(b=> b.addEventListener("click", ()=>{
    filterDialog(s.filters.find(x=>x.id===b.dataset.fedit), ()=>renderFilters(body));
  }));
  body.querySelectorAll("[data-fdel]").forEach(b=> b.addEventListener("click", ()=>{
    const f = s.filters.find(x=>x.id===b.dataset.fdel);
    App.confirm(`Delete filter "${f.name}"?`, ()=>{ s.filters = s.filters.filter(x=>x.id!==f.id); Store.save(); renderFilters(body); });
  }));
}
function describeFilter(f){
  const c = f.criteria, parts = [];
  if(c.from) parts.push("from "+c.from); if(c.subject) parts.push("subject "+c.subject);
  if(c.hasWords) parts.push("has "+c.hasWords); if(c.hasAttachment) parts.push("has attachment");
  const a = f.actions, acts = [];
  if(a.delete) acts.push("delete"); if(a.archive) acts.push("archive"); if(a.markRead) acts.push("mark read");
  if(a.star) acts.push("star"); if(a.label) acts.push("label "+a.label); if(a.forwardTo) acts.push("forward");
  if(a.neverSpam) acts.push("never spam"); if(a.important) acts.push("important");
  return (parts.join(", ")||"all mail") + " → " + (acts.join(", ")||"no action");
}
function filterDialog(f, done){
  const isNew = !f; f = f ? JSON.parse(JSON.stringify(f)) : Filters.blank();
  const c = f.criteria, a = f.actions;
  const crit = (k,label,type,ph)=>`<div class="field"><label>${label}</label><input type="${type||"text"}" data-ck="${k}" value="${esc(c[k]||"")}" placeholder="${ph||""}"></div>`;
  App.dialog({ title: isNew?"Create filter":"Edit filter", wide:true, body:`
    <div class="field"><label>Filter name</label><input type="text" id="ff-name" value="${esc(f.name)}"></div>
    <div class="theme-sec">Match when ALL of these match</div>
    <div class="grid c2">${crit("from","From")}${crit("to","To")}${crit("subject","Subject")}${crit("hasWords","Includes words")}${crit("noWords","Excludes words")}${crit("larger","Larger than (e.g. 1MB)","text","1MB")}${crit("smaller","Smaller than","text","")}${crit("after","After date","date")}${crit("before","Before date","date")}</div>
    <div class="check-row"><input type="checkbox" data-ck="hasAttachment" ${c.hasAttachment?"checked":""}> Has attachment</div>
    <div class="theme-sec">Then do this</div>
    <div class="grid c2">
      ${[["archive","Archive (skip inbox)"],["markRead","Mark as read"],["star","Star it"],["delete","Delete it"],["neverSpam","Never send to spam"],["important","Mark important"]].map(([k,l])=>`<div class="check-row"><input type="checkbox" data-ak="${k}" ${a[k]?"checked":""}> ${l}</div>`).join("")}
    </div>
    <div class="grid c2" style="margin-top:8px">
      <div class="field"><label>Apply label</label><input type="text" data-ak="label" value="${esc(a.label||"")}" placeholder="e.g. work"></div>
      <div class="field"><label>Forward to</label><input type="email" data-ak="forwardTo" value="${esc(a.forwardTo||"")}" placeholder="name@example.com"></div>
    </div>`,
    actions:[{label:"Cancel"},{label:isNew?"Create filter":"Save", primary:true, fn:()=>{
      f.name = document.getElementById("ff-name").value.trim() || "Untitled filter";
      document.querySelectorAll("[data-ck]").forEach(i=>{ f.criteria[i.dataset.ck] = i.type==="checkbox" ? i.checked : i.value.trim(); });
      document.querySelectorAll("[data-ak]").forEach(i=>{ f.actions[i.dataset.ak] = i.type==="checkbox" ? i.checked : i.value.trim(); });
      const s = Store.state;
      if(isNew) s.filters.push(f); else { const ix = s.filters.findIndex(x=>x.id===f.id); s.filters[ix]=f; }
      Store.save(); App.toast("Filter saved ✓"); done && done();
    }}]});
}

/* ---------- vacation ---------- */
function renderVacation(body){
  const v = Store.state.vacation;
  body.innerHTML = `<div class="card"><h3>🏖️ Vacation responder</h3>
    <div class="check-row" style="margin-bottom:10px"><button class="pill-toggle" role="switch" aria-checked="${v.on}" id="sv-on"></button>
      <b>Vacation responder ${v.on?"is ON":"is OFF"}</b></div>
    <div class="field"><label>Subject</label><input type="text" id="sv-subj" value="${esc(v.subject)}"></div>
    <div class="field"><label>Message</label><textarea id="sv-msg" rows="5">${esc(v.message)}</textarea></div>
    <div class="btn-row"><button class="btn primary" id="sv-save">Save</button></div>
    <p class="hint" style="margin-top:10px;font-size:12px;color:var(--ink-3)">When ON, anyone opening a compose to you sees this note (demo behaviour until the real backend auto-replies).</p></div>`;
  body.querySelector("#sv-on").addEventListener("click", ev=>{ v.on=!v.on; Store.save(); renderVacation(body); App.toast("Vacation responder "+(v.on?"enabled":"disabled")); });
  body.querySelector("#sv-save").addEventListener("click", ()=>{
    v.subject = body.querySelector("#sv-subj").value; v.message = body.querySelector("#sv-msg").value;
    Store.save(); App.toast("Vacation responder saved ✓");
  });
}

/* ---------- blocked & allowed ---------- */
function renderLists(body){
  const s = Store.state;
  const listHtml = (arr, key, title, hint)=>`
    <div class="card" style="margin-bottom:14px"><h3>${title}</h3><p class="hint" style="font-size:12px;color:var(--ink-3);margin-bottom:8px">${hint}</p>
    ${arr.map((x,i)=>`<div class="todo"><span>${esc(x)}</span><button class="t-x icon-btn sm" data-lk="${key}" data-li="${i}">×</button></div>`).join("") || `<div class="empty-note">Empty.</div>`}
    <div class="btn-row" style="margin-top:8px"><input type="text" id="in-${key}" placeholder="name@example.com" style="max-width:260px">
    <button class="btn sm" data-add="${key}">Add</button></div></div>`;
  body.innerHTML =
    listHtml(s.blocked, "blocked", "🚫 Blocked senders", "Mail from these addresses is sent straight to Spam.") +
    listHtml(s.allowed, "allowed", "✅ Allowed senders", "Mail from these addresses always lands in the Inbox.");
  body.querySelectorAll("[data-add]").forEach(b=> b.addEventListener("click", ()=>{
    const k = b.dataset.add, inp = body.querySelector("#in-"+k), v = inp.value.trim().toLowerCase();
    if(!v || !/.+@.+\..+/.test(v)){ App.toast("Enter a valid email address."); return; }
    if(!s[k].includes(v)) s[k].push(v); Store.save(); renderLists(body); App.toast("Added ✓");
  }));
  body.querySelectorAll("[data-lk]").forEach(x=> x.addEventListener("click", ()=>{
    const k = x.dataset.lk; s[k].splice(+x.dataset.li,1); Store.save(); renderLists(body);
  }));
}

/* ---------- shortcuts ---------- */
function renderShortcuts(body){
  const rows = [["C","Compose new message"],["/","Focus search"],["J / K","Next / previous message"],
    ["X","Select message"],["S","Star / unstar"],["E","Archive"],["#","Delete"],["R","Reply"],["F","Forward"],
    ["?","This shortcuts panel"],["Esc","Close dialog"]];
  body.innerHTML = `<div class="card"><h3>⌨️ Keyboard shortcuts</h3>
    ${rows.map(([k,d])=>`<div class="sc-row"><span>${d}</span><span class="kbd">${k}</span></div>`).join("")}</div>`;
}

/* ---------- sounds & data ---------- */
function renderData(body){
  const p = Store.state.prefs, st = Mail.storage();
  body.innerHTML = `<div class="card"><h3>💾 Sounds & data</h3>
    <div class="check-row"><button class="pill-toggle" role="switch" aria-checked="${p.sounds}" id="sd-snd"></button> Play sounds (new mail, sent)</div>
    <div class="sc-row"><span>Storage used</span><span>${st.used} MB of ${(st.total/1024).toFixed(0)} GB</span></div>
    <div class="sc-row"><span>Messages</span><span>${Store.state.emails.length}</span></div>
    <div class="sc-row"><span>Contacts</span><span>${Store.state.contacts.length}</span></div>
    <div class="btn-row" style="margin-top:14px">
      <button class="btn sm" id="sd-test">🔔 Test sound</button>
      <button class="btn sm danger" id="sd-reset">Reset demo data</button></div>
    <p class="hint" style="margin-top:10px;font-size:12px;color:var(--ink-3)">Reset restores the original demo mailbox, contacts and settings on this device.</p></div>`;
  body.querySelector("#sd-snd").addEventListener("click", ev=>{ p.sounds=!p.sounds; Store.save(); renderData(body); });
  body.querySelector("#sd-test").addEventListener("click", ()=> App.sound("mail"));
  body.querySelector("#sd-reset").addEventListener("click", ()=>{
    App.confirm("Reset all demo data on this device?", ()=>{ Store.reset(); Themes.apply(); App.go("today"); App.refreshNav(); App.toast("Demo data reset ✓"); });
  });
}
})();
