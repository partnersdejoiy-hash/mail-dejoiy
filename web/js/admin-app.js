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
  ["overview","home","Overview"],["users","contacts","Mailboxes"],["org","tag","Teams & roles"],["domains","shield","Domains"],
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
  const main=$("adm-main"), fn=({overview,users,org,domains,lists,plans,settings})[state.section]||overview;
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
function showSignIn(){ location.replace(location.hostname.startsWith("admin-")?"/signin?next=admin":"/?next=admin"); }
if(location.hostname.startsWith("admin-")) $("adm-open-mail").href=location.protocol+"//"+location.host.replace(/^admin-/,"")+"/";
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
  // Zoho-style summary: who is active, who went quiet, who never signed in, who is switched off
  const seen=u=>{ const m=/^(\d{4})(\d\d)(\d\d)/.exec(u.lastLogin||""); return m?Date.UTC(+m[1],m[2]-1,+m[3]):0; }, month=Date.now()-30*864e5;
  const on=d.users.filter(u=>u.status==="active");
  const people=[["Active",on.filter(u=>seen(u)>=month).length,"good"],["Quiet",on.filter(u=>seen(u)&&seen(u)<month).length,"warn"],["Never signed in",on.filter(u=>!seen(u)).length,"mute"],["Switched off",d.users.length-on.length,"bad"]];
  const top=[...d.users].sort((a,b)=>(b.used||0)-(a.used||0)).slice(0,8), biggest=Math.max(1,...top.map(u=>u.used||0));
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
    <div class="adm-two">
      <div class="adm-card"><div class="adm-card-head"><h2>People</h2><a href="#/users">All mailboxes →</a></div>
        <div class="adm-seg" role="img" aria-label="${people.map(p=>p[1]+" "+p[0]).join(", ")}">${people.filter(p=>p[1]).map(p=>`<i class="${p[2]}" style="flex:${p[1]}"></i>`).join("")}</div>
        <ul class="adm-legend">${people.map(p=>`<li><i class="${p[2]}"></i><span>${p[0]}</span><b>${p[1]}</b></li>`).join("")}</ul>
        <p class="adm-muted">Quiet = no sign-in for 30 days. A mailbox nobody uses still counts on your plan.</p></div>
      <div class="adm-card"><div class="adm-card-head"><h2>Mail security</h2><a href="#/domains">Domains →</a></div>
        <div id="ov-dns"><p class="adm-muted">Checking each domain's public DNS…</p></div></div>
    </div>
    <div class="adm-card"><div class="adm-card-head"><h2>Storage by mailbox</h2><a href="#/users">All mailboxes →</a></div>
      <div class="adm-bars">${top.map(u=>`<div class="adm-bar"><span title="${esc(u.email)}">${esc(u.name)}</span>
        <div class="adm-bar-track" role="img" aria-label="${esc(u.name)} uses ${mb(u.used||0)}${u.limit?" of "+mb(u.limit):""}"><i class="${u.limit&&(u.used||0)/u.limit>0.9?"full":""}" style="width:${Math.max(1,Math.round((u.used||0)/(u.limit||biggest)*100))}%"></i></div>
        <small>${mb(u.used||0)}${u.limit?" of "+mb(u.limit):""}</small></div>`).join("")||`<p class="adm-muted">No mailboxes yet.</p>`}</div></div>`;
  $("ov-refresh").addEventListener("click",()=>reload("Refreshed."));
  // Mail security: how many domains have each DNS record live (MX to receive, SPF/DKIM/DMARC to be trusted)
  (async()=>{ const box=$("ov-dns"), domains=d.domains.slice(0,12), tally={};
    for(const x of domains){ try{ const out=await act({op:"dns_records",domain:x.domain});
      for(const r of out.records){ const k=tally[r.kind]=tally[r.kind]||{ok:0,all:0,missing:[]}; k.all++; if(r.ok) k.ok++; else k.missing.push(x.domain); } }catch(_){ /* not allowed or lookup failed: left out */ } }
    if(!$("ov-dns")) return;
    const kinds=Object.entries(tally);
    box.innerHTML=kinds.length?kinds.map(([kind,k])=>`<div class="adm-bar"><span>${esc(kind)}</span>
      <div class="adm-bar-track" role="img" aria-label="${esc(kind)} live on ${k.ok} of ${k.all} domains"><i class="${k.ok===k.all?"good":"warn"}" style="width:${Math.max(2,Math.round(k.ok/k.all*100))}%"></i></div>
      <small>${k.ok}/${k.all}${k.missing.length?` · fix ${esc(k.missing[0])}${k.missing.length>1?" +"+(k.missing.length-1):""}`:""}</small></div>`).join("")
      +(d.domains.length>12?`<p class="adm-muted">First 12 domains checked.</p>`:"")
      :`<p class="adm-muted">DNS couldn't be checked right now. Open Domains → DNS setup for each domain.</p>`; })();
}

/* The mailbox list as a spreadsheet file. Cells starting with = + - @ get a quote so Excel never runs them as formulas. */
function exportUsers(d){
  const cell=v=>{ let t=String(v??""); if(/^[=+\-@]/.test(t)) t="'"+t; return '"'+t.replace(/"/g,'""')+'"'; };
  const rows=[["Name","Email","Status","Department","Title","Role","Used (MB)","Limit (MB)","Last sign-in","Aliases"],
    ...d.users.map(u=>[u.name,u.email,u.status,u.department||"",u.title||"",u.role,u.used==null?"":Math.round(u.used/1048576),u.limit?Math.round(u.limit/1048576):"",when(u.lastLogin),(u.aliases||[]).join(" ")])];
  const a=document.createElement("a"); a.href=URL.createObjectURL(new Blob(["\ufeff"+rows.map(r=>r.map(cell).join(",")).join("\r\n")],{type:"text/csv"}));
  a.download="mailboxes-"+new Date().toISOString().slice(0,10)+".csv"; a.click(); setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}
function users(main, d){
  const plans=d.plans||[], planName=id=>{const n=(id&&plans.find(p=>p.id===id)?.name)||"default";return n.charAt(0).toUpperCase()+n.slice(1);};
  main.innerHTML=head("Mailboxes",`${d.users.length} mailboxes`,`<input type="search" id="u-search" placeholder="Search name or email" aria-label="Search mailboxes"><button class="adm-btn ghost" id="u-export">Export CSV</button>${can("mailboxes.manage")?'<button class="adm-btn primary" id="u-add">+ New mailbox</button>':""}`)+`
    <div class="adm-card adm-flush"><table class="adm-table" id="u-table"><thead><tr><th>Mailbox</th><th>Status</th><th>Department</th><th>Role</th><th>Plan</th><th>Storage</th><th>Last sign-in</th><th></th></tr></thead><tbody>
    ${d.users.map((u,i)=>`<tr data-q="${esc((u.name+" "+u.email+" "+(u.department||"")+" "+(u.title||"")).toLowerCase())}"><td><b>${esc(u.name)}</b><small>${esc(u.email)}</small></td>
      <td><span class="adm-pill ${u.status==="active"?"good":"warn"}">${esc(u.status)}</span></td><td>${esc(u.department||"—")}</td><td>${esc(u.title||u.role)}${u.title?`<small>${esc(u.role)}</small>`:""}</td><td>${esc(planName(u.cosId))}</td>
      <td>${mb(u.used)}${u.limit?` <small>of ${mb(u.limit)}</small>`:""}</td><td><small>${esc(when(u.lastLogin))}</small></td>
      <td><button class="adm-btn ghost sm" data-edit="${i}">Manage</button></td></tr>`).join("")}
    </tbody></table></div>`;
  $("u-export").addEventListener("click",()=>exportUsers(d));
  $("u-search").addEventListener("input",e=>{const q=e.target.value.trim().toLowerCase();main.querySelectorAll("#u-table tbody tr").forEach(r=>r.hidden=!r.dataset.q.includes(q));});
  $("u-add")?.addEventListener("click",()=>dialog({title:"New mailbox",body:`
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
      ${d.departments?`<label>Department<select id="mu-dept"><option value="">No department</option>${d.departments.map(x=>`<option value="${esc(x.id)}" ${x.name===u.department?"selected":""}>${esc(x.name)} · ${esc(x.email)}</option>`).join("")}</select></label>`:""}
      <label>Role<select id="mu-title"><option value="">No role</option>${companyRoles(d,u).map(r=>`<option value="${esc(r.name)}" ${r.name===u.title?"selected":""}>${esc(r.name)}${r.access==="Domain admin"?" · company admin":""}</option>`).join("")}</select></label>
      <button class="adm-btn" id="mu-org-save">Save department &amp; role</button>
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
  root.querySelector("#mu-org-save").addEventListener("click",async e=>{
    const b=e.currentTarget;b.disabled=true;err.textContent="";
    try{
      const dept=root.querySelector("#mu-dept"); if(dept && dept.value!==(d.departments.find(x=>x.name===u.department)?.id||"")) await act({op:"set_department",id:u.id,department:dept.value});
      const title=$("mu-title").value; if(title!==(u.title||"")){
        await act({op:"set_title",id:u.id,title});
        // A role carries its access level: company-admin roles make the person a company admin.
        const access=companyRoles(d,u).find(r=>r.name===title)?.access||"User";
        if(!self && u.role!=="Admin" && access!==u.role) await act({op:"role",id:u.id,role:access});
      }
      $("adm-dialog-root").innerHTML=""; await reload("Department and role saved.");
    }catch(x){err.textContent=x.message;b.disabled=false;}
  });
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

const companyRoles = (d, u) => (d.domains.find(x=>u&&u.email.endsWith("@"+x.domain)) || d.domains.find(x=>x.domain===d.scope) || d.domains[0] || {}).roles || [];

// What the signed-in admin's role allows; platform admins (perms null) can do everything.
const can = perm => !state.data?.perms || state.data.perms.includes(perm);
const CONSOLE_ONLY = perm => perm !== "updates.post";

function org(main, d){
  const domain = d.scope || d.domains[0]?.domain || "", here = d.domains.find(x=>x.domain===domain) || {}, roles = here.roles || [];
  const perms = d.permissions || {}, editRoles = can("roles.manage"), editTeams = can("teams.manage");
  const count = name => d.users.filter(u=>u.department===name).length, holders = name => d.users.filter(u=>u.title===name).length;
  main.innerHTML=head("Teams & roles","Run the company like business units: departments, roles and what each role may do. Saved on the mail server.")+`
    <div class="adm-card"><div class="adm-card-head"><h2>Company box</h2></div>
      <p class="adm-muted">Every mailbox in ${esc(domain||"your company")} gets a page for company updates. Name it after your company; roles with "${esc(perms["updates.post"]||"Post in the company box")}" can post there.</p>
      <div class="adm-add"><input id="o-box" maxlength="40" value="${esc(here.boxName||"")}" placeholder="Company updates" aria-label="Company box name" ${editRoles?"":"disabled"}>
      ${editRoles?`<button class="adm-btn primary" id="o-box-save">Save name</button>`:""}</div></div>
    <div class="adm-card"><div class="adm-card-head"><h2>Departments</h2>${d.departments&&editTeams?`<button class="adm-btn primary" id="o-dept-add">+ New department</button>`:""}</div>
      ${!d.departments?`<p class="adm-muted">Departments are not available for your administrator role.</p>`:`
      <p class="adm-muted">Each department has its own address. Mail sent to it reaches everyone in the department.</p>
      <table class="adm-table"><thead><tr><th>Department</th><th>People</th><th></th></tr></thead><tbody>
      ${d.departments.map((x,i)=>`<tr><td><b>${esc(x.name||x.email)}</b><small>${esc(x.email)}</small></td><td>${count(x.name)}</td>
        <td class="adm-right">${editTeams?`<button class="adm-btn ghost sm" data-dmem="${i}">People</button> <button class="adm-btn ghost sm" data-ddel="${i}">Delete</button>`:""}</td></tr>`).join("")||`<tr><td class="adm-muted" colspan="3">No departments yet. Start with one like Sales, Support or Accounts.</td></tr>`}
      </tbody></table>`}</div>
    <div class="adm-card"><div class="adm-card-head"><h2>Roles &amp; permissions${domain?` · ${esc(domain)}`:""}</h2>${editRoles?`<button class="adm-btn ghost" id="o-role-add">+ Add role</button>`:""}</div>
      <p class="adm-muted">Pick what each role may do. Admin-console permissions need company admin access. A company admin without a role can do everything.</p>
      <div class="adm-roles" id="o-roles">
      ${roles.map((r,i)=>`<div class="adm-role"><div class="adm-role-head">
          <input data-rname="${i}" value="${esc(r.name)}" maxlength="40" aria-label="Role name" ${editRoles?"":"disabled"}>
          <select data-raccess="${i}" aria-label="Access for ${esc(r.name)}" ${editRoles?"":"disabled"}><option value="User" ${r.access==="User"?"selected":""}>Mail only</option><option value="Domain admin" ${r.access==="Domain admin"?"selected":""}>Company admin</option></select>
          <span class="adm-muted">${holders(r.name)} ${holders(r.name)===1?"person":"people"}</span>
          ${editRoles?`<button class="adm-btn ghost sm" data-rdel="${i}">Remove</button>`:""}</div>
        <div class="adm-perms">${Object.entries(perms).map(([key,label])=>{const off=!editRoles||(r.access!=="Domain admin"&&CONSOLE_ONLY(key));
          return `<label class="adm-check ${off&&r.access!=="Domain admin"&&CONSOLE_ONLY(key)?"is-off":""}"><input type="checkbox" data-rperm="${i}" value="${key}" ${(r.perms||[]).includes(key)&&!(r.access!=="Domain admin"&&CONSOLE_ONLY(key))?"checked":""} ${off?"disabled":""}> ${esc(label)}</label>`;}).join("")}</div></div>`).join("")}
      </div><p role="alert" class="adm-error" id="o-err"></p>${editRoles?`<button class="adm-btn primary" id="o-roles-save">Save roles</button>`:""}</div>`;
  let list = roles.map(r=>({...r, perms:[...(r.perms||[])]}));
  const sync = ()=>{
    main.querySelectorAll("[data-rname]").forEach(i=>list[+i.dataset.rname].name=i.value);
    main.querySelectorAll("[data-raccess]").forEach(i=>list[+i.dataset.raccess].access=i.value);
    list.forEach((r,i)=>{ r.perms=[...main.querySelectorAll(`[data-rperm="${i}"]:checked`)].map(x=>x.value).filter(p=>r.access==="Domain admin"||!CONSOLE_ONLY(p)); });
  };
  // Unsaved role edits redraw from the list being edited, not from the server copy.
  const redraw = change=>{ sync(); change(); org(main,{...d,domains:d.domains.map(x=>x.domain===domain?{...x,roles:list}:x)}); };
  main.querySelectorAll("[data-raccess]").forEach(sel=>sel.addEventListener("change",()=>redraw(()=>{})));
  if(editRoles){
    $("o-role-add").addEventListener("click",()=>{ redraw(()=>list.push({name:"New role",access:"User",perms:[]})); main.querySelector(`[data-rname="${list.length-1}"]`)?.select(); });
    main.querySelectorAll("[data-rdel]").forEach(b=>b.addEventListener("click",()=>redraw(()=>list.splice(+b.dataset.rdel,1))));
    $("o-roles-save").addEventListener("click",async e=>{ const b=e.currentTarget; sync(); b.disabled=true;
      try{ await act({op:"save_roles",domain,roles:list}); await reload("Roles saved."); }catch(x){ $("o-err").textContent=x.message; b.disabled=false; } });
    $("o-box-save").addEventListener("click",async e=>{ const b=e.currentTarget; b.disabled=true;
      try{ await act({op:"company_settings",domain,boxName:$("o-box").value}); await reload("Company box renamed."); }catch(x){ toast(x.message); b.disabled=false; } });
  }
  if(!d.departments || !editTeams) return;
  $("o-dept-add").addEventListener("click",()=>dialog({title:"New department",body:`
    <label>Department name<input id="nd-dname" maxlength="64" placeholder="Sales"></label>
    <label>Department email<input id="nd-demail" type="email" placeholder="sales@${esc(domain||"example.com")}"></label>
    <p class="adm-muted">Add people from each mailbox's Profile tab, or with People here.</p><p role="alert" class="adm-error"></p>`,
    actions:[{label:"Cancel"},{label:"Create department",primary:true,fn:async()=>{await act({op:"create_department",name:$("nd-dname").value,email:$("nd-demail").value});await reload("Department created.");}}]}));
  main.querySelectorAll("[data-ddel]").forEach(b=>b.addEventListener("click",()=>{const x=d.departments[+b.dataset.ddel];confirmDialog("Delete department",`Delete ${x.name}? Its address ${x.email} stops working. People keep their mailboxes.`,"Delete",async()=>{await act({op:"delete_list",id:x.id});await reload("Department deleted.");});}));
  main.querySelectorAll("[data-dmem]").forEach(b=>b.addEventListener("click",()=>deptPeople(d.departments[+b.dataset.dmem], d)));
}
function deptPeople(x, d){
  const inIt=d.users.filter(u=>u.department===x.name), others=d.users.filter(u=>u.department!==x.name && u.email.endsWith("@"+x.email.split("@")[1]));
  const root=dialog({title:x.name,body:`<ul class="adm-list">${inIt.map(u=>`<li><span>${esc(u.name)} <small>${esc(u.email)}</small></span><button class="adm-btn ghost sm" data-out="${esc(u.id)}">Remove</button></li>`).join("")||'<li class="adm-muted">Nobody in this department yet.</li>'}</ul>
    ${others.length?`<label>Add a person<select id="dp-add">${others.map(u=>`<option value="${esc(u.id)}">${esc(u.name)} · ${esc(u.email)}${u.department?" (now in "+esc(u.department)+")":""}</option>`).join("")}</select></label><button class="adm-btn primary" id="dp-add-btn">Add to ${esc(x.name)}</button>`:""}<p role="alert" class="adm-error"></p>`});
  const err=root.querySelector("[role=alert]");
  const move=async(id,department,b)=>{b.disabled=true;try{await act({op:"set_department",id,department});$("adm-dialog-root").innerHTML="";await reload("Department updated.");}catch(e){err.textContent=e.message;b.disabled=false;}};
  root.querySelectorAll("[data-out]").forEach(b=>b.addEventListener("click",()=>move(b.dataset.out,"",b)));
  root.querySelector("#dp-add-btn")?.addEventListener("click",e=>move($("dp-add").value,x.id,e.currentTarget));
}

function domains(main, d){
  main.innerHTML=head("Domains","Mail domains this organisation receives mail for.",d.scope?"":`<button class="adm-btn primary" id="d-add">+ Add domain</button>`)+`
    <div class="adm-card adm-flush"><table class="adm-table"><thead><tr><th>Domain</th><th>Mailboxes</th><th>Status</th><th></th></tr></thead><tbody>
    ${d.domains.map((x,i)=>`<tr><td><b>${esc(x.domain)}</b></td><td>${d.users.filter(u=>u.email.endsWith("@"+x.domain)).length}</td>
      <td>${d.scope?`<span class="adm-pill ${x.status==="active"?"good":"warn"}">${esc(x.status)}</span>`:`<select data-dstatus="${i}" aria-label="Status for ${esc(x.domain)}">${["active","locked","maintenance","suspended"].map(s=>`<option ${s===x.status?"selected":""}>${s}</option>`).join("")}</select>`}</td>
      <td class="adm-right"><button class="adm-btn ghost sm" data-dns="${esc(x.domain)}">DNS setup</button> <button class="adm-btn ghost sm" data-host="${esc(x.domain)}">Sign-in address</button>${d.scope?"":` <button class="adm-btn ghost sm" data-ddel="${i}" aria-label="Delete ${esc(x.domain)}">Delete</button>`}</td></tr>`).join("")}
    </tbody></table></div>
    <div class="adm-card"><h2>DNS checklist</h2><p class="adm-muted">Adding a domain here does not change public DNS. At your DNS provider, point <b>MX</b> to this server and publish <b>SPF</b>, <b>DKIM</b> and <b>DMARC</b> records so mail is delivered and trusted.</p></div>`;
  main.querySelectorAll("[data-dstatus]").forEach(s=>s.addEventListener("change",async()=>{const x=d.domains[+s.dataset.dstatus];s.disabled=true;try{await act({op:"domain_status",id:x.id,status:s.value});x.status=s.value;toast("Domain status updated.");}catch(e){s.value=x.status;toast(e.message);}finally{s.disabled=false;}}));
  main.querySelectorAll("[data-dns]").forEach(b=>b.addEventListener("click",()=>dnsSetup(b.dataset.dns)));
  main.querySelectorAll("[data-host]").forEach(b=>b.addEventListener("click",()=>loginHost(b.dataset.host)));
  main.querySelectorAll("[data-ddel]").forEach(b=>b.addEventListener("click",()=>deleteDomain(d,d.domains[+b.dataset.ddel])));
  if(!d.scope) $("d-add").addEventListener("click",()=>dialog({title:"Add domain",body:`<label>Domain name<input id="nd-name" placeholder="example.com" autocomplete="off"></label><p role="alert" class="adm-error"></p>`,
    actions:[{label:"Cancel"},{label:"Add domain",primary:true,fn:async()=>{await act({op:"create_domain",domain:$("nd-name").value});await reload("Domain added. Configure its DNS next.");}}]}));
}

// A domain can only go once it is empty: Zimbra refuses otherwise, so say so up front.
function deleteDomain(d, x){
  const boxes=d.users.filter(u=>u.email.toLowerCase().endsWith("@"+x.domain)).length;
  const lists=(d.lists||[]).concat(d.departments||[]).filter(l=>String(l.email||"").toLowerCase().endsWith("@"+x.domain)).length;
  if(boxes||lists) return dialog({title:"Delete "+x.domain,
    body:`<p><b>${esc(x.domain)}</b> still has ${boxes?`${boxes} mailbox${boxes===1?"":"es"}`:""}${boxes&&lists?" and ":""}${lists?`${lists} mailing list${lists===1?"":"s"}`:""}.</p>
      <p class="adm-muted">Delete or move them first, then delete the domain. This keeps anyone's mail from disappearing by accident.</p>`,
    actions:[{label:"Close"},...(boxes?[{label:"Show mailboxes",primary:true,fn:()=>{location.hash="#/users";}}]:[])]});
  dialog({title:"Delete "+x.domain,
    body:`<p>This removes <b>${esc(x.domain)}</b> from Dejoiy Mail. It has no mailboxes, so no mail is lost. You can add it again later.</p>
      <p class="adm-muted">Also remove its MX, SPF, DKIM and DMARC records at your DNS provider.</p>
      <label>Type <b>${esc(x.domain)}</b> to confirm<input id="dd-confirm" autocomplete="off" spellcheck="false"></label><p role="alert" class="adm-error"></p>`,
    actions:[{label:"Cancel"},{label:"Delete domain",danger:true,fn:async()=>{
      if($("dd-confirm").value.trim().toLowerCase()!==x.domain.toLowerCase()) throw new Error("Type the domain name exactly to confirm.");
      await act({op:"delete_domain",id:x.id,confirm:$("dd-confirm").value.trim()}); await reload(x.domain+" deleted.");}}]});
}

/* A company's own sign-in address (mail.theircompany.com) and how its sign-in page looks. */
async function loginHost(domain){
  const root=dialog({title:"Sign-in address · "+domain, wide:true, body:`<p class="adm-muted">Loading…</p>`});
  const body=root.querySelector(".adm-dialog-body");
  const draw=(out,note)=>{
    const b=out.brand||{}, suggested="mail."+domain;
    body.innerHTML=`${note?`<p class="${note.bad?"adm-error":"adm-muted"}" role="status">${esc(note.text)}</p>`:""}
      <p>Let your team sign in at your own address instead of ${esc(out.target)}. Only ${esc(domain)} mailboxes can sign in there.</p>
      <div class="adm-form">
        <label>Your address<input id="lh-host" value="${esc(out.host||suggested)}" placeholder="${esc(suggested)}" autocapitalize="off" spellcheck="false"></label>
        <label>Company name on the sign-in page<input id="lh-name" maxlength="60" value="${esc(b.name||"")}" placeholder="Your company"></label>
        <label>One line under it<input id="lh-tag" maxlength="120" value="${esc(b.tagline||"")}" placeholder="Mail for the whole team"></label>
        <label>Button colour<input id="lh-colour" type="color" value="${esc(b.colour||"#ff4fa3")}"></label>
      </div>
      <div class="adm-dns-row ${out.pointing?"ok":""}"><div class="adm-dns-head"><b>Step 1 · DNS</b><span class="adm-pill ${out.pointing?"good":"warn"}">${out.host?(out.pointing?"Pointing here":"Not pointing here"):"Not set up"}</span></div>
        <dl><dt>Type</dt><dd><code>CNAME</code></dd><dt>Host</dt><dd><code id="lh-label">${esc((out.host||suggested).split(".")[0])}</code></dd><dt>Value</dt><dd><code>${esc(out.target)}</code></dd></dl>
        <p class="adm-muted">Add this where ${esc(domain)}'s DNS is managed, wait a few minutes, then press Save.</p></div>
      <div class="adm-dns-row"><div class="adm-dns-head"><b>Step 2 · Secure connection</b></div>
        <p class="adm-muted">After you save, the padlock (HTTPS certificate) is set up by itself within about 10 minutes. Until then the address may show a warning; nothing else changes for your team.</p></div>
      <div class="adm-dialog-actions">${out.host?`<button class="adm-btn ghost" id="lh-remove">Remove address</button>`:""}<button class="adm-btn primary" id="lh-save">Save</button></div>`;
    $("lh-host").addEventListener("input",e=>{ $("lh-label").textContent=e.target.value.trim().split(".")[0]||"mail"; });
    $("lh-save").addEventListener("click",async()=>{ const btn=$("lh-save"); btn.disabled=true;
      try{ draw(await act({op:"login_host_set",domain,host:$("lh-host").value,name:$("lh-name").value,tagline:$("lh-tag").value,colour:$("lh-colour").value}),{text:"Saved. Your address will be ready in about 10 minutes."}); }
      catch(e){ btn.disabled=false; const old=body.querySelector("[role=status]"); if(old) old.remove(); body.insertAdjacentHTML("afterbegin",`<p class="adm-error" role="status">${esc(e.message)}</p>`); } });
    const rm=$("lh-remove"); if(rm) rm.addEventListener("click",async()=>{ try{ draw(await act({op:"login_host_remove",domain}),{text:"Removed. Your team signs in at "+out.target+" again."}); }catch(e){ draw(out,{text:e.message,bad:true}); } });
  };
  try{ draw(await act({op:"login_host_get",domain})); }catch(e){ body.innerHTML=`<p class="adm-error">${esc(e.message)}</p>`; }
}

async function dnsSetup(domain){
  const root=dialog({title:"DNS setup · "+domain, wide:true, body:`<p class="adm-muted">Checking public DNS…</p>`});
  const draw=async()=>{
    let out; try{ out=await act({op:"dns_records",domain}); }catch(e){ root.querySelector(".adm-dialog-body").innerHTML=`<p class="adm-error">${esc(e.message)}</p>`; return; }
    const done=out.records.filter(r=>r.ok).length;
    root.querySelector(".adm-dialog-body").innerHTML=`<p>Add these records where <b>${esc(domain)}</b>'s DNS is managed. <b>${done} of ${out.records.length}</b> are live.</p>
      <div class="adm-dns">${out.records.map((r,i)=>`<div class="adm-dns-row ${r.ok?"ok":""}">
        <div class="adm-dns-head"><b>${esc(r.kind)}</b><span class="adm-pill ${r.ok?"good":"warn"}">${r.ok?"Live":r.pending?"Preparing":r.status==="conflict"?"Needs a fix":"Not found"}</span></div>${r.purpose?`<p class="adm-muted">${esc(r.purpose)}</p>`:""}
        ${r.pending?`<p class="adm-muted">The signing key for this domain is being created. Check again in two minutes.</p>`:`
        <dl><dt>Type</dt><dd><code>${esc(r.type)}</code>${r.priority?` · priority <code>${r.priority}</code>`:""}</dd>
        <dt>Host</dt><dd><code>${esc(r.host)}</code></dd>
        <dt>Value</dt><dd><code class="adm-dns-value">${esc(r.value)}</code> <button class="adm-btn ghost sm" data-copy="${i}">Copy</button></dd></dl>${r.note?`<p class="adm-error">${esc(r.note)}</p>`:""}`}</div>`).join("")}</div>
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
    <label>Minimum password length<input id="pl-min" type="number" min="10" max="64" value="${Math.max(10,p.passwordMinLength)}"></label>
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
if("serviceWorker" in navigator && location.protocol==="https:") navigator.serviceWorker.register("/sw.js").catch(()=>{});
