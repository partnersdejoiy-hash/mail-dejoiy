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

  let attachments = draftId ? [...(Mail.get(draftId)?.attachments||[])] : mode==='forward' && window.Live?.enabled ? [...(Mail.get(srcId)?.attachments||[])] : [];
  let pendingFiles=0;
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
  el.querySelector("#c-ccbtn").addEventListener("click", async ()=>{
    const r = el.querySelector("#c-ccrow"); r.style.display = r.style.display==="none"?"flex":"none";
  });
  el.querySelectorAll("[data-fmt]").forEach(b=> b.addEventListener("click", async ()=>{
    const c = b.dataset.fmt;
    if(c==="createLink"){ const u = prompt("Link URL:", "https://"); if(u) document.execCommand("createLink", false, u); }
    else document.execCommand(c, false, null);
    $("compose-body").focus();
  }));
  el.querySelector("#c-files").addEventListener("change", async ev=>{
    const files=[...ev.target.files];ev.target.value="";
    if(!window.Live?.enabled){files.forEach(f=>attachments.push({name:f.name,size:fmtSize(f.size)}));renderAtt();return;}
    if(attachments.length+files.length>20){App.toast('Select up to 20 attachments.');return;}
    if(attachments.reduce((sum,a)=>sum+(a.bytes||Number(a.size)||0),0)+files.reduce((sum,f)=>sum+f.size,0)>15*1024*1024){App.toast('Attachments must total 15 MB or less.');return;}
    pendingFiles++;$("c-send").disabled=true;$("c-savedraft").disabled=true;
    try{
      const added=await Promise.all(files.map(file=>new Promise((resolve,reject)=>{
        const reader=new FileReader();reader.onerror=()=>reject(new Error('Could not read the attachment. Select it again.'));
        reader.onload=()=>resolve({name:file.name,size:fmtSize(file.size),bytes:file.size,type:file.type||'application/octet-stream',data:String(reader.result).split(',')[1]});reader.readAsDataURL(file);
      })));
      attachments.push(...added);renderAtt();
    }catch(error){App.toast(error.message);}finally{pendingFiles--;if(!pendingFiles){$("c-send").disabled=false;$("c-savedraft").disabled=false;}}
  });
  function renderAtt(){
    el.querySelector("#c-attachlist").innerHTML = attachments.map((a,i)=>
      `<span class="attach-chip">📎 ${esc(a.name)} <span style="color:var(--ink-3)">${esc(a.size)}</span><button data-rmatt="${i}" aria-label="Remove">×</button></span>`).join("");
    el.querySelectorAll("[data-rmatt]").forEach(x=> x.addEventListener("click", async ()=>{ attachments.splice(+x.dataset.rmatt,1); renderAtt(); }));
  }
  const collect = ()=>({ to:$("c-to").value, cc:$("c-cc").value, subject:$("c-subj").value,
    body:$("compose-body").innerHTML, attachments:[...attachments] });

  $("c-send").addEventListener("click", async ()=>{
    if(pendingFiles)return;
    const d = collect();
    if(window.Live?.enabled && draftId)d.id=draftId;
    if(!d.to.trim()){ App.toast("Add at least one recipient first."); $("c-to").focus(); return; }
    const button=$("c-send"); button.disabled=true;
    try { await Mail.send(d); }
    catch(error){ App.toast(error.message); button.disabled=false; return; }
    if(draftId && !window.Live?.enabled){ try{ await Mail.deleteForever(draftId); }catch(error){ App.toast("Message accepted, but draft cleanup failed. Refresh before retrying."); } }
    App.go("mail:sent"); App.toast(window.Live?.enabled?"Message submitted to the mail server ✓":"Message sent ✓"); App.refreshNav();
  });
  $("c-savedraft").addEventListener("click", async ()=>{
    if(pendingFiles)return;
    const button=$("c-savedraft"); button.disabled=true;
    let em;
    try{ em=await Mail.saveDraft(Object.assign(collect(), {id:draftId})); }
    catch(error){ App.toast(error.message); button.disabled=false; return; }
    button.disabled=false; draftId=em.id;
    $("c-status").textContent = "Draft saved " + new Date().toLocaleTimeString();
    App.toast("Draft saved."); App.refreshNav();
  });
  $("c-discard").addEventListener("click", async ()=>{
    App.confirm("Discard this message?", async ()=>{ if(draftId) await Mail.deleteForever(draftId); App.go("mail:inbox"); });
  });
  renderAtt();
  setTimeout(()=> $("c-to").focus(), 60);
};

function fmtSize(b){ return b>1048576 ? (b/1048576).toFixed(1)+" MB" : b>1024 ? Math.round(b/1024)+" KB" : b+" B"; }
})();
