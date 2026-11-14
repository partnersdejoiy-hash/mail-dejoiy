/* ============ Dejoiy Mail — view-tickets.js : Help desk ============
   The company's own internal tickets. Anyone raises one for a department (IT, HR, payroll…);
   that department sees it in its queue, takes it, answers, and closes it.
   The server decides who may see and change what; this page only shows what it is given. */
(function(){
"use strict";

const PRIORITY = {low:"Low", normal:"Normal", high:"High", urgent:"Urgent"};
const STATUS = {open:"Open", in_progress:"In progress", waiting:"Waiting for requester", resolved:"Resolved", closed:"Closed"};
const when = ts => new Date(ts*1000).toLocaleString([], {day:"numeric", month:"short", hour:"2-digit", minute:"2-digit"});
const who = email => (email||"").split("@")[0];
let meta = null, view = "mine";

const pill = (kind, value, text) => `<span class="tk-pill tk-${kind}-${esc(value)}">${esc(text)}</span>`;

Views.desk = async function(el, number){   // number: a ticket's code, T-0007 or P-0007
  if(!window.Live?.enabled){ el.innerHTML = `<div class="view-head"><h1>Help desk</h1></div><div class="empty-note">The help desk works on your company's mail server. This demo has no server.</div>`; return; }
  el.innerHTML = `<div class="tk"><div class="view-head"><h1>Help desk</h1></div><div class="empty-note">Loading…</div></div>`;
  try{
    if(!meta) meta = await Live.request("tickets/meta");
    if(number) await ticket(el, number); else await list(el);
  }catch(error){ el.innerHTML = `<div class="tk"><div class="view-head"><h1>Help desk</h1></div><div class="empty-note" role="alert">${esc(error.message)}</div></div>`; }
};

async function list(el){
  if((view==="team" && !meta.department && !meta.manage) || (view==="all" && !meta.manage) || (view==="platform" && !meta.platform)) view="mine";
  const data = await Live.request("tickets?view="+view);
  if(App.route!=="desk") return;
  const queue = meta.department ? meta.department+" queue" : "Company admin queue";
  const tabs = [["mine","My tickets"], ...(meta.department||meta.manage?[["team", queue+(meta.waiting?` · ${meta.waiting}`:"")]]:[]), ...(meta.manage?[["all","All company tickets"]]:[]),
    ...(meta.platform?[["platform","From companies to Dejoiy"+(meta.waitingPlatform?` · ${meta.waitingPlatform}`:"")]]:[])];
  const empty = view==="mine" ? "You have not raised a ticket yet. Need something from IT, HR, your admin or another team? Raise one." : view==="team" ? "Nothing in your queue."
    : view==="platform" ? "No company admin has raised a ticket to Dejoiy." : "No tickets in your company yet.";
  el.innerHTML = `<div class="tk">
    <div class="view-head"><div><h1>Help desk</h1><p class="sub">Ask any team in your company for help, and follow it until it is done.</p></div>
      <span class="spacer"></span><button class="btn" id="tk-bug">Report a bug</button><button class="btn primary" id="tk-new">${Icons.get("compose")} New ticket</button></div>
    <div class="seg tk-tabs" role="tablist">${tabs.map(([id,label])=>`<button role="tab" aria-selected="${id===view}" class="${id===view?"on":""}" data-view="${id}">${esc(label)}</button>`).join("")}</div>
    ${data.tickets.length ? `<div class="tk-list" role="list">${data.tickets.map(t=>`<button class="tk-row ${t.late?"late":""}" role="listitem" data-open="${esc(t.code)}">
        <span class="tk-code">${esc(t.code)}</span>
        <span class="tk-main"><b>${esc(t.subject)}</b><small>${esc(t.platform&&view==="platform"?t.domain:t.team)} · ${view==="mine" ? (t.assignee?"with "+esc(who(t.assignee)):"not picked up yet") : "from "+esc(who(t.requester))+(t.assignee?" · with "+esc(who(t.assignee)):" · unassigned")}</small></span>
        ${pill("pri", t.priority, PRIORITY[t.priority])}${pill("st", t.status, t.statusName)}
        <span class="tk-when">${t.late?`<b>Overdue</b>`:esc(when(t.updated))}</span></button>`).join("")}</div>`
      : `<div class="empty-note">${esc(empty)}</div>`}
  </div>`;
  el.querySelectorAll("[data-view]").forEach(b=>b.addEventListener("click",()=>{ view=b.dataset.view; list(el).catch(e=>App.toast(e.message)); }));
  el.querySelectorAll("[data-open]").forEach(b=>b.addEventListener("click",()=>App.go("desk:"+b.dataset.open)));
  el.querySelector("#tk-new").addEventListener("click",()=>create());
  el.querySelector("#tk-bug").addEventListener("click",()=>Views.deskReport());
}

/* "Report a bug" (account menu): a ticket to the people who can fix it. Employees reach their company's admins;
   a company admin reaches the Dejoiy team. */
Views.deskReport = async function(){
  try{ if(!meta) meta = await Live.request("tickets/meta"); }catch(error){ App.toast(error.message); return; }
  create({team: meta.raiseTo.includes("Dejoiy platform") ? "Dejoiy platform" : "Company admin", subject:"Bug: ",
    hint:"What did you do, what did you expect, and what happened instead? Add the page you were on and your phone or browser."});
};

function create(preset={}){
  const send = ()=>{
    const get=id=>document.getElementById(id).value, note=document.getElementById("tn-note"), button=document.querySelector(".dlg-foot .primary");
    if(!get("tn-subject").trim() || !get("tn-body").trim()){ note.textContent="Write a short title and what you need."; return false; }
    if(button.disabled) return false; button.disabled=true; note.textContent="";
    Live.request("tickets",{op:"create",subject:get("tn-subject"),body:get("tn-body"),team:get("tn-team"),priority:get("tn-priority")})
      .then(out=>{ App.closeDialog(); meta=null; App.toast(out.ticket.code+" sent to "+out.ticket.team+"."); App.go("desk:"+out.ticket.code); })
      .catch(error=>{ button.disabled=false; note.textContent=error.message; });
    return false;
  };
  App.dialog({title:"New ticket", wide:true, body:`
    <div class="field"><label for="tn-subject">What do you need? (short title)</label><input type="text" id="tn-subject" maxlength="160" placeholder="Laptop will not start" value="${esc(preset.subject||"")}"></div>
    <div class="grid c2"><div class="field"><label for="tn-team">Which team should handle it?</label><select id="tn-team">${meta.raiseTo.map(t=>`<option value="${esc(t)}" ${t===preset.team?"selected":""}>${esc(t==="Company admin"?"Company admin (your company's mail admins)":t==="Dejoiy platform"?"Dejoiy platform (the Dejoiy team)":t)}</option>`).join("")}</select></div>
      <div class="field"><label for="tn-priority">How urgent is it?</label><select id="tn-priority">${Object.entries(PRIORITY).map(([id,label])=>`<option value="${id}" ${id==="normal"?"selected":""}>${label} · answer within ${meta.priorities?.[id]||""} hours</option>`).join("")}</select></div></div>
    <div class="field"><label for="tn-body">Details</label><textarea id="tn-body" rows="6" maxlength="8000" placeholder="${esc(preset.hint||"What happened, since when, and what you already tried.")}"></textarea></div>
    <p id="tn-note" role="alert" class="field-error"></p>`,
    actions:[{label:"Cancel"},{label:"Send ticket", primary:true, fn:send}]});
}

async function ticket(el, number){
  const t = await Live.request("tickets/"+encodeURIComponent(number));
  const assignees = t.platform ? [["","Nobody"],[Store.state.user.email,"Me"],...(t.assignee&&t.assignee!==Store.state.user.email?[[t.assignee,t.assignee]]:[])] : [["","Nobody"],...meta.people.map(p=>[p,p])];
  if(App.route!=="desk") return;
  const done = t.status==="resolved" || t.status==="closed", handle = t.canHandle;
  const select = (id, label, options, value) => `<label class="tk-set">${label}<select id="${id}">${options.map(([v,text])=>`<option value="${esc(v)}" ${v===value?"selected":""}>${esc(text)}</option>`).join("")}</select></label>`;
  el.innerHTML = `<div class="tk tk-one">
    <div class="tk-top"><button class="btn" id="tk-back">${Icons.get("back")} All tickets</button></div>
    <header class="tk-head"><p class="tk-code">${esc(t.code)}</p><h1>${esc(t.subject)}</h1>
      <p class="tk-meta">${pill("st", t.status, t.statusName)}${pill("pri", t.priority, PRIORITY[t.priority])}${t.late?`<span class="tk-pill tk-late">Overdue</span>`:""}
        <span>${esc(t.team)}${t.platform?" · "+esc(t.domain):""}</span><span>raised by ${esc(t.requester)} · ${esc(when(t.created))}</span><span>${t.assignee?"with "+esc(t.assignee):"not picked up yet"}</span>${done?"":`<span>due ${esc(when(t.due))}</span>`}</p></header>
    ${handle ? `<div class="tk-actions">
        ${select("tk-status","Status",Object.entries(STATUS),t.status)}
        ${select("tk-assign","Assigned to",assignees,t.assignee)}
        ${select("tk-priority","Priority",Object.entries(PRIORITY),t.priority)}
        ${t.platform?"":select("tk-team","Team",meta.teams.map(n=>[n,n]),t.team)}</div>`
      : t.mine ? `<div class="tk-actions">${done?`<button class="btn" data-status="open">Reopen: this is not solved</button>`:`<button class="btn" data-status="closed">Close: I no longer need this</button>`}</div>` : ""}
    <ol class="tk-thread">
      <li class="tk-note-item"><p class="tk-by"><b>${esc(t.requester)}</b> · ${esc(when(t.created))}</p><div class="tk-text">${esc(t.body)}</div></li>
      ${t.notes.map(n=> n.kind==="change" ? `<li class="tk-change">${esc(who(n.author))} · ${esc(n.text)} · ${esc(when(n.at))}</li>`
        : `<li class="tk-note-item ${n.internal?"internal":""}"><p class="tk-by"><b>${esc(n.author)}</b> · ${esc(when(n.at))}${n.internal?` · <span class="tk-pill tk-internal">Team only</span>`:""}</p><div class="tk-text">${esc(n.text)}</div></li>`).join("")}
    </ol>
    <form class="tk-reply" id="tk-reply"><label for="tk-text">${handle&&!t.mine?"Answer "+esc(who(t.requester)):"Add a message"}</label>
      <textarea id="tk-text" rows="4" maxlength="8000" required></textarea>
      <div class="tk-reply-foot">${handle?`<label class="tk-check"><input type="checkbox" id="tk-internal"> Team only (the person who raised it does not see this)</label>`:"<span></span>"}<button class="btn primary">Send</button></div></form>
  </div>`;
  const act = async payload => { try{ const out = await Live.request("tickets",{code:t.code,...payload}); meta=null;
      if(out.ticket) await Views.desk(el, t.code); else { App.toast("Moved to another team."); App.go("desk"); } }catch(error){ App.toast(error.message); Views.desk(el, t.code); } };
  el.querySelector("#tk-back").addEventListener("click",()=>App.go("desk"));
  el.querySelectorAll("[data-status]").forEach(b=>b.addEventListener("click",()=>act({op:"status",status:b.dataset.status})));
  if(handle){
    el.querySelector("#tk-status").addEventListener("change",e=>act({op:"status",status:e.target.value}));
    el.querySelector("#tk-assign").addEventListener("change",e=>act({op:"assign",assignee:e.target.value}));
    el.querySelector("#tk-priority").addEventListener("change",e=>act({op:"priority",priority:e.target.value}));
    el.querySelector("#tk-team")?.addEventListener("change",e=>act({op:"team",team:e.target.value}));
  }
  el.querySelector("#tk-reply").addEventListener("submit",e=>{ e.preventDefault(); const text=el.querySelector("#tk-text").value.trim(); if(!text) return;
    e.target.querySelector("button").disabled=true; act({op:"comment",text,internal:!!el.querySelector("#tk-internal")?.checked}); });
}
})();
