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

/* The console tree (like a mail server's admin console): [path under /admin/, icon, label, page, platform team only] */
const P = true;
const TREE = [
  ["Monitor",[["monitor/overview","home","Overview","overview"],["monitor/servers","settings","Server status","servers",P],
    ["monitor/statistics","refresh","Server statistics","statistics",P],["monitor/mail-queues","mail","Mail queues","queues",P],
    ["monitor/sessions","contacts","Active sessions","sessions"],["monitor/reports","note","Reports","reports"]]],
  ["Manage",[["manage/accounts","contacts","Accounts","users"],["manage/teams","tag","Teams & roles","org"],
    ["manage/lists","mail","Distribution lists","lists"],["manage/resources","calendar","Resources","resources"],
    ["manage/domains","building","Domains","domains"],["manage/chat","chat","Chat & meetings","shine"]]],
  ["Configure",[["configure/cos","tag","Class of service","cos",P],["configure/global-settings","settings","Global settings","globalSettings",P],
    ["configure/policies","shield","Mailbox policies","policies"],["configure/admins","shield","Admins & rights","rights",P],
    ["configure/zimlets","layoutlist","Add-ons","zimlets",P],["configure/certificates","check","Certificates","certs",P],
    ["configure/retention","archive","Retention","retention",P],["configure/webhooks","refresh","Webhooks","webhooks"],["configure/api-tokens","shield","API tokens","apiTokens"]]],
  ["Tools",[["tools/bulk-import","compose","Bulk import","bulkImport"],["tools/mailbox","inbox","Mailbox tools","mailboxTools"],
    ["tools/caches","refresh","Server caches","caches",P]]],
  ["Search",[["search","search","Search directory","search"]]]
];
// old #/links keep working
const LEGACY = {overview:"monitor/overview",users:"manage/accounts",org:"manage/teams",domains:"manage/domains",lists:"manage/lists",
  policies:"configure/policies",reports:"monitor/reports",shine:"manage/chat",plans:"configure/cos",settings:"configure/global-settings"};
const routePath = () => { const p=location.pathname.replace(/^\/admin\/?/,"").replace(/\/+$/,""); return p||"monitor/overview"; };

const state = { csrf:"", user:null, data:null, section:routePath() };

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

// Company admins manage their own domain; server-wide items stay with the platform team.
const visibleTree = () => TREE.map(([g,items])=>[g,items.filter(x=>!(x[4]&&state.data?.scope))]).filter(([,items])=>items.length);
const roles = () => ["User","Domain admin",...(state.user?.canManageRoles?["Admin"]:[])];
// the page for a path: its tree entry, plus what follows it (an id, like manage/accounts/<id>)
function findRoute(path){
  for(const [group,items] of visibleTree()) for(const item of items)
    if(path===item[0]||path.startsWith(item[0]+"/")) return {group,item,rest:path.slice(item[0].length+1)};
  return null;
}
function renderNav(){
  const nav=$("adm-nav"); nav.hidden=false;
  const at=findRoute(state.section)?.item[0];
  nav.innerHTML=visibleTree().map(([group,items])=>`<div class="adm-nav-group"><p>${esc(group)}</p>${items.map(([path,ico,label])=>
    `<a href="/admin/${path}" class="${at===path?"active":""}" ${at===path?'aria-current="page"':""}>${icon(ico)}<span>${esc(label)}</span></a>`).join("")}</div>`).join("");
}
function navigate(path, replace){
  const url="/admin/"+path.replace(/^\/+/,"");
  if(replace) history.replaceState(null,"",url); else history.pushState(null,"",url);
  state.section=routePath(); if(state.data){ renderNav(); renderSection(); }
}
document.addEventListener("click",e=>{
  const a=e.target.closest?.("a[href^='/admin/']");
  if(!a||e.defaultPrevented||e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||a.target) return;
  e.preventDefault(); navigate(a.getAttribute("href").slice(7));
});
window.addEventListener("popstate",()=>{ state.section=routePath(); if(state.data){ renderNav(); renderSection(); } });
if(location.hash.startsWith("#/")) history.replaceState(null,"","/admin/"+(LEGACY[location.hash.slice(2)]||"monitor/overview"));
state.section=routePath();

async function load(){
  try{ state.data = await api("admin"); }
  catch(e){ if(e.status===401) return showSignIn(); if(e.status===403) return showVerify(e.message); throw e; }
  const ts=$("adm-top-search"); ts.hidden=false;
  ts.onsubmit=e=>{ e.preventDefault(); const q=ts.elements.q.value.trim(); history.pushState(null,"","/admin/search"+(q?"?q="+encodeURIComponent(q):"")); state.section="search"; renderNav(); renderSection(); };
  $("adm-account").hidden=false; $("adm-who").textContent=state.data.scope?`${state.user?.email||""} · ${state.data.scope}`:state.user?.email||"";
  renderNav(); renderSection();
}
function renderSection(){
  const main=$("adm-main"), found=findRoute(state.section);
  if(!found){ navigate("monitor/overview",true); return; }
  const pages={overview,users,org,domains,lists,policies,reports,shine,plans,settings,...(window.AdminPages||{})};
  const fn=(found.rest&&pages[found.item[3]+"Detail"])||pages[found.item[3]]||overview;
  document.title=found.item[2]+" · Dejoiy Mail Admin";
  Promise.resolve(fn(main, state.data, helpers, found.rest)).catch(e=>{ main.innerHTML=head(found.item[2])+`<div class="adm-card adm-error">${esc(e.message)}</div>`; });
  const crumb=$("adm-crumb"); if(crumb) crumb.textContent=found.group+" › "+found.item[2];
  main.focus({preventScroll:true});
}
const reload = async msg => { if(msg) toast(msg); await load(); };

/* ---------------- sign-in ---------------- */
function authCard(inner){
  $("adm-nav").hidden=true; $("adm-account").hidden=true; $("adm-top-search").hidden=true; $("adm-crumb").textContent="";
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
      <a class="adm-card adm-stat" href="/admin/manage/accounts"><b>${d.users.length}</b><span>Mailboxes</span></a>
      <a class="adm-card adm-stat" href="/admin/manage/domains"><b>${d.domains.length}</b><span>Domains</span></a>
      <a class="adm-card adm-stat" href="/admin/manage/lists"><b>${d.lists?d.lists.length:"—"}</b><span>Mailing lists</span></a>
      <div class="adm-card adm-stat"><b>${mb(used)}</b><span>Storage used</span></div>
    </div>
    <div class="adm-card"><div class="adm-card-head"><h2>Server health</h2>${d.services?`<span class="adm-pill ${stopped.length?"bad":"good"}">${stopped.length?stopped.length+" stopped":"All running"}</span>`:""}</div>
      ${d.scope?`<p class="adm-muted">Dejoiy monitors the mail servers for you around the clock.</p>`:d.services?`<div class="adm-services">${d.services.map(s=>`<div class="adm-service ${s.running?"up":"down"}"><i aria-hidden="true"></i><span>${esc(s.service)}</span><small>${s.running?"Running":"Stopped"}</small></div>`).join("")}</div>`:`<p class="adm-muted">Server health is available to full administrators.</p>`}
    </div>
    <div class="adm-two">
      <div class="adm-card"><div class="adm-card-head"><h2>People</h2><a href="/admin/manage/accounts">All mailboxes →</a></div>
        <div class="adm-seg" role="img" aria-label="${people.map(p=>p[1]+" "+p[0]).join(", ")}">${people.filter(p=>p[1]).map(p=>`<i class="${p[2]}" style="flex:${p[1]}"></i>`).join("")}</div>
        <ul class="adm-legend">${people.map(p=>`<li><i class="${p[2]}"></i><span>${p[0]}</span><b>${p[1]}</b></li>`).join("")}</ul>
        <p class="adm-muted">Quiet = no sign-in for 30 days. A mailbox nobody uses still counts on your plan.</p></div>
      <div class="adm-card"><div class="adm-card-head"><h2>Mail security</h2><a href="/admin/manage/domains">Domains →</a></div>
        <div id="ov-dns"><p class="adm-muted">Checking each domain's public DNS…</p></div></div>
    </div>
    <div class="adm-card"><div class="adm-card-head"><h2>Storage by mailbox</h2><a href="/admin/manage/accounts">All mailboxes →</a></div>
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
/* Policies: the rules a company sets for its own mailboxes. Every rule is a setting on the mail server, which enforces it. */
const RULES=[
  ["passwordMinLength","Shortest password","characters","number"],["passwordMaxAgeDays","Change password every","days (0 = never)","number"],
  ["passwordHistory","Can't reuse the last","passwords (0 = allowed)","number"],["lockoutAfter","Lock the mailbox after","wrong passwords (0 = never)","number"],
  ["lockoutMinutes","Stay locked for","minutes","number"],["sessionHours","Sign out automatically after","hours","number"],
  ["trashDays","Empty Trash after","days","number"],["spamDays","Empty Spam after","days","number"],
  ["forwarding","Forwarding mail to another address","","switch"],["imap","Other mail apps (IMAP: Outlook, phone mail)","","switch"],["pop","Downloading mail with POP","","switch"]];
const ruleLine=(p)=>{ const r=p.rules; return [`${r.passwordMinLength}+ character passwords`,r.passwordMaxAgeDays?`changed every ${r.passwordMaxAgeDays} days`:"",
  r.lockoutAfter?`locks after ${r.lockoutAfter} wrong tries`:"never locks",`signs out after ${r.sessionHours} h`,r.forwarding?"forwarding allowed":"no forwarding",r.imap?"mail apps allowed":"web only"].filter(Boolean).join(" · "); };
async function policies(main, d){
  const domains=d.domains.map(x=>x.domain); let domain=d.scope||state.policyDomain||domains[0];
  if(!domain){ main.innerHTML=head("Policies","Add a domain first.",""); return; }
  main.innerHTML=head("Policies","Rules for your mailboxes: passwords, lock-out, sign-out, forwarding and mail apps.",
    (d.scope||domains.length<2?"":`<select id="po-domain" aria-label="Company domain">${domains.map(x=>`<option ${x===domain?"selected":""}>${esc(x)}</option>`).join("")}</select>`)+`<button class="adm-btn primary" id="po-add">+ New policy</button>`)+`<div id="po-body"><p class="adm-muted">Loading…</p></div>`;
  const pick=$("po-domain"); if(pick) pick.addEventListener("change",()=>{ state.policyDomain=pick.value; policies(main,d); });
  let out; try{ out=await act({op:"policies_get",domain}); }catch(e){ if($("po-body")) $("po-body").innerHTML=`<p class="adm-error">${esc(e.message)}</p>`; return; }
  if(!$("po-body")) return;
  let list=out.policies, def=out.default; const limits=out.limits;
  const people=d.users.filter(u=>u.email.toLowerCase().endsWith("@"+domain));
  const save=async(next,nextDefault,done)=>{ const r=await act({op:"policies_save",domain,policies:next,default:nextDefault});
    list=r.policies; def=r.default; toast(`${done} Applied to ${r.applied} mailbox${r.applied===1?"":"es"}${r.failed?`; ${r.failed} could not be updated`:""}.`); await load(); };
  const edit=(i)=>{ const isNew=i<0, p=isNew?{name:"",rules:{...list.find(x=>x.name===def).rules}}:list[i];
    const root=dialog({title:isNew?"New policy":"Edit policy · "+p.name, wide:true, body:`<div class="adm-form">
      <label>Policy name<input id="pe-name" maxlength="40" value="${esc(p.name)}" placeholder="e.g. Managers, Interns, Strict"></label>
      ${RULES.map(([k,label,unit,kind])=>kind==="number"
        ?`<label class="adm-rule"><span>${label}</span><span><input type="number" id="pe-${k}" min="${limits[k][0]}" max="${limits[k][1]}" value="${p.rules[k]}" inputmode="numeric"> <small>${unit} · ${limits[k][0]} to ${limits[k][1]}</small></span></label>`
        :`<label class="adm-rule adm-check"><span>${label}</span><input type="checkbox" id="pe-${k}" ${p.rules[k]?"checked":""}></label>`).join("")}
      <p class="adm-muted">Turning forwarding off also stops mail that is already being forwarded. A shorter sign-out time applies from each person's next sign-in.</p></div>`,
      actions:[{label:"Cancel"},{label:isNew?"Create policy":"Save and apply",primary:true,fn:async()=>{
        const rules={}; for(const [k,,,kind] of RULES) rules[k]=kind==="number"?parseInt($("pe-"+k).value,10):$("pe-"+k).checked;
        const item={name:$("pe-name").value.trim(),rules}, next=isNew?[...list,item]:list.map((x,j)=>j===i?item:x);
        await save(next, !isNew&&def===p.name?item.name:def, isNew?"Policy created.":"Policy saved.");
      }}]}); void root; };
  const draw=()=>{ $("po-body").innerHTML=`
    <div class="adm-policies">${list.map((p,i)=>{ const n=people.filter(u=>(u.policy||def)===p.name).length; return `<div class="adm-card adm-policy">
      <div class="adm-card-head"><h2>${esc(p.name)}</h2>${p.name===def?`<span class="adm-pill good">New mailboxes get this</span>`:""}</div>
      <p>${esc(ruleLine(p))}</p><p class="adm-muted">${n} mailbox${n===1?"":"es"}</p>
      <div class="adm-dialog-actions">${p.name===def?"":`<button class="adm-btn ghost sm" data-default="${i}">Make default</button>`}${list.length>1&&p.name!==def?`<button class="adm-btn ghost sm" data-del="${i}">Delete</button>`:""}<button class="adm-btn sm" data-edit-policy="${i}">Edit</button></div></div>`; }).join("")}</div>
    <div class="adm-card adm-flush"><div class="adm-card-head adm-pad"><h2>Who follows which policy</h2></div>
      ${people.length?`<table class="adm-table"><thead><tr><th>Mailbox</th><th>Policy</th></tr></thead><tbody>${people.map(u=>`<tr><td><b>${esc(u.name)}</b><small>${esc(u.email)}</small></td>
        <td><select data-assign="${esc(u.id)}" aria-label="Policy for ${esc(u.email)}">${u.policy?"":`<option value="" selected>Not set yet (${esc(def)})</option>`}${list.map(p=>`<option ${u.policy===p.name?"selected":""}>${esc(p.name)}</option>`).join("")}</select></td></tr>`).join("")}</tbody></table>`
        :`<p class="adm-muted adm-pad">No mailboxes on ${esc(domain)} yet.</p>`}</div>`;
    $("po-body").querySelectorAll("[data-edit-policy]").forEach(b=>b.addEventListener("click",()=>edit(+b.dataset.editPolicy)));
    $("po-body").querySelectorAll("[data-default]").forEach(b=>b.addEventListener("click",async()=>{ try{ await save(list,list[+b.dataset.default].name,"Default changed."); }catch(e){ toast(e.message); } }));
    $("po-body").querySelectorAll("[data-del]").forEach(b=>b.addEventListener("click",()=>{ const p=list[+b.dataset.del];
      dialog({title:"Delete "+p.name+"?",body:`<p>Mailboxes on <b>${esc(p.name)}</b> move to <b>${esc(def)}</b> right away.</p>`,actions:[{label:"Cancel"},{label:"Delete policy",danger:true,fn:()=>save(list.filter(x=>x!==p),def,"Policy deleted.")}]}); }));
    $("po-body").querySelectorAll("[data-assign]").forEach(sel=>sel.addEventListener("change",async()=>{ if(!sel.value) return;
      try{ await act({op:"policy_assign",id:sel.dataset.assign,policy:sel.value}); const u=d.users.find(u=>u.id===sel.dataset.assign); if(u) u.policy=sel.value; toast("Policy applied."); draw(); }
      catch(e){ toast(e.message); draw(); } }));
  };
  $("po-add").addEventListener("click",()=>edit(-1));
  draw();
}

/* Chat & meetings: Shine managed here, with the same sign-in and the same company limits as mail. */
async function shine(main, d){
  main.innerHTML=head("Chat & meetings",d.scope?`Shine for ${d.scope}: people, channels and live meetings.`:"Shine across all companies: people, channels and live meetings.",`<button class="adm-btn ghost" id="sh-refresh">${icon("refresh")} Refresh</button>`)+`<div id="sh-body"><p class="adm-muted">Loading…</p></div>`;
  $("sh-refresh").addEventListener("click",()=>shine(main,d));
  let r; try{ r=await act({op:"shine_summary"}); }catch(e){ if($("sh-body")) $("sh-body").innerHTML=`<div class="adm-card"><p class="adm-error">${esc(e.message)}</p></div>`; return; }
  if(!$("sh-body")) return;
  const t=r.totals, at=ms=>ms?new Date(ms).toLocaleString([], {day:"numeric",month:"short",hour:"numeric",minute:"2-digit"}):"—";
  const dot={online:["good","Active"],away:["warn","Away"],busy:["bad","Do not disturb"],offline:["","Offline"]};
  const ACTS={"user.activated":"Switched an account on","user.deactivated":"Switched an account off","meeting.ended":"Ended a meeting","device.registered":"Signed in on a new device"};
  $("sh-body").innerHTML=`
    <div class="adm-stats">
      <div class="adm-card adm-stat"><b>${t.people}</b><span>People in Shine</span></div>
      <div class="adm-card adm-stat"><b>${t.activeNow}</b><span>Active right now</span></div>
      <div class="adm-card adm-stat"><b>${t.messages}${t.messagesCapped?"+":""}</b><span>Messages (7 days)</span></div>
      <div class="adm-card adm-stat"><b>${t.liveMeetings}</b><span>Live meetings</span></div>
    </div>
    <div class="adm-card adm-flush"><div class="adm-card-head adm-pad"><h2>Live meetings</h2></div>
      ${r.meetings.length?`<table class="adm-table"><thead><tr><th>Meeting</th><th>Host</th><th>Started</th><th>People in it</th><th></th></tr></thead><tbody>${r.meetings.map(m=>`<tr><td><b>${esc(m.title)}</b></td><td>${esc(m.host)}</td><td><small>${at(m.startedAt)}</small></td><td>${m.people}</td>
        <td class="adm-right">${can("mailboxes.manage")?`<button class="adm-btn ghost sm" data-end="${esc(m.id)}" data-title="${esc(m.title)}">End meeting</button>`:""}</td></tr>`).join("")}</tbody></table>`
        :`<p class="adm-muted adm-pad">No meetings are running.</p>`}</div>
    <div class="adm-card adm-flush"><div class="adm-card-head adm-pad"><h2>People</h2><input type="search" id="sh-search" placeholder="Search name or email" aria-label="Search people in Shine"></div>
      <table class="adm-table" id="sh-people"><thead><tr><th>Person</th><th>Now</th><th>Role in Shine</th><th>Last seen</th><th>Chat access</th><th></th></tr></thead><tbody>
      ${r.people.map(p=>`<tr data-q="${esc((p.name+" "+p.email).toLowerCase())}"><td><b>${esc(p.name)}</b><small>${esc(p.email)}</small></td>
        <td><span class="adm-pill ${dot[p.status]?.[0]||""}">${dot[p.status]?.[1]||"Offline"}</span></td><td>${esc(String(p.role).replace(/_/g," "))}</td><td><small>${at(p.lastSeen)}</small></td>
        <td><span class="adm-pill ${p.active?"good":"bad"}">${p.active?"On":"Switched off"}</span></td>
        <td class="adm-right">${can("mailboxes.manage")?`<button class="adm-btn ghost sm" data-toggle="${esc(p.email)}" data-on="${p.active?1:0}">${p.active?"Switch off":"Switch on"}</button>`:""}</td></tr>`).join("")||`<tr><td colspan="6"><p class="adm-muted">Nobody has opened Shine yet. People appear here after their first sign-in, or when the mailbox list syncs.</p></td></tr>`}
      </tbody></table></div>
    <div class="adm-two">
      <div class="adm-card adm-flush"><div class="adm-card-head adm-pad"><h2>Channels (${t.channels})</h2></div>
        ${r.channels.length?`<table class="adm-table"><thead><tr><th>Channel</th><th>Members</th><th>Last message</th></tr></thead><tbody>${r.channels.map(c=>`<tr><td><b>#${esc(c.name)}</b>${c.private?` <span class="adm-pill">Private</span>`:""}<small>by ${esc(c.createdBy)}</small></td><td>${c.members}</td><td><small>${at(c.lastMessageAt)}</small></td></tr>`).join("")}</tbody></table>`
          :`<p class="adm-muted adm-pad">No channels yet.</p>`}</div>
      <div class="adm-card adm-flush"><div class="adm-card-head adm-pad"><h2>Shine activity</h2></div>
        ${r.audit.length?`<table class="adm-table"><thead><tr><th>When</th><th>Who</th><th>What</th></tr></thead><tbody>${r.audit.map(a=>`<tr><td><small>${at(a.at)}</small></td><td>${esc(a.actor)}</td><td>${esc(ACTS[a.action]||a.action.replace(/[._]/g," "))}${a.details?`<small>${esc(a.details)}</small>`:""}</td></tr>`).join("")}</tbody></table>`
          :`<p class="adm-muted adm-pad">Nothing recorded yet.</p>`}</div>
    </div>
    <p class="adm-muted">Switching someone off here stops their chat and meetings only; their mailbox keeps working. To stop both, lock the mailbox in Mailboxes.</p>`;
  $("sh-search").addEventListener("input",e=>{ const q=e.target.value.trim().toLowerCase(); $("sh-people").querySelectorAll("tbody tr[data-q]").forEach(tr=>tr.hidden=!tr.dataset.q.includes(q)); });
  $("sh-body").querySelectorAll("[data-toggle]").forEach(b=>b.addEventListener("click",()=>{ const email=b.dataset.toggle, on=b.dataset.on==="1";
    const go=async()=>{ await act({op:"shine_set_active",email,active:!on}); toast(on?"Chat switched off for "+email+".":"Chat switched on for "+email+"."); shine(main,d); };
    if(on) dialog({title:"Switch off chat for "+email+"?",body:`<p>They are signed out of Shine and can't chat or join meetings until you switch them on again. Their mailbox keeps working.</p>`,actions:[{label:"Cancel"},{label:"Switch off",danger:true,fn:go}]});
    else go().catch(e=>toast(e.message)); }));
  $("sh-body").querySelectorAll("[data-end]").forEach(b=>b.addEventListener("click",()=>dialog({title:"End “"+b.dataset.title+"”?",body:`<p>Everyone in the meeting is disconnected now.</p>`,
    actions:[{label:"Cancel"},{label:"End meeting",danger:true,fn:async()=>{ await act({op:"shine_end_meeting",meetingId:b.dataset.end}); toast("Meeting ended."); shine(main,d); }}]})));
}

/* Reports: email numbers for the last 14 days, sign-ins (failed ones flagged) and who changed what. */
const OPS={create_user:"Created mailbox",delete_user:"Deleted mailbox",password:"Reset password",status:"Changed status",quota:"Changed storage limit",forward:"Changed forwarding",
  add_alias:"Added alias",remove_alias:"Removed alias",set_name:"Renamed",set_plan:"Changed plan",role:"Changed role",set_title:"Changed title",save_roles:"Edited roles",
  company_settings:"Changed company settings",create_domain:"Added domain",delete_domain:"Removed domain",domain_status:"Changed domain status",create_list:"Created list",
  delete_list:"Deleted list",add_member:"Added list member",remove_member:"Removed list member",create_department:"Created department",set_department:"Changed department",
  policies_save:"Changed mailbox policies",policy_assign:"Changed a mailbox's policy",shine_set_active:"Switched chat on or off",shine_end_meeting:"Ended a meeting",brand_set:"Changed name or logo",login_host_set:"Set sign-in address",login_host_remove:"Removed sign-in address",plan_update:"Edited plan",settings_update:"Changed server settings"};
async function reports(main, d){
  main.innerHTML=head("Reports",d.scope?`Email and sign-in activity on ${d.scope}.`:"Email and sign-in activity across all domains.",`<button class="adm-btn ghost" id="rp-refresh">${icon("refresh")} Refresh</button>`)+`<div id="rp-body"><p class="adm-muted">Loading…</p></div>`;
  $("rp-refresh").addEventListener("click",()=>reports(main,d));
  let r; try{ r=await act({op:"reports"}); }catch(e){ if($("rp-body")) $("rp-body").innerHTML=`<p class="adm-error">${esc(e.message)}</p>`; return; }
  if(!$("rp-body")) return;
  const t=r.totals, max=Math.max(1,...r.days.map(x=>Math.max(x.sent,x.signins))), who=id=>{ const u=d.users.find(u=>u.id===id); return u?u.email:id; };
  const at=ms=>new Date(ms).toLocaleString([], {day:"numeric",month:"short",hour:"numeric",minute:"2-digit"});
  const short=iso=>new Date(iso+"T00:00:00Z").toLocaleDateString([], {day:"numeric",month:"short",timeZone:"UTC"});
  const rate=t.signins+t.failed?Math.round(t.failed/(t.signins+t.failed)*100):0;
  $("rp-body").innerHTML=`
    <div class="adm-stats">
      <div class="adm-card adm-stat"><b>${t.sent}</b><span>Emails sent (14 days)</span></div>
      <div class="adm-card adm-stat"><b>${t.active}</b><span>People active</span></div>
      <div class="adm-card adm-stat"><b>${t.signins}</b><span>Sign-ins</span></div>
      <div class="adm-card adm-stat"><b class="${t.failed?"adm-bad":""}">${t.failed}</b><span>Failed sign-ins${t.failed?` (${rate}%)`:""}</span></div>
    </div>
    <div class="adm-card"><div class="adm-card-head"><h2>Each day</h2><span class="adm-chart-key"><i class="k-sent"></i>Sent <i class="k-in"></i>Sign-ins <i class="k-bad"></i>Failed</span></div>
      <div class="adm-chart" role="img" aria-label="Emails sent, sign-ins and failed sign-ins for each of the last 14 days">${r.days.map(x=>`<div class="adm-day" title="${short(x.date)}: ${x.sent} sent, ${x.signins} sign-ins, ${x.failed} failed">
        <div class="adm-cols"><i class="k-sent" style="height:${x.sent/max*100}%"></i><i class="k-in" style="height:${x.signins/max*100}%"></i><i class="k-bad" style="height:${x.failed/max*100}%"></i></div><small>${short(x.date)}</small></div>`).join("")}</div>
      <table class="adm-table adm-sr"><caption>The same numbers as a table</caption><thead><tr><th>Day</th><th>Sent</th><th>Sign-ins</th><th>Failed</th><th>Active</th></tr></thead><tbody>${r.days.map(x=>`<tr><td>${short(x.date)}</td><td>${x.sent}</td><td>${x.signins}</td><td>${x.failed}</td><td>${x.active}</td></tr>`).join("")}</tbody></table>
      <p class="adm-muted">Counts mail sent from Dejoiy Mail on the web and in its apps. Mail received, and mail sent from other mail apps (IMAP), is not counted yet.</p></div>
    <div class="adm-two">
      <div class="adm-card"><h2>Top senders</h2>${r.topSenders.length?`<table class="adm-table"><tbody>${r.topSenders.map(x=>`<tr><td>${esc(x.email)}</td><td class="adm-right">${x.count}</td></tr>`).join("")}</tbody></table>`:`<p class="adm-muted">No mail sent in this period.</p>`}</div>
      <div class="adm-card"><h2>Most failed sign-ins</h2>${r.failedSignins.length?`<table class="adm-table"><tbody>${r.failedSignins.map(x=>`<tr><td>${esc(x.email)}${x.count>=5?` <span class="adm-pill bad">Check this</span>`:""}</td><td class="adm-right">${x.count}</td></tr>`).join("")}</tbody></table>
        <p class="adm-muted">Many wrong passwords on one mailbox can mean someone is guessing. Reset its password if the owner doesn't recognise them.</p>`:`<p class="adm-muted">No failed sign-ins. </p>`}</div>
    </div>
    <div class="adm-card adm-flush"><div class="adm-card-head adm-pad"><h2>Sign-ins</h2></div>
      ${r.signins.length?`<table class="adm-table"><thead><tr><th>When</th><th>Mailbox</th><th>Result</th><th>From (IP)</th></tr></thead><tbody>${r.signins.map(x=>`<tr><td><small>${at(x.at)}</small></td><td>${esc(x.actor)}</td>
        <td><span class="adm-pill ${x.kind==="signin"?"good":"bad"}">${x.kind==="signin"?"Signed in":"Wrong password"}</span></td><td><small>${esc(x.ip||"—")}</small></td></tr>`).join("")}</tbody></table>`:`<p class="adm-muted adm-pad">No sign-ins recorded yet. They appear here from now on.</p>`}</div>
    <div class="adm-card adm-flush"><div class="adm-card-head adm-pad"><h2>Admin activity</h2></div>
      ${r.audit.length?`<table class="adm-table"><thead><tr><th>When</th><th>Admin</th><th>What</th><th>On</th><th>From (IP)</th></tr></thead><tbody>${r.audit.map(x=>{ const op=x.kind.replace(/^admin:?/,"");
        return `<tr><td><small>${at(x.at)}</small></td><td>${esc(x.actor)}</td><td>${op==="_signin"?"Opened the admin console":op==="_signin_failed"?`<span class="adm-pill bad">Wrong admin password</span>`:esc(OPS[op]||op.replace(/_/g," "))}</td><td>${esc(who(x.target)||"—")}</td><td><small>${esc(x.ip||"—")}</small></td></tr>`; }).join("")}</tbody></table>`
        :`<p class="adm-muted adm-pad">No admin changes recorded yet. Every change made here is listed from now on.</p>`}</div>
    <p class="adm-muted">Kept for 90 days. Passwords and the contents of mail are never recorded.</p>`;
}

function users(main, d){
  const plans=d.plans||[], planName=id=>{const n=(id&&plans.find(p=>p.id===id)?.name)||"default";return n.charAt(0).toUpperCase()+n.slice(1);};
  main.innerHTML=head("Accounts",`${d.users.length} mailboxes`,`<input type="search" id="u-search" placeholder="Search name or email" aria-label="Search mailboxes"><button class="adm-btn ghost" id="u-export">Export CSV</button>${can("mailboxes.manage")?'<button class="adm-btn primary" id="u-add">+ New mailbox</button>':""}`)+`
    <div class="adm-card adm-flush"><table class="adm-table" id="u-table"><thead><tr><th>Mailbox</th><th>Status</th><th>Department</th><th>Role</th><th>Plan</th><th>Storage</th><th>Last sign-in</th><th></th></tr></thead><tbody>
    ${d.users.map((u,i)=>`<tr data-q="${esc((u.name+" "+u.email+" "+(u.department||"")+" "+(u.title||"")).toLowerCase())}"><td><b>${esc(u.name)}</b><small>${esc(u.email)}</small></td>
      <td><span class="adm-pill ${u.status==="active"?"good":"warn"}">${esc(u.status)}</span></td><td>${esc(u.department||"—")}</td><td>${esc(u.title||u.role)}${u.title?`<small>${esc(u.role)}</small>`:""}</td><td>${esc(planName(u.cosId))}</td>
      <td>${mb(u.used)}${u.limit?` <small>of ${mb(u.limit)}</small>`:""}</td><td><small>${esc(when(u.lastLogin))}</small></td>
      <td class="adm-right"><button class="adm-btn ghost sm" data-edit="${i}">Manage</button> <a class="adm-btn ghost sm" href="/admin/manage/accounts/${esc(u.id)}">Details</a></td></tr>`).join("")}
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
      <td class="adm-right">${can("domain.view")?`<a class="adm-btn ghost sm" href="/admin/manage/domains/${esc(x.domain)}">Settings</a> `:""}<button class="adm-btn ghost sm" data-dns="${esc(x.domain)}">DNS setup</button> <button class="adm-btn ghost sm" data-host="${esc(x.domain)}">Branding & sign-in</button>${d.scope?"":` <button class="adm-btn ghost sm" data-ddel="${i}" aria-label="Delete ${esc(x.domain)}">Delete</button>`}</td></tr>`).join("")}
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
    actions:[{label:"Close"},...(boxes?[{label:"Show mailboxes",primary:true,fn:()=>{navigate("manage/accounts");}}]:[])]});
  dialog({title:"Delete "+x.domain,
    body:`<p>This removes <b>${esc(x.domain)}</b> from Dejoiy Mail. It has no mailboxes, so no mail is lost. You can add it again later.</p>
      <p class="adm-muted">Also remove its MX, SPF, DKIM and DMARC records at your DNS provider.</p>
      <label>Type <b>${esc(x.domain)}</b> to confirm<input id="dd-confirm" autocomplete="off" spellcheck="false"></label><p role="alert" class="adm-error"></p>`,
    actions:[{label:"Cancel"},{label:"Delete domain",danger:true,fn:async()=>{
      if($("dd-confirm").value.trim().toLowerCase()!==x.domain.toLowerCase()) throw new Error("Type the domain name exactly to confirm.");
      await act({op:"delete_domain",id:x.id,confirm:$("dd-confirm").value.trim()}); await reload(x.domain+" deleted.");}}]});
}

/* A company's own look (name, line, colour, logo: everywhere its people open mail) and its own sign-in address. */
async function loginHost(domain){
  const root=dialog({title:"Branding & sign-in address · "+domain, wide:true, body:`<p class="adm-muted">Loading…</p>`});
  const body=root.querySelector(".adm-dialog-body");
  const draw=(out,note)=>{
    const b=out.brand||{}, suggested="mail."+domain; let logoData="", removeLogo=false;
    body.innerHTML=`${note?`<p class="${note.bad?"adm-error":"adm-muted"}" role="status">${esc(note.text)}</p>`:""}
      <h3 class="adm-h3">Your name and logo</h3>
      <p class="adm-muted">Shown to everyone with a ${esc(domain)} mailbox, wherever they open mail: the name at the top, the browser tab and your sign-in page. A small Dejoiy mark and the Dejoiy tab icon stay.</p>
      <div class="adm-form">
        <label>Name<input id="lh-name" maxlength="60" value="${esc(b.name||"")}" placeholder="Your company (shown as “Your company Mail”)"></label>
        <label>One line on the sign-in page<input id="lh-tag" maxlength="120" value="${esc(b.tagline||"")}" placeholder="Mail for the whole team"></label>
        <label>Button colour on the sign-in page<input id="lh-colour" type="color" value="${esc(b.colour||"#ff4fa3")}"></label>
        <div class="adm-logo"><span id="lh-preview">${b.logo?`<img src="${esc(b.logo)}" alt="Current logo">`:`<i>No logo</i>`}</span>
          <label class="adm-btn ghost">Choose logo<input id="lh-logo" type="file" accept="image/png,image/jpeg" hidden></label>
          ${b.logo?`<button class="adm-btn ghost" id="lh-nologo" type="button">Remove logo</button>`:""}<small class="adm-muted">PNG or JPG, square works best, up to 200 KB.</small></div>
      </div>
      <div class="adm-dialog-actions"><button class="adm-btn primary" id="lh-brand">Save name and logo</button></div>
      <h3 class="adm-h3">Your own sign-in address (optional)</h3>
      <p class="adm-muted">Let your team sign in at your own address instead of ${esc(out.target)}. Only ${esc(domain)} mailboxes can sign in there.</p>
      <div class="adm-form"><label>Your address<input id="lh-host" value="${esc(out.host||suggested)}" placeholder="${esc(suggested)}" autocapitalize="off" spellcheck="false"></label></div>
      <div class="adm-dns-row ${out.pointing?"ok":""}"><div class="adm-dns-head"><b>Step 1 · DNS</b><span class="adm-pill ${out.pointing?"good":"warn"}">${out.host?(out.pointing?"Pointing here":"Not pointing here"):"Not set up"}</span></div>
        <dl><dt>Type</dt><dd><code>CNAME</code></dd><dt>Host</dt><dd><code id="lh-label">${esc((out.host||suggested).split(".")[0])}</code></dd><dt>Value</dt><dd><code>${esc(out.target)}</code></dd></dl>
        <p class="adm-muted">Add this where ${esc(domain)}'s DNS is managed, wait a few minutes, then press Save address.</p></div>
      <div class="adm-dns-row"><div class="adm-dns-head"><b>Step 2 · Secure connection</b></div>
        <p class="adm-muted">After you save, the padlock (HTTPS certificate) is set up by itself within about 10 minutes.</p></div>
      <div class="adm-dialog-actions">${out.host?`<button class="adm-btn ghost" id="lh-remove">Remove address</button>`:""}<button class="adm-btn" id="lh-save">Save address</button></div>`;
    const fail=e=>{ const old=body.querySelector("[role=status]"); if(old) old.remove(); body.insertAdjacentHTML("afterbegin",`<p class="adm-error" role="status">${esc(e.message)}</p>`); body.scrollTop=0; };
    $("lh-host").addEventListener("input",e=>{ $("lh-label").textContent=e.target.value.trim().split(".")[0]||"mail"; });
    $("lh-logo").addEventListener("change",e=>{ const f=e.target.files[0]; if(!f) return;
      if(!/^image\/(png|jpeg)$/.test(f.type)||f.size>200*1024){ fail(new Error("Choose a PNG or JPG logo of up to 200 KB.")); e.target.value=""; return; }
      const reader=new FileReader(); reader.onload=()=>{ logoData=String(reader.result); removeLogo=false; const img=document.createElement("img"); img.src=logoData; img.alt="New logo"; $("lh-preview").replaceChildren(img); }; reader.readAsDataURL(f); });
    const nl=$("lh-nologo"); if(nl) nl.addEventListener("click",()=>{ removeLogo=true; logoData=""; $("lh-preview").innerHTML="<i>No logo</i>"; });
    $("lh-brand").addEventListener("click",async()=>{ const btn=$("lh-brand"); btn.disabled=true;
      try{ draw(await act({op:"brand_set",domain,name:$("lh-name").value,tagline:$("lh-tag").value,colour:$("lh-colour").value,...(logoData?{logo:logoData}:{}),...(removeLogo?{removeLogo:true}:{})}),{text:"Saved. Your team sees it the next time they open or refresh mail."}); }
      catch(e){ btn.disabled=false; fail(e); } });
    $("lh-save").addEventListener("click",async()=>{ const btn=$("lh-save"); btn.disabled=true;
      try{ draw(await act({op:"login_host_set",domain,host:$("lh-host").value}),{text:"Saved. Your address will be ready in about 10 minutes."}); }
      catch(e){ btn.disabled=false; fail(e); } });
    const rm=$("lh-remove"); if(rm) rm.addEventListener("click",async()=>{ try{ draw(await act({op:"login_host_remove",domain}),{text:"Removed. Your team signs in at "+out.target+" again."}); }catch(e){ fail(e); } });
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
  if(!d.lists){ main.innerHTML=head("Distribution lists")+unavailable("Distribution lists"); return; }
  main.innerHTML=head("Distribution lists","One address that delivers to many people.",`<button class="adm-btn primary" id="l-add">+ New list</button>`)+`
    <div class="adm-card adm-flush"><table class="adm-table"><thead><tr><th>List</th><th></th></tr></thead><tbody>
    ${d.lists.map((l,i)=>`<tr><td><b>${esc(l.name||l.email)}</b><small>${esc(l.email)}</small></td><td class="adm-right"><a class="adm-btn ghost sm" href="/admin/manage/lists/${esc(l.id)}">Settings</a> <button class="adm-btn ghost sm" data-members="${i}">Members</button> <button class="adm-btn ghost sm" data-ldel="${i}">Delete</button></td></tr>`).join("")||`<tr><td class="adm-muted">No mailing lists yet.</td><td></td></tr>`}
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

/* ---------------- what admin-console.js pages get ---------------- */
const helpers = { $, esc, icon, mb, when, act, api, dialog, confirmDialog, toast, head, unavailable, reload, navigate, can, state, settings };

/* ---------------- start ---------------- */
(async function start(){
  try{ const s=await api("session"); state.csrf=s.csrf; state.user=s.user; }
  catch(e){ return showSignIn(); }
  if(state.user.isAdmin!==true) return showSignIn("This mailbox is not an administrator. Sign in with an administrator mailbox.");
  try{ await load(); }catch(e){ $("adm-main").innerHTML=`<div class="adm-card adm-error">${esc(e.message)}</div>`; }
})();
})();
if("serviceWorker" in navigator && location.protocol==="https:") navigator.serviceWorker.register("/sw.js").catch(()=>{});
