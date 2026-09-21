/* ============ Dejoiy Mail — view-compose.js : rich-text composer ============ */
(function(){
"use strict";

Views.compose = function(el, arg){
  let draft = {to:"", cc:"", subject:"", body:""}, draftId = null, mode = "new", srcId = null;
  if(arg && arg!=="new"){
    const [m, id] = arg.split(":");
    mode = m; srcId = id;
    if(m==="draft"){ const e = Mail.get(id); if(e){ draftId=id; draft={to:(e.to||[]).join(", "),cc:(e.cc||[]).join(", "),subject:e.subject,body:e.body}; } }
    else if(m==="reply"){ const d = Mail.replyDraft(id); if(d) draft=d; }
    else if(m==="replyall"){ const d = Mail.replyDraft(id, true); if(d) draft=d; }
    else if(m==="forward"){ const d = Mail.forwardDraft(id); if(d) draft=d; }
  }
  if(!draft.body && Store.state.user.signature)
    draft.body = `<br><br><div style="color:var(--ink-2)">--<br>${esc(Store.state.user.signature).replace(/\n/g,"<br>")}</div>`;

  let attachments = [];
  el.innerHTML = `
  <div class="compose">
    <div class="compose-head"><span>✎</span> ${mode==="new"?"New message":mode[0].toUpperCase()+mode.slice(1)} <span class="sp"></span>
      <button class="btn sm ghost" id="c-discard">Discard</button></div>
    <div class="c-row"><span class="c-lab">To</span><input id="c-to" type="text" value="${esc(draft.to)}" placeholder="name@example.com" autocomplete="off">
      <button class="btn sm ghost" id="c-ccbtn">Cc</button></div>
    <div class="c-row" id="c-ccrow" style="display:${draft.cc?"flex":"none"}"><span class="c-lab">Cc</span><input id="c-cc" type="text" value="${esc(draft.cc)}" placeholder="cc@example.com"></div>
    <div class="c-row"><span class="c-lab">Subject</span><input id="c-subj" type="text" value="${esc(draft.subject)}" placeholder="Subject"></div>
    <div class="fmt-bar" role="toolbar" aria-label="Formatting">
      ${[["bold","B"],["italic","I"],["underline","U"],["strikeThrough","S"],["insertUnorderedList","• List"],["insertOrderedList","1. List"],["createLink","🔗"]].map(([c,l])=>`<button class="icon-btn sm" data-fmt="${c}" title="${c}"><b>${l}</b></button>`).join("")}
      <span style="flex:1"></span>
      <label class="icon-btn sm" title="Attach files" style="cursor:pointer">📎<input type="file" id="c-files" multiple class="sr"></label>
    </div>
    <div id="compose-body" contenteditable="true" data-ph="Write your message…">${draft.body}</div>
    <div id="c-attachlist" style="padding:0 18px"></div>
    <div class="compose-foot">
      <button class="btn primary" id="c-send">Send ➤</button>
      <button class="btn" id="c-savedraft">Save draft</button>
      <span style="margin-left:auto;font-size:12px;color:var(--ink-3)" id="c-status"></span>
    </div>
  </div>`;

  const $ = id => el.querySelector("#"+id);
  el.querySelector("#c-ccbtn").addEventListener("click", ()=>{
    const r = el.querySelector("#c-ccrow"); r.style.display = r.style.display==="none"?"flex":"none";
  });
  el.querySelectorAll("[data-fmt]").forEach(b=> b.addEventListener("click", ()=>{
    const c = b.dataset.fmt;
    if(c==="createLink"){ const u = prompt("Link URL:", "https://"); if(u) document.execCommand("createLink", false, u); }
    else document.execCommand(c, false, null);
    $("compose-body").focus();
  }));
  el.querySelector("#c-files").addEventListener("change", ev=>{
    [...ev.target.files].forEach(f=> attachments.push({name:f.name, size:fmtSize(f.size)}));
    renderAtt(); ev.target.value="";
  });
  function renderAtt(){
    el.querySelector("#c-attachlist").innerHTML = attachments.map((a,i)=>
      `<span class="attach-chip">📎 ${esc(a.name)} <span style="color:var(--ink-3)">${esc(a.size)}</span><button data-rmatt="${i}" aria-label="Remove">×</button></span>`).join("");
    el.querySelectorAll("[data-rmatt]").forEach(x=> x.addEventListener("click", ()=>{ attachments.splice(+x.dataset.rmatt,1); renderAtt(); }));
  }
  const collect = ()=>({ to:$("c-to").value, cc:$("c-cc").value, subject:$("c-subj").value,
    body:$("compose-body").innerHTML, attachments:[...attachments] });

  $("c-send").addEventListener("click", ()=>{
    const d = collect();
    if(!d.to.trim()){ App.toast("Add at least one recipient first."); $("c-to").focus(); return; }
    Mail.send(d);
    if(draftId) Mail.deleteForever(draftId);
    App.go("mail:sent"); App.toast("Message sent ✓"); App.refreshNav();
  });
  $("c-savedraft").addEventListener("click", ()=>{
    const em = Mail.saveDraft(Object.assign(collect(), {id:draftId})); draftId = em.id;
    $("c-status").textContent = "Draft saved " + new Date().toLocaleTimeString();
    App.toast("Draft saved."); App.refreshNav();
  });
  $("c-discard").addEventListener("click", ()=>{
    App.confirm("Discard this message?", ()=>{ if(draftId) Mail.deleteForever(draftId); App.go("mail:inbox"); });
  });
  setTimeout(()=> $("c-to").focus(), 60);
};

function fmtSize(b){ return b>1048576 ? (b/1048576).toFixed(1)+" MB" : b>1024 ? Math.round(b/1024)+" KB" : b+" B"; }
})();
