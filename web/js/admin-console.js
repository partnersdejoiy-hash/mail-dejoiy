/* ============ Dejoiy Mail Admin — admin-console.js : the full mail-server console ============
   Pages for Monitor, Manage, Configure, Tools and Search. Each page is (main, data, h, rest):
   h = helpers from admin-app.js (act, dialog, head, esc …), rest = what follows the page's path
   (an id, like /admin/manage/accounts/<id>). Every button is a real call to the server
   (/api/admin/action, op "z_…"); nothing here is sample data. */
(function(){
"use strict";

/* ---------- settings forms: one helper for accounts, classes of service, lists, rooms, domains, global ---------- */
// [key, label, kind, hint]; kind: bool | int | mb | days | hours | minutes | text | long | choice:a,b
const FEATURES = [
  ["zimbraFeatureMailEnabled","Mail","bool"],["zimbraFeatureCalendarEnabled","Calendar","bool"],["zimbraFeatureContactsEnabled","Contacts","bool"],
  ["zimbraFeatureTasksEnabled","Tasks","bool"],["zimbraFeatureBriefcasesEnabled","Files (briefcase)","bool"],["zimbraFeatureFiltersEnabled","Mail filters","bool"],
  ["zimbraFeatureMailForwardingEnabled","Forwarding","bool"],["zimbraFeatureOutOfOfficeReplyEnabled","Out-of-office reply","bool"],
  ["zimbraFeatureIdentitiesEnabled","Extra sender identities","bool"],["zimbraFeatureSharingEnabled","Sharing","bool"],
  ["zimbraFeatureChangePasswordEnabled","Can change own password","bool"],["zimbraFeatureGalEnabled","Company directory","bool"],
  ["zimbraFeatureSavedSearchesEnabled","Saved searches","bool"],["zimbraFeatureTaggingEnabled","Tags","bool"],
  ["zimbraImapEnabled","IMAP access","bool"],["zimbraPop3Enabled","POP access","bool"],
  ["zimbraFeatureTwoFactorAuthAvailable","Two-step sign-in available","bool"],["zimbraFeatureTwoFactorAuthRequired","Two-step sign-in required","bool"]];
const PASSWORD = [
  ["zimbraPasswordMinLength","Minimum length","int","10 to 64 characters"],["zimbraPasswordMaxAge","Expires after (days)","int","0 = never"],
  ["zimbraPasswordMinAge","Can change again after (days)","int","0 = any time"],["zimbraPasswordEnforceHistory","Remember old passwords","int","0 to 24"],
  ["zimbraPasswordLockoutEnabled","Lock after wrong passwords","bool"],["zimbraPasswordLockoutMaxFailures","Wrong passwords before lock","int","3 to 100"],
  ["zimbraPasswordLockoutDuration","Lock lasts (minutes)","minutes","5 to 1440"]];
const LIMITS = [
  ["zimbraMailQuota","Mailbox storage (MB)","mb","0 = unlimited"],["zimbraContactMaxNumEntries","Most contacts","int","0 = unlimited"],
  ["zimbraAuthTokenLifetime","Stay signed in (hours)","hours","1 to 720"]];
const ACCOUNT_GROUPS = [
  ["General",[["displayName","Display name","text"],["givenName","First name","text"],["sn","Last name","text"],["title","Job title","text"],
    ["company","Company","text"],["telephoneNumber","Phone","text"],["mobile","Mobile","text"],["description","Notes","long"],
    ["zimbraHideInGal","Hide from the company directory","bool"],["zimbraPrefLocale","Language","choice:,en,en_US,en_GB,hi"]]],
  ["Features",FEATURES],
  ["Password",[["zimbraPasswordMustChange","Must change password at next sign-in","bool"],["zimbraPasswordLocked","Password can't be changed","bool"],...PASSWORD]],
  ["Limits",LIMITS],
  ["Out of office",[["zimbraPrefOutOfOfficeReplyEnabled","Send an automatic reply","bool"],["zimbraPrefOutOfOfficeReply","Reply text","long"]]]];
const COS_GROUPS = [["General",[["description","Description","long"]]],["Features",FEATURES],["Password",PASSWORD],["Limits",LIMITS]];
const LIST_FIELDS = [["displayName","Name","text"],["description","Description","long"],["zimbraMailStatus","Receives mail","choice:enabled,disabled"],
  ["zimbraHideInGal","Hide from the company directory","bool"],["zimbraDistributionListSubscriptionPolicy","People asking to join","choice:ACCEPT,APPROVAL,REJECT"],
  ["zimbraDistributionListUnsubscriptionPolicy","People asking to leave","choice:ACCEPT,APPROVAL,REJECT"],
  ["zimbraDistributionListSendShareMessageToNewMembers","Tell new members about shared folders","bool"]];
const RESOURCE_FIELDS = [["displayName","Name","text"],["description","Description","long"],["zimbraCalResLocationDisplayName","Where it is","text"],
  ["zimbraCalResCapacity","Seats","int"],["zimbraCalResContactName","Contact name","text"],["zimbraCalResContactEmail","Contact email","text"],
  ["zimbraCalResContactPhone","Contact phone","text"],["zimbraCalResAutoAcceptDecline","Accept or decline invitations by itself","bool"],
  ["zimbraCalResAutoDeclineIfBusy","Decline when already booked","bool"],["zimbraCalResAutoDeclineRecurring","Decline repeating meetings","bool"],
  ["zimbraCalResMaxNumConflictsAllowed","Clashes allowed in a repeating meeting","int"],["zimbraHideInGal","Hide from the company directory","bool"]];
const GLOBAL_GROUPS = [
  // the message and upload size limits are set in the Settings card above, in one place only
  ["Messages",[["zimbraAttachmentsBlocked","Block all attachments","bool"],["zimbraAttachmentsViewInHtmlOnly","Open attachments as web pages only","bool"],
    ["zimbraMtaBlockedExtensionWarnRecipient","Tell the recipient when an attachment is blocked","bool"]]],
  ["Delivery",[["zimbraMtaRelayHost","Send outgoing mail through (relay)","text","host:port, empty = send directly"],
    ["zimbraMtaTlsAuthOnly","Only allow sign-in over encrypted connections","bool"],["zimbraSmtpSendAddOriginatingIP","Add the sender's IP to sent mail","bool"],
    ["zimbraDefaultDomainName","Default domain","text"]]],
  ["Spam and viruses",[["zimbraSpamTagPercent","Mark as spam from score (%)","int","1 to 100"],["zimbraSpamKillPercent","Reject from score (%)","int","1 to 100"],
    ["zimbraSpamSubjectTag","Add to the subject of spam","text"],["zimbraVirusWarnAdmin","Tell the admin about viruses","bool"],
    ["zimbraVirusWarnRecipient","Tell the recipient about viruses","bool"],["zimbraVirusBlockEncryptedArchive","Block password-protected archives","bool"],
    ["zimbraVirusDefinitionsUpdateFrequency","Update virus definitions every","choice:1h,2h,4h,8h,12h,24h"]]],
  ["Access",[["zimbraImapCleartextLoginEnabled","Allow IMAP sign-in without encryption","bool"],["zimbraPop3CleartextLoginEnabled","Allow POP sign-in without encryption","bool"],
    ["zimbraGalMaxResults","Most directory results","int","1 to 10000"]]]];
const NUMBER = new Set(["int","mb","days","hours","minutes"]);

function field(h, [key,label,kind,hint], value){
  const id="f-"+key, e=h.esc;
  if(kind==="bool") return `<label class="adm-check adm-field"><input type="checkbox" id="${id}" data-key="${e(key)}" data-kind="bool" ${value?"checked":""}> ${e(label)}</label>`;
  if(kind.startsWith("choice:")) return `<label class="adm-field">${e(label)}<select id="${id}" data-key="${e(key)}" data-kind="choice">${kind.slice(7).split(",").map(o=>`<option value="${e(o)}" ${o===(value??"")?"selected":""}>${e(o||"Default")}</option>`).join("")}</select></label>`;
  if(kind==="long") return `<label class="adm-field adm-wide">${e(label)}<textarea id="${id}" data-key="${e(key)}" data-kind="text" rows="3">${e(value??"")}</textarea></label>`;
  return `<label class="adm-field">${e(label)}<input id="${id}" data-key="${e(key)}" data-kind="${NUMBER.has(kind)?"number":"text"}" ${NUMBER.has(kind)?'type="number" min="0"':""} value="${e(value??"")}">${hint?`<small>${e(hint)}</small>`:""}</label>`;
}
/* A tabbed form; Save sends only what changed: save(changes) → Promise. */
function settingsForm(h, container, groups, values, save, opts={}){
  const tabs=groups.length>1;
  container.innerHTML=`<form class="adm-card adm-settings">
    ${tabs?`<div class="adm-tabs" role="tablist">${groups.map(([g],i)=>`<button type="button" role="tab" data-tab="${i}" class="${i?"":"on"}">${h.esc(g)}</button>`).join("")}</div>`:""}
    ${groups.map(([g,fields],i)=>`<section data-panel="${i}" ${i?"hidden":""}><div class="adm-fields">${fields.map(f=>field(h,f,values[f[0]])).join("")}</div></section>`).join("")}
    <p role="alert" class="adm-error"></p>${opts.readOnly?"":`<button class="adm-btn primary">${h.esc(opts.label||"Save changes")}</button>`}</form>`;
  const form=container.querySelector("form");
  form.querySelectorAll("[data-tab]").forEach(b=>b.addEventListener("click",()=>{
    form.querySelectorAll("[data-tab]").forEach(x=>x.classList.toggle("on",x===b));
    form.querySelectorAll("[data-panel]").forEach(p=>p.hidden=p.dataset.panel!==b.dataset.tab);
  }));
  if(opts.readOnly) form.querySelectorAll("input,select,textarea").forEach(x=>x.disabled=true);
  form.addEventListener("submit",async e=>{
    e.preventDefault(); const btn=form.querySelector("button.primary"), err=form.querySelector("[role=alert]"); err.textContent="";
    const changes={};
    form.querySelectorAll("[data-key]").forEach(x=>{
      const k=x.dataset.key, kind=x.dataset.kind, before=values[k];
      const now=kind==="bool"?x.checked:kind==="number"?(x.value===""?null:Number(x.value)):x.value;
      if(now===null||now===(before??(kind==="bool"?false:kind==="number"?null:""))) return;
      changes[k]=now;
    });
    if(!Object.keys(changes).length){ err.textContent="Nothing changed."; return; }
    btn.disabled=true;
    try{ await save(changes); Object.assign(values,changes); h.toast("Saved."); }
    catch(x){ err.textContent=x.message; }
    finally{ btn.disabled=false; }
  });
}

const loading = (h, main, title, sub) => { main.innerHTML=h.head(title,sub)+`<div class="adm-card adm-muted">Loading…</div>`; };
const zstamp = s => { const m=/^(\d{4})(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)/.exec(s||""); return m?new Date(Date.UTC(+m[1],m[2]-1,+m[3],+m[4],+m[5],+m[6])).toLocaleString([],{dateStyle:"medium",timeStyle:"short"}):"—"; };
const ago = ms => { if(!ms) return "—"; const s=Math.max(0,(Date.now()-ms)/1000); return s<60?"just now":s<3600?Math.round(s/60)+" min ago":s<86400?Math.round(s/3600)+" h ago":Math.round(s/86400)+" days ago"; };
const pill = (text, good) => `<span class="adm-pill ${good?"good":"warn"}">${text}</span>`;
const empty = (h, text) => `<p class="adm-muted adm-empty">${h.esc(text)}</p>`;

/* ================= Monitor ================= */
async function servers(main, d, h){
  loading(h,main,"Server status","Every mail server and the services running on it.");
  const o=await h.act({op:"z_overview"});
  const byServer={}; o.status.forEach(s=>(byServer[s.server]=byServer[s.server]||[]).push(s));
  main.innerHTML=h.head("Server status",`Release ${o.version.release} · ${o.version.edition} edition · built ${o.version.built}`,`<button class="adm-btn ghost" id="sv-refresh">${h.icon("refresh")} Refresh</button>`)+`
    <div class="adm-stats"><div class="adm-card adm-stat"><b>${o.servers.length}</b><span>Servers</span></div>
      <div class="adm-card adm-stat"><b>${o.status.filter(s=>s.running).length}/${o.status.length}</b><span>Services running</span></div>
      <div class="adm-card adm-stat"><b>${o.mailboxes?o.mailboxes.count:"—"}</b><span>Mailboxes on disk</span></div>
      <div class="adm-card adm-stat"><b>${o.mailboxes?h.mb(o.mailboxes.bytes):"—"}</b><span>Mail stored</span></div></div>
    ${o.servers.map(s=>`<div class="adm-card"><div class="adm-card-head"><h2>${h.esc(s.name)}</h2><small class="adm-muted">${s.services.length} services enabled</small></div>
      <div class="adm-services">${(byServer[s.name]||[]).map(x=>`<div class="adm-service ${x.running?"":"down"}"><i></i><b>${h.esc(x.service)}</b><small>${x.running?"Running":"Stopped"}${x.time?" · checked "+ago(+x.time*1000):""}</small></div>`).join("")||empty(h,"No status reported yet.")}</div></div>`).join("")}`;
  h.$("sv-refresh").addEventListener("click",()=>servers(main,d,h));
}

const STAT_LABELS = {heap_used:["Memory in use","bytes"],heap_free:["Memory free","bytes"],http_threads:["Web worker threads"],imap_conn:["IMAP connections"],
  imap_ssl_conn:["Secure IMAP connections"],pop_conn:["POP connections"],pop_ssl_conn:["Secure POP connections"],soap_sessions:["Web sessions"],
  soap_count:["Web requests (last minute)"],soap_ms_avg:["Average web request (ms)"],lmtp_rcvd_msgs:["Messages received (last minute)"],
  lmtp_dlvd_msgs:["Messages delivered (last minute)"],lmtp_rcvd_bytes:["Received (last minute)","bytes"],lmtp_dlvd_bytes:["Delivered (last minute)","bytes"],
  mbox_cache:["Mailbox cache hit rate (%)"],mbox_get_count:["Mailbox look-ups"],db_conn_count:["Database connections"],imap_count:["IMAP requests"],idx_bytes_written:["Search index written","bytes"]};
async function statistics(main, d, h){
  loading(h,main,"Server statistics");
  const [s,o]=await Promise.all([h.act({op:"z_server_stats"}),h.act({op:"z_overview"})]);
  main.innerHTML=h.head("Server statistics","Live counters from the mail store.",`<button class="adm-btn ghost" id="st-refresh">${h.icon("refresh")} Refresh</button>`)+`
    <div class="adm-stats">${Object.entries(s.stats).filter(([k])=>STAT_LABELS[k]).map(([k,v])=>`<div class="adm-card adm-stat"><b>${STAT_LABELS[k][1]==="bytes"?h.mb(v):Math.round(v*100)/100}</b><span>${h.esc(STAT_LABELS[k][0])}</span></div>`).join("")}</div>
    <div class="adm-card"><div class="adm-card-head"><h2>Storage by mailbox</h2><a href="/admin/manage/accounts">All accounts →</a></div>
      <table class="adm-table"><thead><tr><th>Mailbox</th><th>Used</th><th>Limit</th></tr></thead><tbody>
      ${[...d.users].sort((a,b)=>(b.used||0)-(a.used||0)).slice(0,15).map(u=>`<tr><td><a href="/admin/manage/accounts/${h.esc(u.id)}">${h.esc(u.email)}</a></td><td>${h.mb(u.used)}</td><td>${u.limit?h.mb(u.limit):"Unlimited"}</td></tr>`).join("")}
      </tbody></table><p class="adm-muted">Total on disk: ${o.mailboxes?h.mb(o.mailboxes.bytes)+" in "+o.mailboxes.count+" mailboxes":"—"}</p></div>`;
  h.$("st-refresh").addEventListener("click",()=>statistics(main,d,h));
}

const QUEUE_HELP = {deferred:"Couldn't be delivered yet; the server keeps retrying.",incoming:"Just arrived, waiting to be processed.",
  active:"Being delivered right now.",hold:"Held by an administrator; nothing happens until released.",corrupt:"Damaged messages the server could not read."};
async function queues(main, d, h){
  loading(h,main,"Mail queues","Counting messages in every queue (this can take a few seconds)…");
  const q=await h.act({op:"z_queues"});
  main.innerHTML=h.head("Mail queues",`Server ${q.server}`,`<button class="adm-btn ghost" id="q-refresh">${h.icon("refresh")} Refresh</button>`)+`
    <div class="adm-stats adm-stats-5">${["deferred","incoming","active","hold","corrupt"].map(n=>{const x=q.queues.find(y=>y.name===n)||{count:0};
      return `<button class="adm-card adm-stat adm-queue" data-q="${n}"><b>${x.count}</b><span>${n[0].toUpperCase()+n.slice(1)}</span></button>`;}).join("")}</div>
    <div id="q-list"></div>`;
  h.$("q-refresh").addEventListener("click",()=>queues(main,d,h));
  main.querySelectorAll("[data-q]").forEach(b=>b.addEventListener("click",()=>{ main.querySelectorAll("[data-q]").forEach(x=>x.classList.toggle("on",x===b)); queueList(h,q.server,b.dataset.q,0); }));
}
async function queueList(h, server, queue, offset){
  const box=h.$("q-list"); box.innerHTML=`<div class="adm-card adm-muted">Reading the ${h.esc(queue)} queue…</div>`;
  let r; try{ r=await h.act({op:"z_queue",server,queue,offset}); }catch(e){ box.innerHTML=`<div class="adm-card adm-error">${h.esc(e.message)}</div>`; return; }
  const acts=queue==="hold"?[["release","Release"],["requeue","Retry now"]]:[["hold","Hold"],["requeue","Retry now"]];
  box.innerHTML=`<div class="adm-card adm-flush"><div class="adm-card-head adm-pad"><div><h2>${h.esc(queue[0].toUpperCase()+queue.slice(1))} · ${r.total} messages</h2><small class="adm-muted">${h.esc(QUEUE_HELP[queue]||"")}</small></div>
    <div class="adm-head-actions">${r.items.length?acts.map(([a,l])=>`<button class="adm-btn ghost sm" data-qa="${a}">${l} selected</button>`).join("")+acts.map(([a,l])=>`<button class="adm-btn ghost sm" data-qall="${a}">${l} all</button>`).join(""):""}</div></div>
    <table class="adm-table"><thead><tr><th><input type="checkbox" id="q-all" aria-label="Select all"></th><th>From</th><th>To</th><th>Size</th><th>Queued</th><th>Reason</th></tr></thead><tbody>
    ${r.items.map(i=>`<tr><td><input type="checkbox" data-id="${h.esc(i.id)}" aria-label="Select"></td><td>${h.esc(i.from||"")}</td><td>${h.esc(i.to||"")}</td><td>${h.mb(+i.size||0)}</td><td><small>${i.time?h.esc(new Date(+i.time*1000).toLocaleString()):""}</small></td><td><small>${h.esc(i.reason||"")}</small></td></tr>`).join("")||`<tr><td colspan="6">${empty(h,"This queue is empty.")}</td></tr>`}
    </tbody></table>${r.more?`<div class="adm-pad"><button class="adm-btn ghost" id="q-more">Next 100</button></div>`:""}</div>
    ${Object.keys(r.summary||{}).length?`<div class="adm-card"><h2>Most common</h2><div class="adm-fields">${Object.entries(r.summary).map(([t,rows])=>`<div><b>${h.esc(t)}</b><ul class="adm-mini">${rows.map(x=>`<li>${h.esc(x.value)} <small>${x.count}</small></li>`).join("")}</ul></div>`).join("")}</div></div>`:""}`;
  box.querySelector("#q-all")?.addEventListener("change",e=>box.querySelectorAll("[data-id]").forEach(c=>c.checked=e.target.checked));
  box.querySelector("#q-more")?.addEventListener("click",()=>queueList(h,server,queue,offset+100));
  const run=async(action,ids)=>{ await h.act({op:"z_queue_action",server,queue,action,ids}); h.toast("Done. Counts update in a moment."); queueList(h,server,queue,0); };
  box.querySelectorAll("[data-qa]").forEach(b=>b.addEventListener("click",async()=>{
    const ids=[...box.querySelectorAll("[data-id]:checked")].map(c=>c.dataset.id); if(!ids.length) return h.toast("Select messages first.");
    b.disabled=true; try{ await run(b.dataset.qa,ids); }catch(e){ h.toast(e.message); b.disabled=false; } }));
  box.querySelectorAll("[data-qall]").forEach(b=>b.addEventListener("click",()=>h.confirmDialog(b.textContent,`${b.textContent} in the ${queue} queue?`,b.textContent,async()=>run(b.dataset.qall,"all"))));
}

async function sessions(main, d, h, rest){
  const types=d.scope?[["soap","Web"],["imap","IMAP"]]:[["soap","Web"],["imap","IMAP"],["admin","Admin console"]];
  const type=new URLSearchParams(location.search).get("type")||"soap";
  loading(h,main,"Active sessions");
  const r=await h.act({op:"z_sessions",type});
  main.innerHTML=h.head("Active sessions","Who is connected right now.",`<div class="adm-seg">${types.map(([t,l])=>`<a class="adm-btn ${t===type?"primary":"ghost"} sm" href="/admin/monitor/sessions" data-type="${t}">${l}</a>`).join("")}</div>`)+`
    <div class="adm-card adm-flush"><table class="adm-table"><thead><tr><th>Account</th><th>Started</th><th>Last active</th><th></th></tr></thead><tbody>
    ${r.sessions.map(s=>{const u=d.users.find(x=>x.email.toLowerCase()===(s.name||"").toLowerCase());
      return `<tr><td>${u?`<a href="/admin/manage/accounts/${h.esc(u.id)}">${h.esc(s.name)}</a>`:h.esc(s.name)}</td><td><small>${ago(s.created)}</small></td><td><small>${ago(s.lastUsed)}</small></td>
      <td class="adm-right">${u&&h.can("mailboxes.manage")?`<button class="adm-btn ghost sm" data-out="${h.esc(u.id)}" data-name="${h.esc(s.name)}">Sign out everywhere</button>`:""}</td></tr>`;}).join("")||`<tr><td colspan="4">${empty(h,"No one is connected this way right now.")}</td></tr>`}
    </tbody></table></div>`;
  main.querySelectorAll("[data-type]").forEach(a=>a.addEventListener("click",e=>{e.preventDefault();e.stopPropagation();history.replaceState(null,"","/admin/monitor/sessions?type="+a.dataset.type);sessions(main,d,h);}));
  main.querySelectorAll("[data-out]").forEach(b=>b.addEventListener("click",()=>signOutEverywhere(h,b.dataset.out,b.dataset.name,()=>sessions(main,d,h))));
}
function signOutEverywhere(h, id, name, after){
  h.confirmDialog("Sign out everywhere",`${name} will be signed out of every browser, phone and mail app and must sign in again.`,"Sign out",async()=>{
    await h.act({op:"z_account_signout",id}); h.toast("Signed out everywhere."); after&&after(); });
}

/* ================= Manage ================= */
async function usersDetail(main, d, h, id){
  loading(h,main,"Account");
  const a=await h.act({op:"z_account",id});
  const cos=(d.plans||[]).find(p=>p.id===a.cosId)?.name||"default";
  const self=a.email.toLowerCase()===(h.state.user?.email||"").toLowerCase();
  main.innerHTML=`<p class="adm-back"><a href="/admin/manage/accounts">← Accounts</a></p>`+h.head(a.settings.displayName||a.email,a.email,
    `${pill(h.esc(a.status),a.status==="active")}${a.isAdmin?pill("Platform admin",true):a.isDomainAdmin?pill("Company admin",true):""}${a.twoFactor?pill("Two-step on",true):""}`)+`
    <div class="adm-stats"><div class="adm-card adm-stat"><b>${h.mb(a.usedBytes)}</b><span>Used${a.settings.zimbraMailQuota?" of "+a.settings.zimbraMailQuota+" MB":""}</span></div>
      <div class="adm-card adm-stat sm"><b>${zstamp(a.lastLogin)}</b><span>Last sign-in</span></div>
      <div class="adm-card adm-stat sm"><b>${zstamp(a.created)}</b><span>Created</span></div>
      <div class="adm-card adm-stat"><b>${h.esc(cos)}</b><span>Class of service</span></div></div>
    <div id="ac-form"></div>
    <div class="adm-grid2">
      <div class="adm-card"><h2>Aliases</h2>${a.aliases.length?`<ul class="adm-mini">${a.aliases.map(x=>`<li>${h.esc(x)}</li>`).join("")}</ul>`:empty(h,"No aliases.")}<small class="adm-muted">Add or remove aliases from Accounts → Manage.</small></div>
      <div class="adm-card"><h2>Member of</h2>${a.lists.length?`<ul class="adm-mini">${a.lists.map(l=>`<li><a href="/admin/manage/lists/${h.esc(l.id)}">${h.esc(l.email)}</a>${l.via?` <small>via ${h.esc(l.via)}</small>`:""}</li>`).join("")}</ul>`:empty(h,"Not in any list.")}</div>
    </div>
    <div class="adm-card"><h2>Tools</h2><div class="adm-head-actions">
      <button class="adm-btn ghost" id="ac-out" ${self?"disabled":""}>Sign out everywhere</button>
      <button class="adm-btn ghost" id="ac-reindex">Rebuild search index</button>
      <button class="adm-btn ghost" id="ac-recalc">Recount storage</button>
      <button class="adm-btn ghost" id="ac-rename" ${self?"disabled":""}>Change address</button></div>
      <p class="adm-muted" id="ac-tool-out"></p></div>`;
  settingsForm(h,h.$("ac-form"),ACCOUNT_GROUPS,a.settings,changes=>h.act({op:"z_account_update",id,settings:changes}));
  h.$("ac-out").addEventListener("click",()=>signOutEverywhere(h,id,a.email));
  h.$("ac-reindex").addEventListener("click",async e=>{ e.currentTarget.disabled=true; const out=h.$("ac-tool-out");
    try{ const r=await h.act({op:"z_reindex",id,action:"start"}); out.textContent="Search index rebuild: "+(r.status||"started")+". Check again for progress.";
      setTimeout(async()=>{ try{ const s=await h.act({op:"z_reindex",id,action:"status"}); out.textContent="Search index rebuild: "+s.status+(s.progress?` · ${s.progress.numSucceeded} done, ${s.progress.numRemaining} left`:""); }catch(_){} },4000); }
    catch(x){ out.textContent=x.message; } finally{ e.currentTarget.disabled=false; } });
  h.$("ac-recalc").addEventListener("click",async()=>{ try{ const r=await h.act({op:"z_recalc",id}); h.$("ac-tool-out").textContent="Storage recounted: "+h.mb(r.usedBytes)+"."; }catch(x){ h.$("ac-tool-out").textContent=x.message; } });
  h.$("ac-rename").addEventListener("click",()=>h.dialog({title:"Change address",body:`<p class="adm-muted">Mail, folders and settings move with it. The old address stops working unless you add it back as an alias.</p>
    <label>New address<input id="rn-email" type="email" value="${h.esc(a.email)}"></label><p role="alert" class="adm-error"></p>`,
    actions:[{label:"Cancel"},{label:"Change address",primary:true,fn:async()=>{ await h.act({op:"z_account_rename",id,email:h.$("rn-email").value}); await h.reload("Address changed."); h.navigate("manage/accounts/"+id,true); }}]}));
}

async function listsDetail(main, d, h, id){
  loading(h,main,"Distribution list");
  const l=await h.act({op:"z_list",id});
  main.innerHTML=`<p class="adm-back"><a href="/admin/manage/lists">← Distribution lists</a></p>`+h.head(l.settings.displayName||l.email,l.email,`<button class="adm-btn ghost" id="dl-rename">Change address</button>`)+`
    <div id="dl-form"></div>
    <div class="adm-grid2"><div class="adm-card"><h2>Members · ${l.members.length}</h2>${l.members.length?`<ul class="adm-mini adm-scroll">${l.members.map(m=>`<li>${h.esc(m)}</li>`).join("")}</ul>`:empty(h,"No members yet.")}<small class="adm-muted">Add or remove members from Distribution lists → Members.</small></div>
      <div class="adm-card"><h2>Owners</h2><p class="adm-muted">Owners manage this list themselves from their mailbox.</p><ul class="adm-list">${l.owners.map(o=>`<li><span>${h.esc(o)}</span><button class="adm-btn ghost sm" data-unown="${h.esc(o)}">Remove</button></li>`).join("")||'<li class="adm-muted">No owners.</li>'}</ul>
        <label>Add owner<input id="dl-owner" type="email" placeholder="person@${h.esc(l.email.split("@")[1])}"></label><button class="adm-btn" id="dl-own">Add owner</button><p role="alert" class="adm-error" id="dl-err"></p></div></div>`;
  settingsForm(h,h.$("dl-form"),[["Settings",LIST_FIELDS]],l.settings,changes=>h.act({op:"z_list_update",id,settings:changes}));
  const again=()=>listsDetail(main,d,h,id);
  h.$("dl-own").addEventListener("click",async()=>{ try{ await h.act({op:"z_list_owner",id,owner:h.$("dl-owner").value}); h.toast("Owner added."); again(); }catch(x){ h.$("dl-err").textContent=x.message; } });
  main.querySelectorAll("[data-unown]").forEach(b=>b.addEventListener("click",async()=>{ try{ await h.act({op:"z_list_owner",id,owner:b.dataset.unown,remove:true}); h.toast("Owner removed."); again(); }catch(x){ h.$("dl-err").textContent=x.message; } }));
  h.$("dl-rename").addEventListener("click",()=>h.dialog({title:"Change list address",body:`<label>New address<input id="dr-email" type="email" value="${h.esc(l.email)}"></label><p role="alert" class="adm-error"></p>`,
    actions:[{label:"Cancel"},{label:"Change address",primary:true,fn:async()=>{ await h.act({op:"z_list_rename",id,email:h.$("dr-email").value}); await h.reload("Address changed."); h.navigate("manage/lists/"+id,true); }}]}));
}

async function resources(main, d, h){
  loading(h,main,"Resources");
  const r=await h.act({op:"z_resources"});
  const domain=d.scope||d.domains[0]?.domain||"example.com";
  main.innerHTML=h.head("Resources","Meeting rooms and equipment people can book in their calendar.",h.can("mailboxes.manage")?`<button class="adm-btn primary" id="rs-add">+ New resource</button>`:"")+`
    <div class="adm-card adm-flush"><table class="adm-table"><thead><tr><th>Resource</th><th>Type</th><th>Where</th><th>Seats</th><th>Books itself</th><th>Status</th><th></th></tr></thead><tbody>
    ${r.resources.map((x,i)=>`<tr><td><b>${h.esc(x.displayName||x.email)}</b><small>${h.esc(x.email)}</small></td><td>${x.type==="Location"?"Room":"Equipment"}</td><td>${h.esc(x.zimbraCalResLocationDisplayName||"—")}</td>
      <td>${x.zimbraCalResCapacity??"—"}</td><td>${x.zimbraCalResAutoAcceptDecline?"Yes":"No"}</td><td>${pill(h.esc(x.status),x.status==="active")}</td>
      <td class="adm-right"><button class="adm-btn ghost sm" data-edit="${i}">Edit</button></td></tr>`).join("")||`<tr><td colspan="7">${empty(h,"No rooms or equipment yet.")}</td></tr>`}
    </tbody></table></div>`;
  h.$("rs-add")?.addEventListener("click",()=>h.dialog({title:"New resource",wide:true,body:`
    <label>Type<select id="nr-type"><option value="Location">Meeting room</option><option value="Equipment">Equipment</option></select></label>
    <label>Name<input id="nr-name" maxlength="200" placeholder="Board room"></label>
    <label>Address<input id="nr-email" type="email" placeholder="boardroom@${h.esc(domain)}"></label>
    <label>Where it is<input id="nr-where" maxlength="200" placeholder="2nd floor"></label>
    <label>Seats<input id="nr-cap" type="number" min="0" value="0"></label>
    <label class="adm-check"><input type="checkbox" id="nr-auto" checked> Accept or decline invitations by itself</label>
    <label class="adm-check"><input type="checkbox" id="nr-busy" checked> Decline when already booked</label><p role="alert" class="adm-error"></p>`,
    actions:[{label:"Cancel"},{label:"Create resource",primary:true,fn:async()=>{
      await h.act({op:"z_resource_create",email:h.$("nr-email").value,type:h.$("nr-type").value,settings:{displayName:h.$("nr-name").value,
        zimbraCalResLocationDisplayName:h.$("nr-where").value,zimbraCalResCapacity:Number(h.$("nr-cap").value)||0,
        zimbraCalResAutoAcceptDecline:h.$("nr-auto").checked,zimbraCalResAutoDeclineIfBusy:h.$("nr-busy").checked}});
      h.toast("Resource created."); resources(main,d,h); }}]}));
  main.querySelectorAll("[data-edit]").forEach(b=>b.addEventListener("click",()=>{
    const x=r.resources[+b.dataset.edit];
    const root=h.dialog({title:x.displayName||x.email,wide:true,body:`<label>Status<select id="rs-status">${["active","closed","maintenance"].map(s=>`<option ${s===x.status?"selected":""}>${s}</option>`).join("")}</select></label><div id="rs-form"></div>`,actions:[{label:"Close",fn:async()=>{ resources(main,d,h); }}]});
    root.querySelector("#rs-status").addEventListener("change",async e=>{ try{ await h.act({op:"z_resource_update",id:x.id,settings:{status:e.target.value}}); h.toast("Status changed."); }catch(err){ h.toast(err.message); } });
    settingsForm(h,root.querySelector("#rs-form"),[["Settings",RESOURCE_FIELDS]],{...x},changes=>h.act({op:"z_resource_update",id:x.id,settings:changes}));
  }));
}

async function domainsDetail(main, d, h, name){
  loading(h,main,"Domain");
  const x=await h.act({op:"z_domain",domain:name});
  const plans=d.plans||[];
  main.innerHTML=`<p class="adm-back"><a href="/admin/manage/domains">← Domains</a></p>`+h.head(x.domain,"Domain settings",pill(h.esc(x.status),x.status==="active"))+`
    ${x.accountsByCos?`<div class="adm-stats">${x.accountsByCos.map(c=>`<div class="adm-card adm-stat"><b>${c.count}</b><span>${h.esc(c.cos)} accounts</span></div>`).join("")}</div>`:""}
    <div id="dm-form"></div>${x.platform?`<h2 class="adm-h3">Platform limits</h2><div id="dm-platform"></div>`:""}
    ${x.virtualHosts.length?`<div class="adm-card"><h2>Web addresses</h2><ul class="adm-mini">${x.virtualHosts.map(v=>`<li>${h.esc(v)}</li>`).join("")}</ul></div>`:""}`;
  settingsForm(h,h.$("dm-form"),[["General",[["description","Description","text"],["zimbraGalMaxResults","Most directory results","int","1 to 10000"]]]],x.settings,
    changes=>h.act({op:"z_domain_update",domain:x.domain,settings:changes}),{readOnly:!h.can("roles.manage")});
  if(x.platform) settingsForm(h,h.$("dm-platform"),[["Limits",[["zimbraDomainMaxAccounts","Most mailboxes","int","0 = no limit"],["zimbraDomainAggregateQuota","Total storage (MB)","mb","0 = no limit"],
    ["zimbraPublicServiceHostname","Public mail address","text","like mail.example.com"],["zimbraDomainDefaultCOSId","Default class of service",`choice:,${plans.map(p=>p.id).join(",")}`]]]],x.platform,
    changes=>h.act({op:"z_domain_update",domain:x.domain,settings:changes}));
  const sel=main.querySelector('[data-key="zimbraDomainDefaultCOSId"]');
  if(sel) sel.querySelectorAll("option").forEach(o=>{ const p=plans.find(p=>p.id===o.value); o.textContent=p?p.name:"Server default"; });
}

/* ================= Configure ================= */
async function cos(main, d, h, rest){
  loading(h,main,"Class of service");
  const r=await h.act({op:"z_cos"});
  const chosen=r.cos.find(c=>c.id===rest);
  if(chosen){
    main.innerHTML=`<p class="adm-back"><a href="/admin/configure/cos">← Classes of service</a></p>`+h.head(chosen.name,`${d.users.filter(u=>u.cosId===chosen.id||(!u.cosId&&chosen.name==="default")).length} accounts use it`,`<button class="adm-btn ghost" id="cs-copy">Copy</button>`)+`<div id="cs-form"></div>`;
    settingsForm(h,h.$("cs-form"),COS_GROUPS,chosen.settings,changes=>h.act({op:"z_cos_update",id:chosen.id,settings:changes}));
    h.$("cs-copy").addEventListener("click",()=>newCos(h,chosen));
    return;
  }
  main.innerHTML=h.head("Class of service","Feature sets, limits and password rules that groups of accounts share.",`<button class="adm-btn primary" id="cs-add">+ New class</button>`)+`
    <div class="adm-card adm-flush"><table class="adm-table"><thead><tr><th>Class</th><th>Accounts</th><th>Storage</th><th>Min. password</th><th>Two-step</th><th></th></tr></thead><tbody>
    ${r.cos.map(c=>`<tr><td><b>${h.esc(c.name)}</b><small>${h.esc(c.settings.description||"")}</small></td><td>${d.users.filter(u=>u.cosId===c.id||(!u.cosId&&c.name==="default")).length}</td>
      <td>${c.settings.zimbraMailQuota?c.settings.zimbraMailQuota+" MB":"Unlimited"}</td><td>${c.settings.zimbraPasswordMinLength??"—"}</td><td>${c.settings.zimbraFeatureTwoFactorAuthRequired?"Required":c.settings.zimbraFeatureTwoFactorAuthAvailable?"Available":"Off"}</td>
      <td class="adm-right"><a class="adm-btn ghost sm" href="/admin/configure/cos/${h.esc(c.id)}">Edit</a></td></tr>`).join("")}
    </tbody></table></div>`;
  h.$("cs-add").addEventListener("click",()=>newCos(h));
}
function newCos(h, from){
  h.dialog({title:from?"Copy "+from.name:"New class of service",body:`<label>Name<input id="nc-name" maxlength="60" placeholder="Staff"></label><p role="alert" class="adm-error"></p>`,
    actions:[{label:"Cancel"},{label:from?"Copy":"Create",primary:true,fn:async()=>{
      const r=await h.act(from?{op:"z_cos_copy",id:from.id,name:h.$("nc-name").value}:{op:"z_cos_create",name:h.$("nc-name").value});
      await h.reload("Class of service saved."); if(r.id) h.navigate("configure/cos/"+r.id); }}]});
}

async function globalSettings(main, d, h){
  h.settings(main,d);  // blocked attachment types and the two size limits (the original Settings card)
  main.querySelector("h1").textContent="Global settings";
  const holder=document.createElement("div"); holder.innerHTML=`<h2 class="adm-h3">Mail server</h2><div class="adm-card adm-muted">Loading…</div>`; main.appendChild(holder);
  const r=await h.act({op:"z_config"});
  holder.innerHTML=`<h2 class="adm-h3">Mail server</h2><p class="adm-muted">Applies to every domain. The mail server picks changes up within a minute.</p><div id="gs-form"></div>`;
  settingsForm(h,holder.querySelector("#gs-form"),GLOBAL_GROUPS,r.settings,changes=>h.act({op:"z_config_update",settings:changes}));
}

async function rights(main, d, h){
  loading(h,main,"Admins & rights");
  const [a,r]=await Promise.all([h.act({op:"z_admins"}),h.act({op:"z_rights"})]);
  main.innerHTML=h.head("Admins & rights","Who can administer what. Company admins are set from Accounts → Manage → Access.")+`
    <div class="adm-card adm-flush"><table class="adm-table"><thead><tr><th>Administrator</th><th>Type</th><th>Status</th><th></th></tr></thead><tbody>
    ${a.admins.map(x=>`<tr><td><b>${h.esc(x.name||x.email)}</b><small>${h.esc(x.email)}</small></td><td>${x.global?"Platform admin":"Delegated admin"}</td><td>${pill(h.esc(x.status),x.status==="active")}</td>
      <td class="adm-right"><button class="adm-btn ghost sm" data-g="${h.esc(x.email)}">Rights</button></td></tr>`).join("")}
    </tbody></table></div><div id="rg-box"></div>
    <datalist id="rg-rights">${r.rights.map(x=>`<option value="${h.esc(x.name)}">${h.esc(x.description)}</option>`).join("")}</datalist>`;
  const show=async email=>{
    const box=h.$("rg-box"); box.innerHTML=`<div class="adm-card adm-muted">Loading rights…</div>`;
    let g; try{ g=await h.act({op:"z_grants",email}); }catch(e){ box.innerHTML=`<div class="adm-card adm-error">${h.esc(e.message)}</div>`; return; }
    box.innerHTML=`<div class="adm-card"><h2>${h.esc(email)}</h2>
      <table class="adm-table"><thead><tr><th>Right</th><th>On</th><th></th><th></th></tr></thead><tbody>
      ${g.grants.map((x,i)=>`<tr><td><b>${h.esc(x.right)}</b>${x.deny?" "+pill("Denied",false):""}${x.canDelegate?" <small>can pass on</small>":""}</td><td>${h.esc(x.target?.type||"")} ${h.esc(x.target?.name||"")}</td><td></td>
        <td class="adm-right"><button class="adm-btn ghost sm" data-rv="${i}">Revoke</button></td></tr>`).join("")||`<tr><td colspan="4">${empty(h,"No rights granted directly.")}</td></tr>`}</tbody></table>
      <h3 class="adm-h3">Grant a right</h3><div class="adm-fields">
        <label class="adm-field">Right<input id="rg-right" list="rg-rights" placeholder="adminConsoleDomainRights"></label>
        <label class="adm-field">Applies to<select id="rg-type"><option value="domain">Domain</option><option value="account">Account</option><option value="dl">Distribution list</option><option value="cos">Class of service</option><option value="global">Everything</option></select></label>
        <label class="adm-field">Name<input id="rg-target" placeholder="example.com"></label>
        <label class="adm-check adm-field"><input type="checkbox" id="rg-deny"> Deny instead of allow</label>
        <label class="adm-check adm-field"><input type="checkbox" id="rg-del"> Can pass it on</label></div>
      <button class="adm-btn primary" id="rg-grant">Grant</button><p role="alert" class="adm-error" id="rg-err"></p></div>`;
    h.$("rg-grant").addEventListener("click",async()=>{ try{ await h.act({op:"z_grant",grantee:email,right:h.$("rg-right").value.trim(),targetType:h.$("rg-type").value,target:h.$("rg-target").value,deny:h.$("rg-deny").checked,canDelegate:h.$("rg-del").checked}); h.toast("Right granted."); show(email); }catch(x){ h.$("rg-err").textContent=x.message; } });
    box.querySelectorAll("[data-rv]").forEach(b=>b.addEventListener("click",()=>{ const x=g.grants[+b.dataset.rv];
      h.confirmDialog("Revoke right",`Take ${x.right} away from ${email}?`,"Revoke",async()=>{ await h.act({op:"z_grant",revoke:true,grantee:email,right:x.right,targetType:x.target?.type,target:x.target?.name||"",deny:x.deny}); h.toast("Right revoked."); show(email); }); }));
  };
  main.querySelectorAll("[data-g]").forEach(b=>b.addEventListener("click",()=>show(b.dataset.g)));
}

async function zimlets(main, d, h){
  loading(h,main,"Add-ons");
  const r=await h.act({op:"z_zimlets"});
  main.innerHTML=h.head("Add-ons","Server add-ons (zimlets) and whether they are switched on.")+`
    <div class="adm-card adm-flush"><table class="adm-table"><thead><tr><th>Add-on</th><th>Kind</th><th>Status</th><th></th></tr></thead><tbody>
    ${r.zimlets.map(z=>`<tr><td><b>${h.esc(z.name)}</b>${z.description?`<small>${h.esc(z.description)}</small>`:""}</td><td>${z.extension?"Server extension":"Mail add-on"}</td><td>${pill(z.enabled?"On":"Off",z.enabled)}</td>
      <td class="adm-right"><button class="adm-btn ghost sm" data-z="${h.esc(z.name)}" data-on="${z.enabled?0:1}">${z.enabled?"Switch off":"Switch on"}</button></td></tr>`).join("")}
    </tbody></table></div>`;
  main.querySelectorAll("[data-z]").forEach(b=>b.addEventListener("click",async()=>{ b.disabled=true;
    try{ await h.act({op:"z_zimlet_status",name:b.dataset.z,enabled:b.dataset.on==="1"}); h.toast("Saved."); zimlets(main,d,h); }catch(x){ h.toast(x.message); b.disabled=false; } }));
}

async function certs(main, d, h, rest, tries=0, refresh=false){
  if(!tries) loading(h,main,"Certificates","Reading the server's certificates. This takes about ten seconds.");
  const title="Certificates", sub="The secure-connection certificates the mail server uses. They renew automatically.";
  let r;
  try{ r=await h.act({op:"z_certs",refresh}); }
  catch(e){ main.innerHTML=h.head(title,sub)+`<div class="adm-card adm-error">${h.esc(e.message||"The certificates could not be read.")} <button class="adm-btn ghost sm" id="ct-again">Try again</button></div>`;
    h.$("ct-again").addEventListener("click",()=>certs(main,d,h,rest)); return; }
  if(r.pending && !r.certs.length){
    // the server is still reading them in the background; ask again (about 2 minutes at most)
    if(tries>=5){ main.innerHTML=h.head(title,sub)+`<div class="adm-card adm-error">The mail server is taking too long to report its certificates. <button class="adm-btn ghost sm" id="ct-again">Try again</button></div>`;
      h.$("ct-again").addEventListener("click",()=>certs(main,d,h,rest)); return; }
    main.querySelector(".adm-card").textContent="Still reading the certificates…";
    setTimeout(()=>{ if(document.body.contains(main)&&location.pathname.endsWith("/certificates")) certs(main,d,h,rest,tries+1); },3000); return;
  }
  const left=s=>{ const t=Date.parse(s); return isNaN(t)?"":Math.round((t-Date.now())/864e5); };
  main.innerHTML=h.head(title,sub)+
    `<p class="adm-muted">${r.checkedAt?"Checked "+new Date(r.checkedAt).toLocaleString([],{dateStyle:"medium",timeStyle:"short"}):""}${r.pending?" · checking again…":""}
      <button class="adm-btn ghost sm" id="ct-refresh"${r.pending?" disabled":""}>Check now</button></p>`+
    (r.error?`<div class="adm-card adm-error">${h.esc(r.error)}</div>`:"")+
    (r.certs.map(c=>{const days=left(c.notAfter);return `<div class="adm-card"><div class="adm-card-head"><h2>${h.esc(c.type)}</h2>${days!==""?pill(days+" days left",days>14):""}</div>
      <dl class="adm-facts"><dt>Issued to</dt><dd>${h.esc(c.subject)}</dd><dt>Issued by</dt><dd>${h.esc(c.issuer)}</dd><dt>Valid from</dt><dd>${h.esc(c.notBefore)}</dd>
      <dt>Valid until</dt><dd>${h.esc(c.notAfter)}</dd><dt>Also covers</dt><dd>${h.esc(c.altNames||"—")}</dd></dl></div>`;}).join("")||`<div class="adm-card">${empty(h,"No certificates reported.")}</div>`);
  h.$("ct-refresh").addEventListener("click",()=>{ loading(h,main,title,"Reading the server's certificates again…"); certs(main,d,h,rest,1,true); });
}

async function webhooks(main, d, h, rest, picked){
  const title="Webhooks";
  const domains=d.scope?[d.scope]:(d.domains||[]).map(x=>x.domain);
  const domain=d.scope||picked||domains[0]||"";
  loading(h,main,title);
  let r;
  try{ r=await h.act({op:"webhooks_get",domain}); }
  catch(e){ main.innerHTML=h.head(title)+`<div class="adm-card adm-error">${h.esc(e.message)}</div>`; return; }
  const when=t=>t?new Date(t*1000).toLocaleString([],{dateStyle:"medium",timeStyle:"short"}):"";
  const last=x=>!x.last?`<span class="adm-muted">Not sent yet</span>`:`${pill(x.last.ok?"OK "+x.last.status:(x.last.status?"Error "+x.last.status:"No answer"),x.last.ok)} <small>${h.esc(when(x.last.at))}</small>`;
  const draw=(out,secret)=>{
    r=out;
    main.innerHTML=h.head(title,"Post a small signed note to your own tools (n8n, Zapier, Make or your code) when something happens. Notes never carry mail content or passwords.")+
      (d.scope?"":`<div class="adm-card"><label>Company <select id="wh-domain">${domains.map(x=>`<option${x===domain?" selected":""}>${h.esc(x)}</option>`).join("")}</select></label></div>`)+
      (secret?`<div class="adm-card"><h2>Signing secret</h2><p>Copy it now. It is shown only this once; to get a new one, remove the webhook and add it again.</p>
        <p><code id="wh-secret">${h.esc(secret)}</code> <button class="adm-btn primary sm" id="wh-copy">Copy</button></p></div>`:"")+
      `<div class="adm-card adm-flush"><table class="adm-table"><thead><tr><th>Address</th><th>Events</th><th>Status</th><th>Last result</th><th></th></tr></thead><tbody>
      ${r.webhooks.map(x=>`<tr><td><b>${h.esc(x.url)}</b><small>Added ${h.esc(when(x.created))}${x.failures?` · ${x.failures} failed in a row`:""}</small></td>
        <td>${x.events.map(e=>`<span class="adm-chip">${h.esc(e)}</span>`).join(" ")}</td><td>${pill(x.active?"On":"Off",x.active)}</td><td>${last(x)}</td>
        <td class="adm-right"><button class="adm-btn ghost sm" data-t="${h.esc(x.id)}">Send test</button>
          <button class="adm-btn ghost sm" data-a="${h.esc(x.id)}" data-on="${x.active?0:1}">${x.active?"Switch off":"Switch on"}</button>
          <button class="adm-btn ghost sm" data-r="${h.esc(x.id)}" data-u="${h.esc(x.url)}">Remove</button></td></tr>`).join("")||`<tr><td colspan="5">${empty(h,"No webhooks yet.")}</td></tr>`}
      </tbody></table></div>`+
      (r.webhooks.length<r.max?`<div class="adm-card"><h2>Add webhook</h2><form id="wh-add" class="adm-wh-form">
        <label>Address<input name="url" type="url" required placeholder="https://hooks.example.com/dejoiy" maxlength="500"></label>
        <fieldset class="adm-wh-ev"><legend>Events</legend>${Object.entries(r.events).map(([k,v])=>`<label><input type="checkbox" name="ev" value="${h.esc(k)}"><span><b>${h.esc(k)}</b> <small>${h.esc(v)}</small></span></label>`).join("")}</fieldset>
        <div><button class="adm-btn primary">Add webhook</button></div></form></div>`:`<p class="adm-muted">A company can have ${r.max} webhooks.</p>`)+
      `<p class="adm-muted">Each note is a POST with a JSON body. Check it with the header <code>X-Dejoiy-Signature: t=&lt;time&gt;,v1=&lt;signature&gt;</code>,
        where signature = HMAC-SHA256(secret, "&lt;time&gt;.&lt;body&gt;") in hex. Ignore notes older than 5 minutes. After 20 failures in a row a webhook switches itself off.</p>`;
    h.$("wh-domain")?.addEventListener("change",e=>webhooks(main,d,h,rest,e.target.value));
    h.$("wh-copy")?.addEventListener("click",async()=>{ try{ await navigator.clipboard.writeText(secret); h.toast("Copied."); }catch(_){ const c=h.$("wh-secret"); const rg=document.createRange(); rg.selectNodeContents(c); const sel=getSelection(); sel.removeAllRanges(); sel.addRange(rg); h.toast("Press Ctrl+C to copy."); } });
    const run=async(btn,body,done)=>{ btn.disabled=true; try{ const out=await h.act({...body,domain}); draw(out); done&&done(out); }catch(e){ h.toast(e.message); btn.disabled=false; } };
    main.querySelectorAll("[data-t]").forEach(b=>b.addEventListener("click",()=>run(b,{op:"webhook_test",id:b.dataset.t},o=>h.toast(o.ok?"Test sent: they answered "+o.status+".":o.status?"They answered "+o.status+".":"No answer from that address."))));
    main.querySelectorAll("[data-a]").forEach(b=>b.addEventListener("click",()=>run(b,{op:"webhook_set_active",id:b.dataset.a,active:b.dataset.on==="1"},()=>h.toast("Saved."))));
    main.querySelectorAll("[data-r]").forEach(b=>b.addEventListener("click",()=>h.confirmDialog("Remove this webhook?",`Notes stop going to ${b.dataset.u}.`,"Remove",()=>run(b,{op:"webhook_remove",id:b.dataset.r},()=>h.toast("Removed.")))));
    h.$("wh-add")?.addEventListener("submit",async e=>{ e.preventDefault(); const f=e.target, btn=f.querySelector("button");
      const events=[...f.querySelectorAll("[name=ev]:checked")].map(x=>x.value);
      btn.disabled=true;
      try{ const out=await h.act({op:"webhook_add",domain,url:f.elements.url.value.trim(),events}); draw(out,out.secret); h.toast("Webhook added."); }
      catch(x){ h.toast(x.message); btn.disabled=false; } });
  };
  draw(r);
}

async function retention(main, d, h){
  loading(h,main,"Retention");
  const r=await h.act({op:"z_retention"});
  const rows=(list,kind)=>list.map(p=>`<tr><td>${h.esc(p.name||"—")}</td><td>${kind}</td><td>${h.esc(p.lifetime||"—")}</td></tr>`).join("");
  main.innerHTML=h.head("Retention","Server-wide rules for how long mail is kept.")+`
    <div class="adm-card adm-flush"><table class="adm-table"><thead><tr><th>Policy</th><th>Kind</th><th>Lifetime</th></tr></thead><tbody>
    ${rows(r.keep,"Keep")+rows(r.purge,"Delete after")||`<tr><td colspan="3">${empty(h,"No retention policies: mail is kept until people delete it.")}</td></tr>`}</tbody></table></div>
    <p class="adm-muted">Shown for reference. Policies that delete mail are not created from this console.</p>`;
}

/* ================= Tools ================= */
function bulkImport(main, d, h){
  if(!h.can("mailboxes.manage")){ main.innerHTML=h.head("Bulk import")+h.unavailable("Bulk import"); return; }
  const domain=d.scope||d.domains[0]?.domain||"example.com";
  main.innerHTML=h.head("Bulk import","Create many mailboxes at once from a CSV file.")+`
    <div class="adm-card"><p>One mailbox per line: <code>email,display name,password</code>. A header line is skipped. Each mailbox gets its company's default policy, like one made by hand.</p>
      <textarea id="bi-text" rows="8" class="adm-mono" placeholder="priya@${h.esc(domain)},Priya Shah,Choose-a-strong-password-1"></textarea>
      <div class="adm-head-actions"><label class="adm-btn ghost">Choose CSV file<input type="file" id="bi-file" accept=".csv,text/csv" hidden></label><button class="adm-btn primary" id="bi-go">Check and create</button></div>
      <p role="alert" class="adm-error" id="bi-err"></p></div><div id="bi-out"></div>`;
  h.$("bi-file").addEventListener("change",async e=>{ const f=e.target.files[0]; if(f) h.$("bi-text").value=await f.text(); });
  h.$("bi-go").addEventListener("click",async e=>{
    const rows=h.$("bi-text").value.split(/\r?\n/).map(l=>l.trim()).filter(Boolean).map(l=>l.split(",").map(x=>x.trim().replace(/^"|"$/g,"")))
      .filter(r=>!/^e-?mail$/i.test(r[0]||""));
    if(!rows.length){ h.$("bi-err").textContent="Paste at least one line."; return; }
    if(rows.length>500){ h.$("bi-err").textContent="Up to 500 mailboxes at a time."; return; }
    const bad=rows.findIndex(r=>r.length<3||!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(r[0])||!r[1]||!r[2]);
    if(bad>=0){ h.$("bi-err").textContent=`Line ${bad+1} needs an email, a name and a password.`; return; }
    h.$("bi-err").textContent=""; e.currentTarget.disabled=true;
    const out=h.$("bi-out"); out.innerHTML=`<div class="adm-card adm-flush"><table class="adm-table"><thead><tr><th>Mailbox</th><th>Result</th></tr></thead><tbody id="bi-rows"></tbody></table></div>`;
    let ok=0;
    for(const [email,name,password] of rows){
      const tr=document.createElement("tr"); tr.innerHTML=`<td>${h.esc(email)}</td><td class="adm-muted">Creating…</td>`; h.$("bi-rows").appendChild(tr);
      try{ await h.act({op:"create_user",email,name,password,role:"User"}); tr.lastChild.innerHTML=pill("Created",true); ok++; }
      catch(x){ tr.lastChild.innerHTML=`<span class="adm-error">${h.esc(x.message)}</span>`; }
    }
    h.$("bi-text").value=""; h.toast(`${ok} of ${rows.length} mailboxes created.`); await h.reload(); h.navigate("tools/bulk-import",true);
  });
}

function mailboxTools(main, d, h){
  main.innerHTML=h.head("Mailbox tools","Fix a mailbox without signing in as the person.")+`
    <div class="adm-card adm-form"><label>Mailbox<select id="mt-user">${d.users.map(u=>`<option value="${h.esc(u.id)}">${h.esc(u.email)}</option>`).join("")}</select></label>
      <div class="adm-head-actions"><button class="adm-btn" data-t="reindex">Rebuild search index</button><button class="adm-btn" data-t="status">Index progress</button>
        <button class="adm-btn" data-t="recalc">Recount storage</button><button class="adm-btn" data-t="signout">Sign out everywhere</button><button class="adm-btn ghost" data-t="open">Open account</button></div>
      <p class="adm-muted" id="mt-out" aria-live="polite"></p></div>
    <div class="adm-card"><h2>When to use these</h2><dl class="adm-facts"><dt>Rebuild search index</dt><dd>Search in the mailbox misses mail it should find.</dd>
      <dt>Recount storage</dt><dd>The storage shown looks wrong after a big clean-up.</dd><dt>Sign out everywhere</dt><dd>A phone was lost or a password may be known to someone else.</dd></dl></div>`;
  const out=h.$("mt-out");
  main.querySelectorAll("[data-t]").forEach(b=>b.addEventListener("click",async()=>{
    const id=h.$("mt-user").value, name=h.$("mt-user").selectedOptions[0]?.textContent||"";
    if(b.dataset.t==="open") return h.navigate("manage/accounts/"+id);
    if(b.dataset.t==="signout") return signOutEverywhere(h,id,name);
    b.disabled=true; out.textContent="Working…";
    try{
      if(b.dataset.t==="recalc"){ const r=await h.act({op:"z_recalc",id}); out.textContent=`${name}: ${h.mb(r.usedBytes)} in use.`; }
      else{ const r=await h.act({op:"z_reindex",id,action:b.dataset.t==="reindex"?"start":"status"}); out.textContent=`${name}: search index ${r.status||"started"}${r.progress?` · ${r.progress.numSucceeded} done, ${r.progress.numRemaining} left`:""}.`; }
    }catch(x){ out.textContent=x.message; } finally{ b.disabled=false; }
  }));
}

function caches(main, d, h){
  const kinds=[["account","Accounts"],["cos","Classes of service"],["domain","Domains"],["config","Global settings"],["group","Groups"],["galgroup","Directory groups"],["zimlet","Add-ons"],["skin","Themes"],["locale","Languages"],["server","Servers"]];
  main.innerHTML=h.head("Server caches","Make every server re-read settings now instead of in a few minutes.")+`
    <div class="adm-card adm-form"><div class="adm-fields">${kinds.map(([k,l])=>`<label class="adm-check adm-field"><input type="checkbox" value="${k}" ${["account","cos","domain","config"].includes(k)?"checked":""}> ${l}</label>`).join("")}</div>
      <button class="adm-btn primary" id="fc-go">Refresh caches</button><p role="alert" class="adm-error" id="fc-err"></p></div>`;
  h.$("fc-go").addEventListener("click",async e=>{ const types=[...main.querySelectorAll("input:checked")].map(x=>x.value); e.currentTarget.disabled=true;
    try{ await h.act({op:"z_flush_cache",types}); h.toast("Caches refreshed."); h.$("fc-err").textContent=""; }catch(x){ h.$("fc-err").textContent=x.message; } finally{ e.currentTarget.disabled=false; } });
}

/* ================= Search ================= */
const KINDS={account:"Account",alias:"Alias",dl:"Distribution list",calresource:"Resource",domain:"Domain"};
async function search(main, d, h){
  const params=new URLSearchParams(location.search), q=params.get("q")||"", status=params.get("status")||"";
  const all=d.scope?["accounts","aliases","distributionlists","resources"]:["accounts","aliases","distributionlists","resources","domains"];
  const types=(params.get("types")||"").split(",").filter(t=>all.includes(t)); const chosen=types.length?types:["accounts","aliases","distributionlists","resources"];
  main.innerHTML=h.head("Search directory",d.scope?`Within ${d.scope}`:"Every domain")+`
    <form class="adm-card adm-search" id="sr-form"><input type="search" name="q" value="${h.esc(q)}" placeholder="Name, address or part of it" aria-label="Search">
      <div class="adm-chips">${all.map(t=>`<label class="adm-check"><input type="checkbox" name="t" value="${t}" ${chosen.includes(t)?"checked":""}> ${{accounts:"Accounts",aliases:"Aliases",distributionlists:"Lists",resources:"Resources",domains:"Domains"}[t]}</label>`).join("")}
      <select name="status" aria-label="Status"><option value="">Any status</option>${["active","locked","lockout","maintenance","closed","pending"].map(s=>`<option ${s===status?"selected":""}>${s}</option>`).join("")}</select></div>
      <button class="adm-btn primary">Search</button></form><div id="sr-out"></div>`;
  const f=h.$("sr-form");
  f.addEventListener("submit",e=>{ e.preventDefault();
    const p=new URLSearchParams(); if(f.elements.q.value.trim()) p.set("q",f.elements.q.value.trim());
    const t=[...f.querySelectorAll("[name=t]:checked")].map(x=>x.value); if(t.length) p.set("types",t.join(","));
    if(f.elements.status.value) p.set("status",f.elements.status.value);
    history.pushState(null,"","/admin/search"+(p.toString()?"?"+p:"")); search(main,d,h); });
  const box=h.$("sr-out"); box.innerHTML=`<div class="adm-card adm-muted">Searching…</div>`;
  let r; try{ r=await h.act({op:"z_search",text:q,types:chosen,status}); }catch(e){ box.innerHTML=`<div class="adm-card adm-error">${h.esc(e.message)}</div>`; return; }
  const link=x=>x.kind==="account"?`/admin/manage/accounts/${x.id}`:x.kind==="dl"?`/admin/manage/lists/${x.id}`:x.kind==="domain"?`/admin/manage/domains/${x.name}`:x.kind==="calresource"?"/admin/manage/resources":"";
  box.innerHTML=`<div class="adm-card adm-flush"><table class="adm-table"><thead><tr><th>Name</th><th>Kind</th><th>Status</th><th>Last sign-in</th></tr></thead><tbody>
    ${r.results.map(x=>`<tr><td>${link(x)?`<a href="${h.esc(link(x))}"><b>${h.esc(x.displayName||x.name)}</b></a>`:`<b>${h.esc(x.displayName||x.name)}</b>`}<small>${h.esc(x.name)}${x.target?" → "+h.esc(x.target):""}</small></td>
      <td>${KINDS[x.kind]||x.kind}${x.type?` <small>${h.esc(x.type)}</small>`:""}</td><td>${x.status?pill(h.esc(x.status),x.status==="active"):"—"}</td><td><small>${x.lastLogin?zstamp(x.lastLogin):"—"}</small></td></tr>`).join("")||`<tr><td colspan="4">${empty(h,"Nothing matches.")}</td></tr>`}
    </tbody></table></div><p class="adm-muted">${r.total} found${r.more?" · showing the first 50; narrow the search to see the rest":""}.</p>`;
}

window.AdminPages = { servers, statistics, queues, sessions, usersDetail, listsDetail, resources, domainsDetail, cos, cosDetail:cos,
  globalSettings, rights, zimlets, certs, retention, webhooks, bulkImport, mailboxTools, caches, search };
})();
