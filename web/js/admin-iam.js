/* ============ Dejoiy Mail Admin — admin-iam.js : Roles & permissions ============
   Overview, roles (system and custom), the permission matrix, who has what, access requests, access reviews and the
   access log. Every number and row comes from the server (/api/admin/action, op "iam_…"); nothing here is sample data.
   Permissions the app does not check yet are marked "Planned", so no switch pretends to do something it does not. */
(function(){
"use strict";

let h, esc, icon, act, dialog, toast, head, $;
const st = { tab:"overview", domain:"", data:null, q:"", module:"", status:"pending", log:{} };
const SCOPE = {org:"Whole company", department:"Departments", users:"Chosen people", self:"Only themselves"};
const SENS = {low:"good", medium:"warn", high:"bad", critical:"bad"};
const day = s => s ? new Date(s*1000).toLocaleString([], {dateStyle:"medium", timeStyle:"short"}) : "—";
const scopeText = s => !s || s.type==="org" ? "Whole company" : SCOPE[s.type]+(s.values?.length?": "+s.values.join(", "):"");
const ends = x => x ? `<span class="adm-pill warn">until ${esc(day(x))}</span>` : "";
const pill = (sens) => `<span class="adm-pill ${SENS[sens]||""}">${esc(sens)}</span>`;
const can = (...p) => p.some(x => st.data?.mine?.includes(x));
const perm = id => st.data.catalog.find(p => p.id===id) || {id, name:id, module:"", live:false, sensitivity:"low"};
const byModule = () => { const out={}; for(const p of st.data.catalog) (out[p.module] ||= []).push(p); return out; };
const people = () => (h.state.data?.users||[]).filter(u => u.email.endsWith("@"+st.domain)).map(u => u.email);
const departments = () => (h.state.data?.departments||[]).filter(x => x.email.endsWith("@"+st.domain)).map(x => x.name || x.email.split("@")[0]);

async function call(payload){ return act({domain:st.domain, ...payload}); }
async function refresh(){ st.data = await call({op:"iam_summary"}); }

/* ---------------- the page ---------------- */
async function iam(main, d, helpers, rest){
  ({esc, icon, act, dialog, toast, head, $} = helpers); h = helpers;
  const domains = d.scope ? [d.scope] : d.domains.map(x=>x.domain);
  st.domain = d.scope || st.domain || domains.find(x => h.state.user?.email.endsWith("@"+x)) || domains[0] || "";
  const pick = d.scope ? "" : `<label class="adm-inline">Company <select id="iam-domain">${domains.map(x=>`<option ${x===st.domain?"selected":""}>${esc(x)}</option>`).join("")}</select></label>`;
  main.innerHTML = head("Roles & permissions", `Who can do what in ${st.domain}. Access is off unless a role or a grant turns it on, and a deny always wins.`, pick)+`<div id="iam-body"><p class="adm-muted">Loading…</p></div>`;
  $("iam-domain")?.addEventListener("change", e => { st.domain=e.target.value; st.data=null; iam(main, d, helpers, rest); });
  try{ await refresh(); }catch(e){ $("iam-body").innerHTML = `<div class="adm-card adm-error">${esc(e.message)}</div>`; return; }
  if(rest) return roleDetail(rest);
  draw();
}
const TABS = [["overview","Overview"],["roles","Roles"],["matrix","Permission matrix"],["people","People & access"],["requests","Access requests"],["reviews","Access reviews"],["log","Access log"]];
function draw(){
  const body = $("iam-body"); if(!body) return;
  const pending = st.data.pending;
  body.innerHTML = `<div class="adm-tabs" role="tablist">${TABS.map(([k,l])=>`<button role="tab" aria-selected="${st.tab===k}" class="${st.tab===k?"on":""}" data-tab="${k}">${esc(l)}${k==="requests"&&pending?` <span class="adm-pill warn">${pending}</span>`:""}</button>`).join("")}</div><div id="iam-tab"></div>`;
  body.querySelectorAll("[data-tab]").forEach(b => b.addEventListener("click", () => { st.tab=b.dataset.tab; draw(); }));
  ({overview, roles, matrix, people:peopleTab, requests, reviews, log})[st.tab]($("iam-tab"));
}

/* ---------------- overview ---------------- */
function overview(el){
  const s = st.data.summary;
  el.innerHTML = `<div class="adm-stats">
      <div class="adm-card adm-stat"><b>${s.roles}</b><span>Roles (${s.systemRoles} ready-made, ${s.customRoles} custom)</span></div>
      <div class="adm-card adm-stat"><b>${s.privileged}</b><span>People with high or critical access</span></div>
      <div class="adm-card adm-stat"><b>${s.temporary}</b><span>People with temporary access</span></div>
      <div class="adm-card adm-stat"><b>${s.pending}</b><span>Requests waiting</span></div></div>
    <div class="adm-grid2">
      <div class="adm-card adm-pad"><h2 class="adm-h3">Do something</h2>
        <div class="adm-row-btns" style="flex-wrap:wrap">
          ${can("roles.create")?`<button class="adm-btn primary" id="iam-new">${icon("compose")} Create a role</button>`:""}
          ${can("roles.assign")?`<button class="adm-btn ghost" id="iam-assign">Give someone a role</button>`:""}
          ${can("permissions.view")?`<button class="adm-btn ghost" id="iam-check">Check someone's access</button>`:""}
          ${can("security.incident_manage")?`<button class="adm-btn danger" id="iam-glass">Emergency access</button>`:""}</div>
        <p class="adm-muted" style="margin-top:12px">${s.livePermissions} of ${s.permissions} permissions are checked by Dejoiy Mail today. The rest are marked <i>Planned</i>: you can put them in roles now, and they start working when that part of the app arrives.</p></div>
      <div class="adm-card adm-pad"><h2 class="adm-h3">Recently changed roles</h2>
        <ul class="adm-list">${s.recent.map(r=>`<li><span>${esc(r.name)}</span><small class="adm-muted">${esc(day(r.updated))}</small></li>`).join("")||"<li>No roles yet.</li>"}</ul></div></div>
    <div class="adm-card adm-pad iam-rules"><h2 class="adm-h3">How access is decided</h2>
      <ol><li>Nothing is allowed unless a role or a direct grant allows it.</li><li>A deny always beats an allow.</li>
      <li>An allow counts only inside its scope (whole company, departments, chosen people or only themselves) and its time limit.</li>
      <li>No role can read other people's mail. That needs an approved request with a reason, for a limited time, approved by two people.</li>
      <li>The last Super Administrator cannot be removed, nobody approves their own request, and nobody gives themselves a role.</li>
      <li>Every change is written to the access log, which cannot be edited or deleted.</li></ol></div>`;
  $("iam-new")?.addEventListener("click", () => editRole(null));
  $("iam-assign")?.addEventListener("click", () => assignDialog());
  $("iam-check")?.addEventListener("click", () => inspector());
  $("iam-glass")?.addEventListener("click", breakGlass);
}

/* ---------------- roles ---------------- */
function roles(el){
  const q = st.q.toLowerCase();
  const list = st.data.roles.filter(r => !q || (r.name+" "+r.description).toLowerCase().includes(q));
  el.innerHTML = `<div class="sc-tools"><input id="iam-q" type="search" placeholder="Search roles" value="${esc(st.q)}">
      ${can("roles.create")?`<button class="adm-btn primary" id="iam-new">${icon("compose")} Create a role</button>`:""}</div>
    <div class="adm-card sc-wrap"><table class="adm-table"><thead><tr><th>Role</th><th>Type</th><th>Sensitivity</th><th>People</th><th>Permissions</th><th></th></tr></thead><tbody>
    ${list.map(r=>`<tr><td><a href="/admin/manage/roles/${esc(r.id)}"><b>${esc(r.name)}</b></a><small>${esc(r.description)}</small></td>
      <td>${r.system?"Ready-made":"Custom"}${r.admin?"<small>Admin console</small>":""}</td><td>${pill(r.sensitivity)}</td><td>${r.users}</td>
      <td>${r.key==="super_admin"?"All":r.allow.length}${r.deny.length?` <small>${r.deny.length} denied</small>`:""}</td>
      <td class="adm-right"><a class="adm-btn ghost" href="/admin/manage/roles/${esc(r.id)}">Open</a>
        ${can("roles.clone")?`<button class="adm-btn ghost" data-clone="${esc(r.id)}">Clone</button>`:""}</td></tr>`).join("")}</tbody></table></div>`;
  $("iam-q").addEventListener("input", e => { st.q=e.target.value; clearTimeout(roles.t); roles.t=setTimeout(()=>{ roles(el); const i=$("iam-q"); i.focus(); i.setSelectionRange(i.value.length,i.value.length); },200); });
  $("iam-new")?.addEventListener("click", () => editRole(null));
  el.querySelectorAll("[data-clone]").forEach(b => b.addEventListener("click", () => cloneRole(b.dataset.clone)));
}
function cloneRole(id){
  const r = st.data.roles.find(x=>x.id===id);
  dialog({title:"Clone "+r.name, body:`<label class="adm-field">Name of the copy<input id="iam-cn" value="${esc("Copy of "+r.name)}" maxlength="60"></label><p role="alert" class="adm-error"></p>`,
    actions:[{label:"Cancel"},{label:"Clone", primary:true, fn: async root => { const out=await call({op:"iam_role_clone", id, name:root.querySelector("#iam-cn").value}); toast("Role cloned"); h.navigate("manage/roles/"+out.role.id); }}]});
}

// one role: overview, permissions, people, settings, history
async function roleDetail(id){
  const body = $("iam-body");
  let out; try{ out = await call({op:"iam_role", id}); }catch(e){ body.innerHTML=`<div class="adm-card adm-error">${esc(e.message)}</div>`; return; }
  const r = out.role, locked = r.key==="super_admin", editable = !locked && can("roles.edit");
  const tab = roleDetail.tab || "permissions";
  const allow = new Set(locked ? st.data.catalog.filter(p=>!p.content).map(p=>p.id) : r.allow), deny = new Set(r.deny);
  body.innerHTML = `<p><a href="/admin/manage/roles" class="adm-back">← All roles</a></p>
    <div class="adm-card adm-pad"><div class="adm-role-head"><div><h2>${esc(r.name)} ${pill(r.sensitivity)}</h2><p class="adm-muted">${esc(r.description)}</p>
      <small class="adm-muted">${r.system?"Ready-made role":"Custom role by "+esc(r.createdBy||"")} · updated ${esc(day(r.updated))}${r.parent?" · inherits from "+esc(st.data.roles.find(x=>x.id===r.parent)?.name||""):""}${r.admin?" · uses the admin console":""}</small></div>
      <div class="adm-row-btns">${can("roles.assign")?`<button class="adm-btn ghost" id="iam-give">Give to someone</button>`:""}
        ${!r.system&&can("roles.delete")?`<button class="adm-btn danger" id="iam-del">Delete</button>`:""}</div></div></div>
    <div class="adm-tabs" role="tablist">${[["permissions","Permissions"],["people",`People (${out.assignments.length})`],["settings","Settings"],["history","History"]].map(([k,l])=>`<button role="tab" aria-selected="${tab===k}" class="${tab===k?"on":""}" data-rt="${k}">${esc(l)}</button>`).join("")}</div>
    <div id="iam-rt"></div>`;
  body.querySelectorAll("[data-rt]").forEach(b=>b.addEventListener("click",()=>{ roleDetail.tab=b.dataset.rt; roleDetail(id); }));
  $("iam-give")?.addEventListener("click", () => assignDialog(r.id));
  $("iam-del")?.addEventListener("click", () => h.confirmDialog("Delete "+r.name, "This removes the role for good. Nobody may still have it.", "Delete", async () => { await call({op:"iam_role_delete", id}); toast("Role deleted"); await refresh(); h.navigate("manage/roles"); }));
  const el = $("iam-rt");
  if(tab==="permissions"){
    const groups = byModule();
    el.innerHTML = `${locked?`<p class="adm-note">The Super Administrator always has every permission except reading other people's mail, so it cannot be changed.</p>`:""}
      <div class="iam-perm-tools"><span class="adm-muted"><b id="iam-count">${allow.size}</b> allowed · <b id="iam-dcount">${deny.size}</b> denied</span>
      ${editable?`<button class="adm-btn primary" id="iam-save">Save permissions</button>`:""}</div>
      ${Object.entries(groups).map(([m,ps])=>`<details class="adm-card iam-module" ${ps.some(p=>allow.has(p.id)||deny.has(p.id))?"open":""}><summary><b>${esc(st.data.modules[m])}</b> <small class="adm-muted">${ps.filter(p=>allow.has(p.id)).length} of ${ps.length}</small></summary>
        <table class="adm-table iam-perms"><tbody>${ps.map(p=>`<tr><td><b>${esc(p.name)}</b> ${p.live?"":`<span class="adm-pill">Planned</span>`}<small>${esc(p.description)} · <span class="adm-mono">${esc(p.id)}</span></small></td><td>${pill(p.sensitivity)}</td>
          <td class="adm-right">${p.content?`<small class="adm-muted">Only by approved request</small>`:`<select data-perm="${esc(p.id)}" ${editable?"":"disabled"} aria-label="${esc(p.name)}">
            <option value="">Not given</option><option value="allow" ${allow.has(p.id)?"selected":""}>Allow</option><option value="deny" ${deny.has(p.id)?"selected":""}>Deny</option></select>`}</td></tr>`).join("")}</tbody></table></details>`).join("")}
      <p role="alert" class="adm-error" id="iam-err"></p>`;
    const count = () => { const v=[...el.querySelectorAll("[data-perm]")]; $("iam-count").textContent=v.filter(s=>s.value==="allow").length; $("iam-dcount").textContent=v.filter(s=>s.value==="deny").length; };
    el.querySelectorAll("[data-perm]").forEach(s=>s.addEventListener("change",count));
    $("iam-save")?.addEventListener("click", async ev => {
      const v=[...el.querySelectorAll("[data-perm]")]; ev.target.disabled=true;
      try{ await call({op:"iam_role_save", id, ...settingsOf(r), allow:v.filter(s=>s.value==="allow").map(s=>s.dataset.perm), deny:v.filter(s=>s.value==="deny").map(s=>s.dataset.perm)});
        toast("Permissions saved"); await refresh(); roleDetail(id); }
      catch(e){ $("iam-err").textContent=e.message; } finally{ ev.target.disabled=false; }
    });
  }
  if(tab==="people"){
    el.innerHTML = out.assignments.length ? `<div class="adm-card sc-wrap"><table class="adm-table"><thead><tr><th>Person</th><th>Scope</th><th>Given by</th><th></th></tr></thead><tbody>
      ${out.assignments.map(a=>`<tr><td><b>${esc(a.email)}</b> ${ends(a.expires)}${a.reason?`<small>${esc(a.reason)}</small>`:""}</td><td>${esc(scopeText(a.scope))}</td><td>${esc(a.by||"")}<small>${esc(day(a.at))}</small></td>
        <td class="adm-right">${can("roles.revoke")?`<button class="adm-btn ghost" data-un="${esc(a.id)}">Remove</button>`:""}</td></tr>`).join("")}</tbody></table></div>`
      : `<p class="adm-muted">Nobody has this role yet.</p>`;
    el.querySelectorAll("[data-un]").forEach(b=>b.addEventListener("click",()=>unassign(b.dataset.un, () => roleDetail(id))));
  }
  if(tab==="settings") roleSettings(el, r, editable);
  if(tab==="history"){
    el.innerHTML = out.history.length ? `<div class="adm-card sc-wrap"><table class="adm-table"><thead><tr><th>When</th><th>Who</th><th>What</th><th>Details</th></tr></thead><tbody>
      ${out.history.map(a=>`<tr><td>${esc(day(a.at))}</td><td>${esc(a.actor)}</td><td>${esc(ACTION[a.action]||a.action)}</td><td><small>${esc(a.target)}${a.reason?" · "+esc(a.reason):""}${diff(a)}</small></td></tr>`).join("")}</tbody></table></div>`
      : `<p class="adm-muted">No changes recorded yet.</p>`;
  }
}
const settingsOf = r => ({name:r.name, description:r.description, sensitivity:r.sensitivity, admin:r.admin, parent:r.parent, approvals:r.approvals});
function roleSettings(el, r, editable){
  const parents = st.data.roles.filter(x => x.id!==r?.id && x.key!=="super_admin");
  el.innerHTML = `<form class="adm-form adm-card adm-pad" id="iam-rs">
    <label class="adm-field">Name<input name="name" maxlength="60" value="${esc(r?.name||"")}" ${r?.system||!editable?"disabled":""} required></label>
    <label class="adm-field">What it is for<textarea name="description" maxlength="300" rows="2" ${editable?"":"disabled"}>${esc(r?.description||"")}</textarea></label>
    <div class="adm-fields"><label class="adm-field">Sensitivity<select name="sensitivity" ${editable?"":"disabled"}>${["low","medium","high","critical"].map(x=>`<option ${(r?.sensitivity||"medium")===x?"selected":""}>${x}</option>`).join("")}</select><small>High and critical roles go into access reviews.</small></label>
    <label class="adm-field">Inherits from<select name="parent" ${editable?"":"disabled"}><option value="">Nothing</option>${parents.map(x=>`<option value="${esc(x.id)}" ${r?.parent===x.id?"selected":""}>${esc(x.name)}</option>`).join("")}</select><small>Gets that role's permissions too.</small></label>
    <label class="adm-field">Approvals when requested<select name="approvals" ${editable?"":"disabled"}><option value="">By sensitivity</option><option value="1" ${r?.approvals===1?"selected":""}>One person</option><option value="2" ${r?.approvals===2?"selected":""}>Two people</option></select></label>
    <label class="adm-field adm-check"><input type="checkbox" name="admin" ${r?.admin?"checked":""} ${editable?"":"disabled"}> Uses the admin console</label></div>
    <p class="adm-muted">“Uses the admin console” gives people with this role company-admin rights on the mail server when the role is given; what they can do there is still limited to this role's permissions.</p>
    ${editable?`<button class="adm-btn primary">Save</button>`:""}<p role="alert" class="adm-error"></p></form>`;
  el.querySelector("form").addEventListener("submit", async e => {
    e.preventDefault(); const f=e.target, err=f.querySelector("[role=alert]");
    const data={name:f.name.value, description:f.description.value, sensitivity:f.sensitivity.value, parent:f.parent.value||null, approvals:f.approvals.value?+f.approvals.value:null, admin:f.admin.checked};
    try{ const out=await call({op:"iam_role_save", id:r?.id, ...data, allow:r?.allow||[], deny:r?.deny||[]}); toast(r?"Role saved":"Role created: now choose its permissions"); await refresh();
      $("adm-dialog-root").innerHTML=""; roleDetail.tab="permissions"; h.navigate("manage/roles/"+out.role.id); }
    catch(x){ err.textContent=x.message; }
  });
}
function editRole(){
  dialog({title:"Create a role", wide:true, body:`<div id="iam-new-form"></div><p class="adm-muted">You choose its permissions on the next screen. Start from an existing role with Clone instead, if one is close.</p>`, actions:[{label:"Close"}]});
  roleSettings($("iam-new-form"), null, true);
}

/* ---------------- matrix ---------------- */
function matrix(el){
  const groups = byModule(), cols = st.data.roles;
  const mods = st.module ? {[st.module]:groups[st.module]} : groups;
  el.innerHTML = `<div class="sc-tools"><select id="iam-mod" aria-label="Module"><option value="">Every module</option>${Object.keys(groups).map(m=>`<option value="${m}" ${st.module===m?"selected":""}>${esc(st.data.modules[m])}</option>`).join("")}</select>
      <span class="adm-muted">✓ allowed · ✕ denied · blank not given. Change a role on its own page.</span></div>
    <div class="adm-card iam-matrix-wrap"><table class="iam-matrix"><thead><tr><th>Permission</th>${cols.map(r=>`<th><a href="/admin/manage/roles/${esc(r.id)}" title="${esc(r.name)}">${esc(r.name)}</a></th>`).join("")}</tr></thead>
    <tbody>${Object.entries(mods).map(([m,ps])=>`<tr class="iam-mrow"><th colspan="${cols.length+1}">${esc(st.data.modules[m])}</th></tr>`+ps.map(p=>`<tr><th>${esc(p.name)}${p.live?"":` <small>Planned</small>`}</th>${cols.map(r=>{
      const on = r.key==="super_admin" ? !p.content : r.allow.includes(p.id), no = r.deny.includes(p.id);
      return `<td class="${no?"no":on?"yes":""}">${no?"✕":on?"✓":""}</td>`; }).join("")}</tr>`).join("")).join("")}</tbody></table></div>`;
  $("iam-mod").addEventListener("change", e => { st.module=e.target.value; matrix(el); });
}

/* ---------------- people & access ---------------- */
function peopleTab(el){
  const a = st.data.assignments, q = st.q.toLowerCase();
  const rows = [...a.roles.map(x=>({...x, kind:"role"})), ...a.grants.map(x=>({...x, kind:"grant"}))].filter(x => !q || (x.email+" "+x.name).toLowerCase().includes(q))
    .sort((x,y)=>x.email.localeCompare(y.email));
  el.innerHTML = `<div class="sc-tools"><input id="iam-q" type="search" placeholder="Search a person or role" value="${esc(st.q)}">
      ${can("roles.assign")?`<button class="adm-btn primary" id="iam-assign">Give a role</button>`:""}
      ${can("permissions.assign","permissions.override")?`<button class="adm-btn ghost" id="iam-grant">Allow or deny one permission</button>`:""}
      ${can("permissions.view")?`<button class="adm-btn ghost" id="iam-check">Check someone's access</button>`:""}</div>
    ${rows.length?`<div class="adm-card sc-wrap"><table class="adm-table"><thead><tr><th>Person</th><th>Access</th><th>Scope</th><th>Given by</th><th></th></tr></thead><tbody>
      ${rows.map(x=>`<tr><td><b>${esc(x.email)}</b></td>
        <td>${x.kind==="role"?`<a href="/admin/manage/roles/${esc(x.role)}">${esc(x.name)}</a> ${pill(x.sensitivity)}`:`<span class="adm-pill ${x.effect==="deny"?"bad":"good"}">${x.effect==="deny"?"Denied":"Allowed"}</span> ${esc(x.name)}`} ${ends(x.expires)}${x.reason?`<small>${esc(x.reason)}</small>`:""}</td>
        <td>${esc(scopeText(x.scope))}${x.conditions?.ips?`<small>Only from ${esc(x.conditions.ips.join(", "))}</small>`:""}</td><td>${esc(x.by||"")}<small>${esc(day(x.at))}</small></td>
        <td class="adm-right">${x.kind==="role"&&can("roles.revoke")?`<button class="adm-btn ghost" data-un="${esc(x.id)}">Remove</button>`:""}${x.kind==="grant"&&can("permissions.revoke")?`<button class="adm-btn ghost" data-ug="${esc(x.id)}">Remove</button>`:""}
          ${can("permissions.view")?`<button class="adm-btn ghost" data-why="${esc(x.email)}">Check</button>`:""}</td></tr>`).join("")}</tbody></table></div>`
      :`<p class="adm-muted">Nobody has roles here yet. Until they do, people keep what their earlier role in Teams &amp; roles gave them.</p>`}`;
  $("iam-q").addEventListener("input", e => { st.q=e.target.value; clearTimeout(peopleTab.t); peopleTab.t=setTimeout(()=>{ peopleTab(el); const i=$("iam-q"); i.focus(); i.setSelectionRange(i.value.length,i.value.length); },200); });
  $("iam-assign")?.addEventListener("click", () => assignDialog());
  $("iam-grant")?.addEventListener("click", grantDialog);
  $("iam-check")?.addEventListener("click", () => inspector());
  el.querySelectorAll("[data-un]").forEach(b=>b.addEventListener("click",()=>unassign(b.dataset.un, async()=>{ await refresh(); draw(); })));
  el.querySelectorAll("[data-ug]").forEach(b=>b.addEventListener("click",()=>h.confirmDialog("Remove this grant","The person loses this direct permission (or the deny is lifted) straight away.","Remove",async()=>{ await call({op:"iam_revoke_grant", id:b.dataset.ug}); toast("Removed"); await refresh(); draw(); })));
  el.querySelectorAll("[data-why]").forEach(b=>b.addEventListener("click",()=>inspector(b.dataset.why)));
}
function unassign(id, after){
  dialog({title:"Remove this role", body:`<label class="adm-field">Why (kept in the access log)<input id="iam-why" maxlength="300"></label><p class="adm-muted">The person loses it straight away.</p><p role="alert" class="adm-error"></p>`,
    actions:[{label:"Cancel"},{label:"Remove", danger:true, fn: async root => { const out=await call({op:"iam_unassign", id, reason:root.querySelector("#iam-why").value});
      toast(out.left?"Role removed":"Role removed. They have no role left: give them Standard Employee so they keep their own mail permissions."); await after(); }}]});
}
const scopeFields = () => `<div class="adm-fields"><label class="adm-field">Where it applies<select id="iam-scope">${Object.entries(SCOPE).map(([k,l])=>`<option value="${k}">${l}</option>`).join("")}</select></label>
  <label class="adm-field" id="iam-sv-wrap" hidden><span id="iam-sv-label">Which</span><input id="iam-sv" list="iam-sv-list" placeholder="Separate with commas"><datalist id="iam-sv-list"></datalist></label>
  <label class="adm-field">How long<select id="iam-hours"><option value="">Until removed</option>${[[1,"1 hour"],[8,"8 hours"],[24,"1 day"],[168,"7 days"],[720,"30 days"],[2160,"90 days"]].map(([v,l])=>`<option value="${v}">${l}</option>`).join("")}</select></label></div>`;
function wireScope(root){
  const s=root.querySelector("#iam-scope"), wrap=root.querySelector("#iam-sv-wrap"), list=root.querySelector("#iam-sv-list"), label=root.querySelector("#iam-sv-label");
  s.addEventListener("change",()=>{ wrap.hidden=!["department","users"].includes(s.value); label.textContent=s.value==="department"?"Which departments":"Which people (email addresses)";
    list.innerHTML=(s.value==="department"?departments():people()).map(x=>`<option value="${esc(x)}">`).join(""); });
}
const readScope = root => { const type=root.querySelector("#iam-scope").value; const values=root.querySelector("#iam-sv").value.split(",").map(x=>x.trim()).filter(Boolean);
  const hours=root.querySelector("#iam-hours").value; return {scope:{type, values}, hours:hours?+hours:null}; };
function assignDialog(roleId){
  const root = dialog({title:"Give a role", wide:true, body:`<div class="adm-fields"><label class="adm-field">Person<input id="iam-who" list="iam-people" placeholder="name@${esc(st.domain)}" autocomplete="off"><datalist id="iam-people">${people().map(x=>`<option value="${esc(x)}">`).join("")}</datalist></label>
      <label class="adm-field">Role<select id="iam-role">${st.data.roles.map(r=>`<option value="${esc(r.id)}" ${r.id===roleId?"selected":""}>${esc(r.name)} (${r.sensitivity})</option>`).join("")}</select></label></div>
      ${scopeFields()}<label class="adm-field">Reason (kept in the access log)<input id="iam-reason" maxlength="300"></label><p role="alert" class="adm-error"></p>`,
    actions:[{label:"Cancel"},{label:"Give role", primary:true, fn: async root => {
      const out=await call({op:"iam_assign", email:root.querySelector("#iam-who").value, role:root.querySelector("#iam-role").value, reason:root.querySelector("#iam-reason").value, ...readScope(root)});
      toast("Role given"); await refresh(); if(location.pathname.includes("/manage/roles/")) roleDetail(root.querySelector("#iam-role")?.value||roleId); else draw(); return out; }}]});
  wireScope(root);
}
function grantDialog(){
  const groups = byModule();
  const root = dialog({title:"Allow or deny one permission", wide:true, body:`<div class="adm-fields"><label class="adm-field">Person<input id="iam-who" list="iam-people" placeholder="name@${esc(st.domain)}" autocomplete="off"><datalist id="iam-people">${people().map(x=>`<option value="${esc(x)}">`).join("")}</datalist></label>
      <label class="adm-field">Permission<select id="iam-perm">${Object.entries(groups).map(([m,ps])=>`<optgroup label="${esc(st.data.modules[m])}">${ps.filter(p=>!p.content).map(p=>`<option value="${esc(p.id)}">${esc(p.name)}${p.live?"":" (planned)"}</option>`).join("")}</optgroup>`).join("")}</select></label>
      <label class="adm-field">Allow or deny<select id="iam-effect">${can("permissions.assign")?`<option value="allow">Allow</option>`:""}${can("permissions.override")?`<option value="deny">Deny (beats every allow)</option>`:""}</select></label>
      <label class="adm-field">Only from these networks<input id="iam-ips" placeholder="e.g. 203.0.113.0/24 (optional)"></label></div>
      ${scopeFields()}<label class="adm-field">Reason (kept in the access log)<input id="iam-reason" maxlength="300"></label>
      <p class="adm-muted">To stop someone mailing outside the company: choose “Send outside the company” and Deny.</p><p role="alert" class="adm-error"></p>`,
    actions:[{label:"Cancel"},{label:"Save", primary:true, fn: async root => {
      const ips=root.querySelector("#iam-ips").value.split(",").map(x=>x.trim()).filter(Boolean);
      await call({op:"iam_grant", email:root.querySelector("#iam-who").value, perm:root.querySelector("#iam-perm").value, effect:root.querySelector("#iam-effect").value,
        reason:root.querySelector("#iam-reason").value, conditions:ips.length?{ips}:null, ...readScope(root)});
      toast("Saved"); await refresh(); draw(); }}]});
  wireScope(root);
}

/* ---------------- "Why does this person have access?" ---------------- */
function inspector(email){
  const groups = byModule();
  const root = dialog({title:"Check someone's access", wide:true, body:`<form id="iam-insp" class="adm-fields"><label class="adm-field">Person<input id="iam-who" list="iam-people" value="${esc(email||"")}" placeholder="name@${esc(st.domain)}" autocomplete="off"><datalist id="iam-people">${people().map(x=>`<option value="${esc(x)}">`).join("")}</datalist></label>
      <label class="adm-field">Can they…<select id="iam-perm"><option value="">(show everything)</option>${Object.entries(groups).map(([m,ps])=>`<optgroup label="${esc(st.data.modules[m])}">${ps.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("")}</optgroup>`).join("")}</select></label>
      <label class="adm-field">…for this person (optional)<input id="iam-tgt" list="iam-people" placeholder="leave empty for company-wide"></label>
      <div class="adm-field adm-check"><button class="adm-btn primary">Check</button></div></form><div id="iam-insp-out"></div><p role="alert" class="adm-error"></p>`, actions:[{label:"Close"}]});
  const go = async e => {
    e?.preventDefault(); const out=root.querySelector("#iam-insp-out"), err=root.querySelector("[role=alert]"); err.textContent="";
    const tgt=root.querySelector("#iam-tgt").value.trim();
    let r; try{ r=await call({op:"iam_inspect", email:root.querySelector("#iam-who").value, perm:root.querySelector("#iam-perm").value||undefined, target:tgt?{email:tgt}:undefined}); }
    catch(x){ err.textContent=x.message; return; }
    const allowed = Object.entries(r.effective).filter(([,v])=>v.allowed), denied = Object.entries(r.effective).filter(([,v])=>v.deny.length);
    const src = v => [...v.allow.map(a=>`<span class="iam-src">${esc(a.via)}${a.scope?.type!=="org"?" · "+esc(scopeText(a.scope)):""}${a.expires?" · until "+esc(day(a.expires)):""}</span>`),
                      ...v.deny.map(a=>`<span class="iam-src no">${esc(a.via)}</span>`)].join(" ");
    out.innerHTML = `${r.answer?`<div class="adm-card adm-pad iam-answer ${r.answer.allowed?"yes":"no"}"><b>${r.answer.allowed?"Yes":"No"}</b> — ${esc(r.email)} ${r.answer.allowed?"can":"cannot"} “${esc(perm(r.answer.perm).name)}”${tgt?" for "+esc(tgt):""}.<br><small>Because: ${esc(r.answer.why)}</small></div>`:""}
      <p class="adm-muted">${esc(r.email)}${r.department?" · "+esc(r.department):""} · ${r.legacy?"No roles here yet: their earlier role in Teams &amp; roles still applies.":r.assignments.roles.map(a=>esc(a.name)).join(", ")||"No roles"}</p>
      <div class="adm-card sc-wrap iam-insp-table"><table class="adm-table"><thead><tr><th>Permission</th><th>Where from</th></tr></thead><tbody>
      ${[...denied.filter(([,v])=>!v.allowed), ...allowed].map(([p,v])=>`<tr><td><b>${esc(perm(p).name)}</b> ${v.allowed?"":`<span class="adm-pill bad">Denied</span>`}<small>${esc(st.data.modules[perm(p).module]||"")}</small></td><td>${src(v)}</td></tr>`).join("")||`<tr><td colspan="2">Nothing allowed.</td></tr>`}</tbody></table></div>
      ${r.requests.length?`<h3 class="adm-h3">Their requests</h3><ul class="adm-list">${r.requests.map(q=>`<li><span>${esc(q.label)} <small class="adm-muted">${esc(q.reason)}</small></span><span class="adm-pill ${q.status==="approved"?"good":q.status==="pending"?"warn":"bad"}">${esc(q.status)}</span></li>`).join("")}</ul>`:""}`;
  };
  root.querySelector("#iam-insp").addEventListener("submit", go);
  if(email) go();
}

/* ---------------- requests ---------------- */
async function requests(el){
  el.innerHTML = `<div class="sc-tools"><select id="iam-rs" aria-label="Status">${[["pending","Waiting"],["approved","Approved"],["rejected","Rejected"],["","All"]].map(([v,l])=>`<option value="${v}" ${st.status===v?"selected":""}>${l}</option>`).join("")}</select></div><div id="iam-rl"><p class="adm-muted">Loading…</p></div>`;
  $("iam-rs").addEventListener("change", e => { st.status=e.target.value; requests(el); });
  let out; try{ out=await call({op:"iam_requests", status:st.status||undefined}); }catch(e){ $("iam-rl").innerHTML=`<p class="adm-error">${esc(e.message)}</p>`; return; }
  const me = h.state.user?.email?.toLowerCase();
  $("iam-rl").innerHTML = out.requests.length ? `<div class="adm-card sc-wrap"><table class="adm-table"><thead><tr><th>Who</th><th>Asks for</th><th>Reason</th><th>Status</th><th></th></tr></thead><tbody>
    ${out.requests.map(r=>{ const approvals=r.votes.filter(v=>v.decision==="approve").length, voted=r.votes.some(v=>v.approver===me);
      return `<tr><td><b>${esc(r.requester)}</b><small>${esc(day(r.created))}${r.ticket?" · ticket "+esc(r.ticket):""}</small></td>
      <td>${esc(r.label)} <small>${r.kind==="role"?"Role":"Permission"} · ${esc(scopeText(r.scope))}${r.hours?" · for "+(r.hours>=24?Math.round(r.hours/24)+" days":r.hours+" hours"):""}</small></td>
      <td><small>${esc(r.reason)}</small></td>
      <td><span class="adm-pill ${r.status==="approved"?"good":r.status==="pending"?"warn":"bad"}">${esc(r.status)}</span>${r.needed>1?`<small>${approvals} of ${r.needed} approvals</small>`:""}${r.votes.map(v=>`<small>${esc(v.decision==="approve"?"Approved":"Rejected")} by ${esc(v.approver)}${v.reason?": "+esc(v.reason):""}</small>`).join("")}</td>
      <td class="adm-right">${r.status==="pending"&&r.requester!==me&&!voted?`<button class="adm-btn primary" data-ok="${esc(r.id)}">Approve</button><button class="adm-btn ghost" data-no="${esc(r.id)}">Reject</button>`:r.requester===me&&r.status==="pending"?`<small class="adm-muted">Your own request</small>`:""}</td></tr>`; }).join("")}</tbody></table></div>`
    : `<p class="adm-muted">No requests here. People ask from Dejoiy Mail, for example with “Request your admin” when outside mail is turned off for them.</p>`;
  el.querySelectorAll("[data-ok]").forEach(b=>b.addEventListener("click",async()=>{ b.disabled=true; try{ const r=await call({op:"iam_decide", id:b.dataset.ok, approve:true}); toast(r.request.status==="approved"?"Approved: access is on now":"Approved. One more person must approve."); await refresh(); requests(el); }catch(e){ toast(e.message); b.disabled=false; } }));
  el.querySelectorAll("[data-no]").forEach(b=>b.addEventListener("click",()=>dialog({title:"Reject the request", body:`<label class="adm-field">Why (they will see this)<input id="iam-why" maxlength="500" required></label><p role="alert" class="adm-error"></p>`,
    actions:[{label:"Cancel"},{label:"Reject", danger:true, fn: async root => { await call({op:"iam_decide", id:b.dataset.no, approve:false, reason:root.querySelector("#iam-why").value}); toast("Rejected"); await refresh(); requests(el); }}]})));
}

/* ---------------- reviews ---------------- */
async function reviews(el, open){
  el.innerHTML = `<div class="sc-tools">${can("roles.revoke")?`<button class="adm-btn primary" id="iam-rv-new">Start an access review</button>`:""}<span class="adm-muted">A review lists everyone with a high or critical role, for someone else to keep or remove.</span></div><div id="iam-rv"><p class="adm-muted">Loading…</p></div>`;
  $("iam-rv-new")?.addEventListener("click", async () => { const r=await call({op:"iam_review_start"}); toast(`Review started: ${r.review.items.length} to check`); reviews(el, r.review.id); });
  let out; try{ out=await call({op:"iam_reviews"}); }catch(e){ $("iam-rv").innerHTML=`<p class="adm-error">${esc(e.message)}</p>`; return; }
  const me = h.state.user?.email?.toLowerCase();
  $("iam-rv").innerHTML = out.reviews.length ? out.reviews.map(r=>{ const done=r.items.filter(i=>i.decision).length;
    return `<details class="adm-card iam-module" ${r.id===open||(!r.closed&&!open)?"open":""}><summary><b>Review of ${esc(day(r.created))}</b> <small class="adm-muted">by ${esc(r.createdBy)} · ${done} of ${r.items.length} decided${r.closed?" · closed":""}</small></summary>
      <table class="adm-table"><tbody>${r.items.map(i=>`<tr><td><b>${esc(i.email)}</b><small>${esc(i.role)}</small></td>
        <td class="adm-right">${i.decision?`<span class="adm-pill ${i.decision==="keep"?"good":"bad"}">${i.decision==="keep"?"Kept":"Removed"}</span><small>${esc(i.by)}</small>`:r.closed||i.email===me?`<small class="adm-muted">${i.email===me?"Someone else reviews yours":""}</small>`:`<button class="adm-btn ghost" data-keep="${esc(r.id)}|${esc(i.assignment)}">Keep</button><button class="adm-btn danger" data-drop="${esc(r.id)}|${esc(i.assignment)}">Remove</button>`}</td></tr>`).join("")||`<tr><td>Nobody with a high or critical role.</td></tr>`}</tbody></table></details>`; }).join("")
    : `<p class="adm-muted">No reviews yet. Run one every quarter, and whenever someone changes job.</p>`;
  const decide = async (v, keep) => { const [id,assignment]=v.split("|"); try{ await call({op:"iam_review_decide", id, assignment, keep}); toast(keep?"Kept":"Removed"); await refresh(); reviews(el, id); }catch(e){ toast(e.message); } };
  el.querySelectorAll("[data-keep]").forEach(b=>b.addEventListener("click",()=>decide(b.dataset.keep,true)));
  el.querySelectorAll("[data-drop]").forEach(b=>b.addEventListener("click",()=>decide(b.dataset.drop,false)));
}

/* ---------------- access log ---------------- */
const ACTION = {"roles.create":"Created a role","roles.edit":"Changed a role","roles.delete":"Deleted a role","roles.assign":"Gave a role","roles.revoke":"Removed a role",
  "permissions.assign":"Allowed a permission","permissions.override":"Denied a permission","permissions.revoke":"Removed a grant","permissions.request":"Asked for access",
  "permissions.approve":"Approved a request","permissions.reject":"Rejected a request","permissions.cancel":"Cancelled a request","security.break_glass":"Used emergency access",
  "roles.review_start":"Started an access review","audit.export":"Exported the log"};
const diff = a => { if(!a.before&&!a.after) return ""; const b=new Set(a.before?.allow||[]), n=new Set(a.after?.allow||[]);
  const plus=[...n].filter(x=>!b.has(x)), minus=[...b].filter(x=>!n.has(x));
  return (plus.length?"<br>+ "+plus.map(x=>esc(perm(x).name)).join(", "):"")+(minus.length?"<br>− "+minus.map(x=>esc(perm(x).name)).join(", "):""); };
async function log(el){
  const f = st.log;
  el.innerHTML = `<div class="sc-tools"><input id="iam-la" type="search" placeholder="Who (email)" value="${esc(f.actor||"")}"><input id="iam-lt" type="search" placeholder="About whom or what" value="${esc(f.target||"")}">
    <select id="iam-lm" aria-label="Kind"><option value="">Every change</option>${[["roles","Roles"],["permissions","Permissions & requests"],["security","Emergency access"],["audit","Exports"]].map(([v,l])=>`<option value="${v}" ${f.module===v?"selected":""}>${l}</option>`).join("")}</select>
    <select id="iam-ls" aria-label="Severity"><option value="">Any severity</option>${["info","high","critical"].map(v=>`<option ${f.severity===v?"selected":""}>${v}</option>`).join("")}</select>
    ${can("audit.export")?`<button class="adm-btn ghost" id="iam-lx">Download CSV</button>`:""}</div><div id="iam-ll"><p class="adm-muted">Loading…</p></div>`;
  const set = (k,v) => { f[k]=v||undefined; clearTimeout(log.t); log.t=setTimeout(()=>load(),250); };
  $("iam-la").addEventListener("input",e=>set("actor",e.target.value.trim()));
  $("iam-lt").addEventListener("input",e=>set("target",e.target.value.trim()));
  $("iam-lm").addEventListener("change",e=>set("module",e.target.value));
  $("iam-ls").addEventListener("change",e=>set("severity",e.target.value));
  $("iam-lx")?.addEventListener("click", async () => { const out=await call({op:"iam_audit", export:true, ...f});
    const a=document.createElement("a"); a.href=URL.createObjectURL(new Blob(["﻿"+out.csv],{type:"text/csv"})); a.download=`access-log-${st.domain}.csv`; a.click(); URL.revokeObjectURL(a.href); });
  const load = async () => {
    let out; try{ out=await call({op:"iam_audit", ...f}); }catch(e){ $("iam-ll").innerHTML=`<p class="adm-error">${esc(e.message)}</p>`; return; }
    $("iam-ll").innerHTML = `<p class="adm-muted">${out.intact?"✓ The log is intact: no entry was changed or removed.":"⚠ The log's chain does not check out. Tell the Dejoiy team."}</p>`+(out.rows.length?`<div class="adm-card sc-wrap"><table class="adm-table"><thead><tr><th>When</th><th>Who</th><th>What</th><th>About</th><th>Details</th></tr></thead><tbody>
      ${out.rows.map(a=>`<tr><td>${esc(day(a.at))}</td><td>${esc(a.actor)}<small>${esc(a.ip||"")}</small></td><td>${esc(ACTION[a.action]||a.action)} ${a.severity==="critical"?pill("critical"):""}</td>
        <td>${esc(a.target)}${a.perm?`<small>${esc(perm(a.perm).name||a.perm)}</small>`:""}</td><td><small>${esc(a.reason||"")}${a.after?.scope&&a.after.scope.type!=="org"?" · "+esc(scopeText(a.after.scope)):""}${a.after?.expires?" · until "+esc(day(a.after.expires)):""}${diff(a)}</small></td></tr>`).join("")}</tbody></table></div>`
      :`<p class="adm-muted">Nothing matches.</p>`);
  };
  load();
}

/* ---------------- emergency access ---------------- */
function breakGlass(){
  dialog({title:"Emergency access", body:`<p>This gives you every permission except reading other people's mail, for one hour. Use it only during a security incident.
    It is written to the access log as critical and every admin can see it.</p><label class="adm-field">What is happening<input id="iam-bg" maxlength="500" required></label><p role="alert" class="adm-error"></p>`,
    actions:[{label:"Cancel"},{label:"Turn on for 1 hour", danger:true, fn: async root => { await call({op:"iam_break_glass", reason:root.querySelector("#iam-bg").value}); toast("Emergency access is on for one hour"); await refresh(); draw(); }}]});
}

window.AdminPages = Object.assign(window.AdminPages || {}, { iam, iamDetail: iam });
})();
