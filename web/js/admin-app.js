/* ============ Dejoiy Mail Admin — admin-app.js : standalone organisation console ============
   Talks only to the Dejoiy adapter (/api/admin*). The adapter applies every change to the mail
   server's own configuration, so settings stay where the server keeps them. */
(function(){
"use strict";

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const icon = name => window.Icons ? Icons.get(name) : "";
const mb = bytes => bytes == null ? "—" : bytes >= 1073741824 ? (bytes/1073741824).toFixed(1)+" GB" : bytes >= 1048576 ? Math.round(bytes/1048576)+" MB" : Math.max(0,Math.round(bytes/1024))+" KB";
const when = stamp => { const m=/^(\d{4})(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)/.exec(stamp||""); if(!m) return "Never"; const d=new Date(Date.UTC(+m[1],m[2]-1,+m[3],+m[4],+m[5],+m[6])); return d.toLocaleString([],{dateStyle:"medium",timeStyle:"short"}); };

const SECTIONS = [
  ["overview","home","Overview"],["users","contacts","Mailboxes"],["domains","shield","Domains"],
  ["lists","mail","Mailing lists"],["plans","tag","Plans"],["settings","settings","Settings"]
];

const state = { csrf:"", user:null, data:null, section:(location.hash.slice(2)||"overview") };

/* ---------------- server ---------------- */
async function api(path, body){
  const res = await fetch("/api/"+path, {method: body===undefined?"GET":"POST", credentials:"same-origin",
    headers: body===undefined?{}:{"Content-Type":"application/json","X-CSRF-Token":state.csrf},
    body: body===undefined?undefined:JSON.stringify(body)});
  let out = {}; try{ out = await res.json(); }catch(_){}
  if(!res.ok){ const e = new Error(out.error || "Request failed"); e.status = res.status; throw e; }
  return out;
}
async function act(payload){
  try{ return await api("admin/action", payload); }
  catch(e){ if(e.status===403 && /Sign in to Dejoiy Mail Admin/.test(e.message)){ $("adm-dialog-root").innerHTML=""; showVerify("Your admin session timed out. Enter your password to continue."); } throw e; }
}

/* ---------------- shell ---------------- */
function toast(text){ const t=document.createElement("div"); t.className="adm-toast"; t.textContent=text; $("adm-toasts").appendChild(t); setTimeout(()=>t.remove(),3800); }
function dialog({title, body, actions=[{label:"Close"}], wide}){
  const root=$("adm-dialog-root");
  root.innerHTML=`<div class="adm-backdrop"><div class="adm-dialog ${wide?"wide":""}" role="dialog" aria-modal="true" aria-labelledby="adm-dlg-title">
    <div class="adm-dialog-head"><h2 id="adm-dlg-title">${esc(title)}</h2><button class="adm-icon-btn" data-close aria-label="Close">×</button></div>
    <div class="adm-dialog-body">${body}</div>
    <div class="adm-dialog-foot">${actions.map((a,i)=>`<button class="adm-btn ${a.primary?"primary":a.danger?"danger":"ghost"}" data-act="${i}">${esc(a.label)}</button>`).join("")}</div></div></div>`;
  const close=()=>{root.innerHTML="";document.removeEventListener("keydown",onKey);};
  const onKey=e=>{if(e.key==="Escape")close();};
  document.addEventListener("keydown",onKey);
  root.querySelector("[data-close]").addEventListener("click",close);
  root.querySelector(".adm-backdrop").addEventListener("click",e=>{if(e.target.classList.contains("adm-backdrop"))close();});
  actions.forEach((a,i)=>root.querySelector(`[data-act="${i}"]`).addEventListener("click",async ev=>{
    if(!a.fn){close();return;}
    const btn=ev.currentTarget; btn.disabled=true;
    try{ if(await a.fn(root)!==false) close(); }catch(e){ const err=root.querySelector("[role=alert]"); if(err) err.textContent=e.message; else toast(e.message); }
    finally{ btn.disabled=false; }
  }));
  const first=root.querySelector("input,select,textarea,button.primary"); if(first) first.focus();
  return root;
}
function confirmDialog(title, text, label, fn){ dialog({title, body:`<p>${esc(text)}</p><p role="alert" class="adm-error"></p>`, actions:[{label:"Cancel"},{label, danger:true, fn}]}); }

// Company admins manage their own domain; plans and server settings stay with the platform team.
const visibleSections = () => state.data?.scope ? SECTIONS.filter(([id])=>!["plans","settings"].includes(id)) : SECTIONS;
const roles = () => ["User","Domain admin",...(state.user?.canManageRoles?["Admin"]:[])];
function renderNav(){
  const nav=$("adm-nav"); nav.hidden=false;
  if(!visibleSections().some(([id])=>id===state.section)) state.section="overview";
  nav.innerHTML=visibleSections().map(([id,ico,label])=>`<a href="#/${id}" class="${state.section===id?"active":""}" ${state.section===id?'aria-current="page"':""}>${icon(ico)}<span>${label}</span></a>`).join("");
}
window.addEventListener("hashchange",()=>{ state.section=location.hash.slice(2)||"overview"; if(state.data){ renderNav(); renderSection(); } });

async function load(){
  try{ state.data = await api("admin"); }
  catch(e){ if(e.status===401) return showSignIn(); if(e.status===403) return showVerify(e.message); throw e; }
  $("adm-account").hidden=false; $("adm-who").textContent=state.data.scope?`${state.user?.email||""} · ${state.data.scope}`:state.user?.email||"";
  renderNav(); renderSection();
}
function renderSection(){
  const main=$("adm-main"), fn=({overview,users,domains,lists,plans,settings})[state.section]||overview;
  fn(main, state.data); main.focus({preventScroll:true});
}
const reload = async msg => { if(msg) toast(msg); await load(); };

/* ---------------- sign-in ---------------- */
function authCard(inner){
  $("adm-nav").hidden=true; $("adm-account").hidden=true;
  $("adm-main").innerHTML=`<div class="adm-auth"><form class="adm-card adm-auth-card">${inner}<p role="alert" class="adm-error"></p></form>
    <p class="adm-muted adm-auth-foot">Dejoiy Mail Admin · for organisation administrators</p></div>`;
  return $("adm-main").querySelector("form");
}
// The console is only served to signed-in administrators; signing in happens in the mail app.
function showSignIn(){ location.replace("/?next=admin"); }
function showVerify(message){
  const form=authCard(`<h1>Confirm it's you</h1><p class="adm-muted">Signed in as <b>${esc(state.user?.email||"")}</b>. Admin access locks after 15 minutes.</p>
    <label>Administrator password<input name="password" type="password" autocomplete="current-password" required></label>
    <button class="adm-btn primary wide">Unlock admin</button>
    <button class="adm-btn ghost wide" type="button" id="adm-switch">Use a different account</button>`);
  if(message && !/Sign in to Dejoiy Mail Admin/.test(message)) form.querySelector("[role=alert]").textContent=message;
  form.querySelector("#adm-switch").addEventListener("click",async()=>{ try{await api("logout",{});}catch(_){} showSignIn(); });
  form.addEventListener("submit",async e=>{
    e.preventDefault(); const btn=form.querySelector("button"); btn.disabled=true;
    try{ await api("admin/login",{password:form.elements.password.value}); form.reset(); await load(); }
    catch(err){ form.elements.password.value=""; form.querySelector("[role=alert]").textContent=err.message; btn.disabled=false; }
  });
}
$("adm-lock").addEventListener("click",async()=>{ try{ await api("admin/logout",{}); }catch(_){} state.data=null; showVerify(); });

/* ---------------- sections ---------------- */
function head(title, sub, extra=""){ return `<div class="adm-head"><div><h1>${esc(title)}</h1>${sub?`<p class="adm-muted">${esc(sub)}</p>`:""}</div><div class="adm-head-actions">${extra}</div></div>`; }
const unavailable = what => `<div class="adm-card adm-muted">${esc(what)} is not available for your administrator role.</div>`;

function overview(main, d){
  const used=d.users.reduce((n,u)=>n+(u.used||0),0), stopped=(d.services||[]).filter(s=>!s.running);
  main.innerHTML=head("Overview",d.scope?`Your company mail on ${d.scope}.`:"Your organisation at a glance.",`<button class="adm-btn ghost" id="ov-refresh">${icon("refresh")} Refresh</button>`)+`
    <div class="adm-stats">
      <a class="adm-card adm-stat" href="#/users"><b>${d.users.length}</b><span>Mailboxes</span></a>
      <a class="adm-card adm-stat" href="#/domains"><b>${d.domains.length}</b><span>Domains</span></a>
      <a class="adm-card adm-stat" href="#/lists"><b>${d.lists?d.lists.length:"—"}</b><span>Mailing lists</span></a>
      <div class="adm-card adm-stat"><b>${mb(used)}</b><span>Storage used</span></div>
    </div>
    <div class="adm-card"><div class="adm-card-head"><h2>Server health</h2>${d.services?`<span class="adm-pill ${stopped.length?"bad":"good"}">${stopped.length?stopped.length+" stopped":"All running"}</span>`:""}</div>
      ${d.scope?`<p class="adm-muted">Dejoiy monitors the mail servers for you around the clock.</p>`:d.services?`<div class="adm-services">${d.services.map(s=>`<div class="adm-service ${s.running?"up":"down"}"><i aria-hidden="true"></i><span>${esc(s.service)}</span><small>${s.running?"Running":"Stopped"}</small></div>`).join("")}</div>`:`<p class="adm-muted">Server health is available to full administrators.</p>`}
    </div>
    <div class="adm-card"><div class="adm-card-head"><h2>Largest mailboxes</h2><a href="#/users">All mailboxes →</a></div>
      <table class="adm-table"><thead><tr><th>Mailbox</th><th>Used</th><th>Limit</th></tr></thead><tbody>
      ${[...d.users].sort((a,b)=>(b.used||0)-(a.used||0)).slice(0,5).map(u=>`<tr><td><b>${esc(u.name)}</b><small>${esc(u.email)}</small></td><td>${mb(u.used)}</td><td>${u.limit?mb(u.limit):"Unlimited"}</td></tr>`).join("")}
      </tbody></table></div>`;
  $("ov-refresh").addEventListener("click",()=>reload("Refreshed."));
}

function users(main, d){
  const plans=d.plans||[], planName=id=>{const n=(id&&plans.find(p=>p.id===id)?.name)||"default";return n.charAt(0).toUpperCase()+n.slice(1);};
  main.innerHTML=head("Mailboxes",`${d.users.length} mailboxes`,`<input type="search" id="u-search" placeholder="Search name or email" aria-label="Search mailboxes"><button class="adm-btn primary" id="u-add">+ New mailbox</button>`)+`
    <div class="adm-card adm-flush"><table class="adm-table" id="u-table"><thead><tr><th>Mailbox</th><th>Status</th><th>Role</th><th>Plan</th><th>Storage</th><th>Last sign-in</th><th></th></tr></thead><tbody>
    ${d.users.map((u,i)=>`<tr data-q="${esc((u.name+" "+u.email).toLowerCase())}"><td><b>${esc(u.name)}</b><small>${esc(u.email)}</small></td>
      <td><span class="adm-pill ${u.status==="active"?"good":"warn"}">${esc(u.status)}</span></td><td>${esc(u.role)}</td><td>${esc(planName(u.cosId))}</td>
      <td>${mb(u.used)}${u.limit?` <small>of ${mb(u.limit)}</small>`:""}</td><td><small>${esc(when(u.lastLogin))}</small></td>
      <td><button class="adm-btn ghost sm" data-edit="${i}">Manage</button></td></tr>`).join("")}
    </tbody></table></div>`;
  $("u-search").addEventListener("input",e=>{const q=e.target.value.trim().toLowerCase();main.querySelectorAll("#u-table tbody tr").forEach(r=>r.hidden=!r.dataset.q.includes(q));});
  $("u-add").addEventListener("click",()=>dialog({title:"New mailbox",body:`
    <label>Display name<input id="nu-name" maxlength="200" required></label>
    <label>Email address<input id="nu-email" type="email" placeholder="name@${esc(d.domains[0]?.domain||"example.com")}" required></label>
    <label>Initial password<input id="nu-pass" type="password" autocomplete="new-password" required></label>
    <label>Role<select id="nu-role"><option value="User">User — mail access</option><option value="Domain admin">Domain admin — manages ${esc(d.scope||"this domain")}</option>${state.user?.canManageRoles?'<option value="Admin">Platform administrator — every domain</option>':""}</select></label>
    <p role="alert" class="adm-error"></p>`,actions:[{label:"Cancel"},{label:"Create mailbox",primary:true,fn:async()=>{
      await act({op:"create_user",name:$("nu-name").value,email:$("nu-email").value,password:$("nu-pass").value,role:$("nu-role").value});
      await reload("Mailbox created.");}}]}));
  main.querySelectorAll("[data-edit]").forEach(b=>b.addEventListener("click",()=>manageUser(d.users[+b.dataset.edit], d)));
}

function manageUser(u, d){
  const plans=d.plans||[], self=u.email.toLowerCase()===(state.user?.email||"").toLowerCase();
  const root=dialog({title:u.email, wide:true, body:`
    <div class="adm-tabs" role="tablist">${["Profile","Access","Storage","Forwarding","Aliases","Password","Delete"].map((t,i)=>`<button role="tab" data-tab="${i}" class="${i?"":"on"}" aria-selected="${!i}">${t}</button>`).join("")}</div>
    <section data-panel="0"><label>Display name<input id="mu-name" value="${esc(u.name)}" maxlength="200"></label><button class="adm-btn primary" id="mu-name-save">Save name</button>
      <dl class="adm-facts"><dt>Created</dt><dd>${esc(when(u.created))}</dd><dt>Last sign-in</dt><dd>${esc(when(u.lastLogin))}</dd></dl></section>
    <section data-panel="1" hidden><label>Status<select id="mu-status" ${self?"disabled":""}>${["active","locked","maintenance"].map(s=>`<option ${s===u.status?"selected":""}>${s}</option>`).join("")}</select></label>
      ${!self&&(state.user?.canManageRoles||u.role!=="Admin")?`<label>Role<select id="mu-role">${roles().map(r=>`<option ${r===u.role?"selected":""}>${r}</option>`).join("")}</select></label>`:`<p class="adm-muted">Role: ${esc(u.role)}</p>`}
      <button class="adm-btn primary" id="mu-access-save" ${self?"disabled":""}>Save access</button>${self?'<p class="adm-muted">You cannot lock or demote your own mailbox.</p>':""}</section>
    <section data-panel="2" hidden><p>Using <b>${mb(u.used)}</b>${u.limit?` of ${mb(u.limit)}`:" · no limit"}.</p>
      ${plans.length?`<label>Plan<select id="mu-plan"><option value="">Default plan</option>${plans.map(p=>`<option value="${esc(p.id)}" ${p.id===u.cosId?"selected":""}>${esc(p.name)} · ${p.quotaMB?p.quotaMB+" MB":"unlimited"}</option>`).join("")}</select></label><button class="adm-btn" id="mu-plan-save">Save plan</button>`:""}
      <label>Mailbox limit override (MB, 0 = use plan / unlimited)<input id="mu-quota" type="number" min="0" step="1" value="${Math.round(Number(u.quota||0)/1048576)}"></label><button class="adm-btn primary" id="mu-quota-save">Save limit</button></section>
    <section data-panel="3" hidden><label>Forward incoming mail to (comma separated, up to 10)<input id="mu-fwd" value="${esc(u.forward)}" placeholder="someone@example.com"></label>
      <label class="adm-check"><input type="checkbox" id="mu-keep" ${u.keepCopy?"checked":""}> Keep a copy in this mailbox</label><button class="adm-btn primary" id="mu-fwd-save">Save forwarding</button></section>
    <section data-panel="4" hidden><ul class="adm-list">${(u.aliases||[]).map((a,i)=>`<li><span>${esc(a)}</span><button class="adm-btn ghost sm" data-rm-alias="${i}">Remove</button></li>`).join("")||'<li class="adm-muted">No aliases yet.</li>'}</ul>
      <label>New alias<input id="mu-alias" type="email" placeholder="alias@${esc(u.email.split("@")[1])}"></label><button class="adm-btn primary" id="mu-alias-add">Add alias</button></section>
    <section data-panel="5" hidden><label>New password<input id="mu-pass" type="password" autocomplete="new-password"></label><button class="adm-btn primary" id="mu-pass-save">Set password</button></section>
    <section data-panel="6" hidden>${self?'<p class="adm-muted">You cannot delete your own mailbox.</p>':`<p>Deleting removes this mailbox and all of its mail permanently.</p>
      <label>Type <b>${esc(u.email)}</b> to confirm<input id="mu-confirm" autocomplete="off"></label><button class="adm-btn danger" id="mu-delete">Delete mailbox</button>`}</section>
    <p role="alert" class="adm-error"></p>`});
  const err=root.querySelector("[role=alert]");
  root.querySelectorAll("[data-tab]").forEach(t=>t.addEventListener("click",()=>{root.querySelectorAll("[data-tab]").forEach(x=>{x.classList.toggle("on",x===t);x.setAttribute("aria-selected",String(x===t));});root.querySelectorAll("[data-panel]").forEach(p=>p.hidden=p.dataset.panel!==t.dataset.tab);err.textContent="";}));
  const run=(id,payload,done)=>{const b=root.querySelector("#"+id);if(b)b.addEventListener("click",async()=>{b.disabled=true;err.textContent="";try{await act(payload());$("adm-dialog-root").innerHTML="";await reload(done);}catch(e){err.textContent=e.message;b.disabled=false;}});};
  run("mu-name-save",()=>({op:"set_name",id:u.id,name:$("mu-name").value}),"Name saved.");
  root.querySelector("#mu-access-save").addEventListener("click",async e=>{
    const b=e.currentTarget;b.disabled=true;err.textContent="";
    try{ const status=$("mu-status").value; if(status!==u.status) await act({op:"status",id:u.id,status});
      const role=root.querySelector("#mu-role")?.value; if(role&&role!==u.role) await act({op:"role",id:u.id,role});
      $("adm-dialog-root").innerHTML=""; await reload("Access updated."); }catch(x){err.textContent=x.message;b.disabled=false;}
  });
  run("mu-plan-save",()=>({op:"set_plan",id:u.id,planId:$("mu-plan").value}),"Plan updated.");
  run("mu-quota-save",()=>({op:"quota",id:u.id,quotaMB:Number($("mu-quota").value)}),"Limit saved.");
  run("mu-fwd-save",()=>({op:"forward",id:u.id,forward:$("mu-fwd").value,keepCopy:$("mu-keep").checked}),"Forwarding saved.");
  run("mu-alias-add",()=>({op:"add_alias",id:u.id,alias:$("mu-alias").value}),"Alias added.");
  root.querySelectorAll("[data-rm-alias]").forEach(b=>b.addEventListener("click",async()=>{b.disabled=true;try{await act({op:"remove_alias",id:u.id,alias:u.aliases[+b.dataset.rmAlias]});$("adm-dialog-root").innerHTML="";await reload("Alias removed.");}catch(e){err.textContent=e.message;b.disabled=false;}}));
  run("mu-pass-save",()=>({op:"password",id:u.id,password:$("mu-pass").value}),"Password updated.");
  run("mu-delete",()=>({op:"delete_user",id:u.id,confirm:$("mu-confirm").value}),"Mailbox deleted.");
}

function domains(main, d){
  main.innerHTML=head("Domains","Mail domains this organisation receives mail for.",d.scope?"":`<button class="adm-btn primary" id="d-add">+ Add domain</button>`)+`
    <div class="adm-card adm-flush"><table class="adm-table"><thead><tr><th>Domain</th><th>Mailboxes</th><th>Status</th><th></th></tr></thead><tbody>
    ${d.domains.map((x,i)=>`<tr><td><b>${esc(x.domain)}</b></td><td>${d.users.filter(u=>u.email.endsWith("@"+x.domain)).length}</td>
      <td>${d.scope?`<span class="adm-pill ${x.status==="active"?"good":"warn"}">${esc(x.status)}</span>`:`<select data-dstatus="${i}" aria-label="Status for ${esc(x.domain)}">${["active","locked","maintenance","suspended"].map(s=>`<option ${s===x.status?"selected":""}>${s}</option>`).join("")}</select>`}</td>
      <td class="adm-right"><button class="adm-btn ghost sm" data-dns="${esc(x.domain)}">DNS setup</button></td></tr>`).join("")}
    </tbody></table></div>
    <div class="adm-card"><h2>DNS checklist</h2><p class="adm-muted">Adding a domain here does not change public DNS. At your DNS provider, point <b>MX</b> to this server and publish <b>SPF</b>, <b>DKIM</b> and <b>DMARC</b> records so mail is delivered and trusted.</p></div>`;
  main.querySelectorAll("[data-dstatus]").forEach(s=>s.addEventListener("change",async()=>{const x=d.domains[+s.dataset.dstatus];s.disabled=true;try{await act({op:"domain_status",id:x.id,status:s.value});x.status=s.value;toast("Domain status updated.");}catch(e){s.value=x.status;toast(e.message);}finally{s.disabled=false;}}));
  main.querySelectorAll("[data-dns]").forEach(b=>b.addEventListener("click",()=>dnsSetup(b.dataset.dns)));
  if(!d.scope) $("d-add").addEventListener("click",()=>dialog({title:"Add domain",body:`<label>Domain name<input id="nd-name" placeholder="example.com" autocomplete="off"></label><p role="alert" class="adm-error"></p>`,
    actions:[{label:"Cancel"},{label:"Add domain",primary:true,fn:async()=>{await act({op:"create_domain",domain:$("nd-name").value});await reload("Domain added. Configure its DNS next.");}}]}));
}

async function dnsSetup(domain){
  const root=dialog({title:"DNS setup · "+domain, wide:true, body:`<p class="adm-muted">Checking public DNS…</p>`});
  const draw=async()=>{
    let out; try{ out=await act({op:"dns_records",domain}); }catch(e){ root.querySelector(".adm-dialog-body").innerHTML=`<p class="adm-error">${esc(e.message)}</p>`; return; }
    const done=out.records.filter(r=>r.ok).length;
    root.querySelector(".adm-dialog-body").innerHTML=`<p>Add these records where <b>${esc(domain)}</b>'s DNS is managed. <b>${done} of ${out.records.length}</b> are live.</p>
      <div class="adm-dns">${out.records.map((r,i)=>`<div class="adm-dns-row ${r.ok?"ok":""}">
        <div class="adm-dns-head"><b>${esc(r.kind)}</b><span class="adm-pill ${r.ok?"good":"warn"}">${r.ok?"Live":r.pending?"Preparing":"Not found"}</span></div>
        ${r.pending?`<p class="adm-muted">The signing key for this domain is being created. Check again in two minutes.</p>`:`
        <dl><dt>Type</dt><dd><code>${esc(r.type)}</code>${r.priority?` · priority <code>${r.priority}</code>`:""}</dd>
        <dt>Host</dt><dd><code>${esc(r.host)}</code></dd>
        <dt>Value</dt><dd><code class="adm-dns-value">${esc(r.value)}</code> <button class="adm-btn ghost sm" data-copy="${i}">Copy</button></dd></dl>`}</div>`).join("")}</div>
      <p class="adm-muted">DNS changes can take up to an hour to appear. MX makes mail arrive; SPF, DKIM and DMARC make sure it is trusted and not marked as spam.</p>
      <button class="adm-btn primary" id="dns-recheck">Check again</button>`;
    root.querySelectorAll("[data-copy]").forEach(b=>b.addEventListener("click",async()=>{try{await navigator.clipboard.writeText(out.records[+b.dataset.copy].value);b.textContent="Copied";}catch(_){b.textContent="Select to copy";}}));
    root.querySelector("#dns-recheck").addEventListener("click",()=>{root.querySelector(".adm-dialog-body").innerHTML=`<p class="adm-muted">Checking public DNS…</p>`;draw();});
  };
  draw();
}

function lists(main, d){
  if(!d.lists){ main.innerHTML=head("Mailing lists")+unavailable("Mailing lists"); return; }
  main.innerHTML=head("Mailing lists","One address that delivers to many people.",`<button class="adm-btn primary" id="l-add">+ New list</button>`)+`
    <div class="adm-card adm-flush"><table class="adm-table"><thead><tr><th>List</th><th></th></tr></thead><tbody>
    ${d.lists.map((l,i)=>`<tr><td><b>${esc(l.name||l.email)}</b><small>${esc(l.email)}</small></td><td class="adm-right"><button class="adm-btn ghost sm" data-members="${i}">Members</button> <button class="adm-btn ghost sm" data-ldel="${i}">Delete</button></td></tr>`).join("")||`<tr><td class="adm-muted">No mailing lists yet.</td><td></td></tr>`}
    </tbody></table></div>`;
  $("l-add").addEventListener("click",()=>dialog({title:"New mailing list",body:`<label>List address<input id="nl-email" type="email" placeholder="team@${esc(d.domains[0]?.domain||"example.com")}"></label><label>Name (optional)<input id="nl-name" maxlength="200"></label><p role="alert" class="adm-error"></p>`,
    actions:[{label:"Cancel"},{label:"Create list",primary:true,fn:async()=>{await act({op:"create_list",email:$("nl-email").value,name:$("nl-name").value});await reload("Mailing list created.");}}]}));
  main.querySelectorAll("[data-ldel]").forEach(b=>b.addEventListener("click",()=>{const l=d.lists[+b.dataset.ldel];confirmDialog("Delete mailing list",`Delete ${l.email}? Mail sent to it will bounce.`,"Delete",async()=>{await act({op:"delete_list",id:l.id});await reload("Mailing list deleted.");});}));
  main.querySelectorAll("[data-members]").forEach(b=>b.addEventListener("click",()=>members(d.lists[+b.dataset.members])));
}
async function members(l){
  const root=dialog({title:l.email,body:`<p class="adm-muted">Loading members…</p>`});
  const draw=async()=>{
    let list=[]; try{ list=(await act({op:"list_members",id:l.id})).members; }catch(e){ root.querySelector(".adm-dialog-body").innerHTML=`<p class="adm-error">${esc(e.message)}</p>`; return; }
    root.querySelector(".adm-dialog-body").innerHTML=`<ul class="adm-list">${list.map((m,i)=>`<li><span>${esc(m)}</span><button class="adm-btn ghost sm" data-rm="${i}">Remove</button></li>`).join("")||'<li class="adm-muted">No members yet.</li>'}</ul>
      <label>Add member<input id="lm-add" type="email" placeholder="person@example.com"></label><button class="adm-btn primary" id="lm-add-btn">Add</button><p role="alert" class="adm-error"></p>`;
    const err=root.querySelector("[role=alert]");
    root.querySelector("#lm-add-btn").addEventListener("click",async e=>{e.currentTarget.disabled=true;try{await act({op:"add_member",id:l.id,member:$("lm-add").value});await draw();}catch(x){err.textContent=x.message;e.currentTarget.disabled=false;}});
    root.querySelectorAll("[data-rm]").forEach(b=>b.addEventListener("click",async()=>{b.disabled=true;try{await act({op:"remove_member",id:l.id,member:list[+b.dataset.rm]});await draw();}catch(x){err.textContent=x.message;b.disabled=false;}}));
  };
  draw();
}

function plans(main, d){
  if(!d.plans){ main.innerHTML=head("Plans")+unavailable("Plans"); return; }
  main.innerHTML=head("Plans","Default limits and password rules applied to groups of mailboxes.")+`
    <div class="adm-card adm-flush"><table class="adm-table"><thead><tr><th>Plan</th><th>Mailboxes</th><th>Storage</th><th>Min. password</th><th>Password expiry</th><th></th></tr></thead><tbody>
    ${d.plans.map((p,i)=>`<tr><td><b>${esc(p.name)}</b></td><td>${d.users.filter(u=>u.cosId===p.id||(!u.cosId&&p.name==="default")).length}</td><td>${p.quotaMB?p.quotaMB+" MB":"Unlimited"}</td><td>${p.passwordMinLength} characters</td><td>${p.passwordMaxAgeDays?p.passwordMaxAgeDays+" days":"Never"}</td>
      <td class="adm-right"><button class="adm-btn ghost sm" data-plan="${i}">Edit</button></td></tr>`).join("")}
    </tbody></table></div>`;
  main.querySelectorAll("[data-plan]").forEach(b=>b.addEventListener("click",()=>{const p=d.plans[+b.dataset.plan];dialog({title:"Edit plan · "+p.name,body:`
    <label>Mailbox storage (MB, 0 = unlimited)<input id="pl-q" type="number" min="0" value="${p.quotaMB}"></label>
    <label>Minimum password length<input id="pl-min" type="number" min="6" max="64" value="${Math.max(6,p.passwordMinLength)}"></label>
    <label>Password expires after (days, 0 = never)<input id="pl-age" type="number" min="0" max="3650" value="${p.passwordMaxAgeDays}"></label><p role="alert" class="adm-error"></p>`,
    actions:[{label:"Cancel"},{label:"Save plan",primary:true,fn:async()=>{await act({op:"plan_update",id:p.id,quotaMB:Number($("pl-q").value),passwordMinLength:Number($("pl-min").value),passwordMaxAgeDays:Number($("pl-age").value)});await reload("Plan saved.");}}]});}));
}

function settings(main, d){
  if(!d.settings){ main.innerHTML=head("Settings")+unavailable("Server settings"); return; }
  const s=d.settings;
  main.innerHTML=head("Settings","Organisation-wide mail limits and protection.")+`
    <form class="adm-card adm-form" id="st-form">
      <label>Maximum message size (MB)<input name="maxMessageMB" type="number" min="1" max="100" value="${s.maxMessageMB}"></label>
      <label>Maximum attachment upload (MB)<input name="uploadMaxMB" type="number" min="1" max="100" value="${s.uploadMaxMB}"></label>
      <label>Blocked attachment types<input name="blocked" value="${esc(s.blockedExtensions.join(", "))}" placeholder="exe, bat, js"></label>
      <p class="adm-muted">Messages with these file extensions are rejected. Separate with commas. Only full administrators can change these settings.</p>
      <p role="alert" class="adm-error"></p><button class="adm-btn primary">Save settings</button></form>`;
  $("st-form").addEventListener("submit",async e=>{e.preventDefault();const f=e.currentTarget,b=f.querySelector("button");b.disabled=true;
    try{await act({op:"settings_update",maxMessageMB:Number(f.elements.maxMessageMB.value),uploadMaxMB:Number(f.elements.uploadMaxMB.value),blockedExtensions:f.elements.blocked.value.split(/[\s,]+/).map(x=>x.replace(/^\./,"").toLowerCase()).filter(Boolean)});await reload("Settings saved.");}
    catch(x){f.querySelector("[role=alert]").textContent=x.message;b.disabled=false;}});
}

/* ---------------- start ---------------- */
(async function start(){
  try{ const s=await api("session"); state.csrf=s.csrf; state.user=s.user; }
  catch(e){ return showSignIn(); }
  if(state.user.isAdmin!==true) return showSignIn("This mailbox is not an administrator. Sign in with an administrator mailbox.");
  try{ await load(); }catch(e){ $("adm-main").innerHTML=`<div class="adm-card adm-error">${esc(e.message)}</div>`; }
})();
})();
