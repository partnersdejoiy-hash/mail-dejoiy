/* ============ Dejoiy Mail — view-compose.js : rich-text composer ============ */
(function(){
"use strict";

Views.compose = function(el, arg){
  let draft = {to:"", cc:"", bcc:"", inReplyTo:"", origId:"", replyType:"", subject:"", body:""}, draftId = null, mode = "new", srcId = null;
  const restored = arg==="restore" && App.undoneSend; if(restored){ App.undoneSend=null; }
  if(restored){ draft={...restored.data}; draftId=restored.draftId||null; mode=restored.mode||"new"; srcId=restored.srcId||null; }
  else if(arg && arg!=="new"){
    let [m, id] = arg.split(":");
    mode = m; srcId = id;
    if(m==="draft"){ const e = Mail.get(id) || Store.state.emails.find(x=>x.folder==="drafts" && Mail.threadKey(x)===String(id)); if(e){ id=e.id; draftId=id; draft={to:(e.to||[]).join(", "),cc:(e.cc||[]).join(", "),bcc:"",inReplyTo:"",subject:e.subject,body:e.body}; } }
    else if(m==="reply"){ const d = Mail.replyDraft(id); if(d) draft=d; }
    else if(m==="replyall"){ const d = Mail.replyDraft(id, true); if(d) draft=d; }
    else if(m==="forward"){ const d = Mail.forwardDraft(id); if(d) draft=d; }
  }
  /* The signature goes under a new message, and above the quoted text of a reply or forward, as Gmail does. */
  const signature = Profile.signatureHtml();
  if(signature && mode!=="draft" && !restored){
    const block = `<div class="dmail-signature">-- <br>${signature}</div>`;
    draft.body = mode==="new" ? `<br><br>${block}` : `<br><br>${block}<br>${String(draft.body||"").replace(/^(<br>)+/,"")}`;
  }

  let attachments = restored ? [...(restored.data.attachments||[])] : draftId ? [...(Mail.get(draftId)?.attachments||[])] : mode==='forward' && window.Live?.enabled ? [...(Mail.get(srcId)?.attachments||[])] : [];
  let pendingFiles=0;
  el.innerHTML = `
  <div class="compose">
    <div class="compose-head"><button class="icon-btn sm c-back" id="c-back" type="button" title="Back" aria-label="Back">${Icons.get("back")}</button><span class="c-ico">${Icons.get("compose")}</span> <span class="c-title">${mode==="new"?"New message":mode==="replyall"?"Reply all":mode[0].toUpperCase()+mode.slice(1)}</span> <span class="sp"></span>
      <button class="btn sm ghost" id="c-discard">Discard</button><button class="btn sm primary c-send-top" id="c-send-top" aria-label="Send">${Icons.get("sent")}</button></div>
    <div class="c-row"><span class="c-lab">To</span><div class="chip-field" data-field="to"><input id="c-to" type="email" multiple placeholder="Type an address or @all, press Enter" autocomplete="off" enterkeyhint="next" aria-label="To"></div>
      <button class="btn sm ghost" id="c-ccbtn">Cc/Bcc</button></div>
    <div class="c-row" id="c-ccrow" style="display:${draft.cc?"flex":"none"}"><span class="c-lab">Cc</span><div class="chip-field" data-field="cc"><input id="c-cc" type="email" multiple placeholder="cc@example.com" autocomplete="off" aria-label="Cc"></div></div>
    <div class="c-row" id="c-bccrow" style="display:none"><span class="c-lab">Bcc</span><div class="chip-field" data-field="bcc"><input id="c-bcc" type="email" multiple placeholder="Hidden recipients" autocomplete="off" aria-label="Bcc"></div></div>
    <div class="c-row"><span class="c-lab">Subject</span><input id="c-subj" type="text" value="${esc(draft.subject)}" placeholder="Subject"></div>
    <div class="c-row c-labels"><span class="c-lab">Label</span><div class="c-label-pills" id="c-labels" role="radiogroup" aria-label="Label"></div></div>
    <div class="fmt-bar" role="toolbar" aria-label="Formatting">
      ${[["bold","B"],["italic","I"],["underline","U"],["strikeThrough","S"],["insertUnorderedList","• List"],["insertOrderedList","1. List"],["createLink","🔗"]].map(([c,l])=>`<button class="icon-btn sm" data-fmt="${c}" title="${c}"><b>${l}</b></button>`).join("")}
      <span style="flex:1"></span>
      ${Settings.ui.templates?`<button class="btn sm ghost" id="c-templates" type="button">${Icons.get("note")} Templates</button>`:""}
      <label class="icon-btn sm" title="Attach files" style="cursor:pointer">${Icons.get("paperclip")}<input type="file" id="c-files" multiple class="sr"></label>
    </div>
    <div id="compose-body" contenteditable="true" data-ph="Write your message…" spellcheck="${Settings.ui.spellcheck!==false}" autocorrect="${Settings.ui.autocorrect!==false?"on":"off"}" autocapitalize="${Settings.ui.autocorrect!==false?"sentences":"off"}" style="${esc(Settings.textStyle())}">${draft.body}</div>
    <div id="c-attachlist" style="padding:0 18px"></div>
    <div class="compose-foot">
      <button class="btn primary" id="c-send">Send ${Icons.get("sent")}</button>
      ${Settings.ui.sendArchive && srcId && ["reply","replyall"].includes(mode) ? `<button class="btn" id="c-send-archive">${Icons.get("archive")} Send &amp; archive</button>` : ""}
      <button class="btn" id="c-savedraft">Save draft</button>
      <span style="margin-left:auto;font-size:12px;color:var(--ink-3)" id="c-status"></span>
    </div>
  </div>`;

  const $ = id => el.querySelector("#"+id);
  const chips = {to:chipField(el.querySelector('[data-field="to"]'), draft.to), cc:chipField(el.querySelector('[data-field="cc"]'), draft.cc), bcc:chipField(el.querySelector('[data-field="bcc"]'), draft.bcc)};
  suggestions(el, ()=>Object.values(chips).forEach(c=>c.draw()));
  el.querySelector("#c-ccbtn").addEventListener("click", async ()=>{
    const open = el.querySelector("#c-ccrow").style.display==="none";
    for(const id of ["c-ccrow","c-bccrow"]) el.querySelector("#"+id).style.display = open?"flex":"none";
    if(open) $("c-cc").focus();
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
  /* Label: pick one, or leave it on Auto and the message is labelled from what it says. */
  const PRESETS = [["Important","important"],["Urgent","danger"],["Work","work"],["Money","money"],["Personal","personal"],["Ideas","fun"]];
  const own = [...new Set((Store.state.emails||[]).flatMap(e=>e.labels||[]))].filter(l=>!PRESETS.some(([n])=>n.toLowerCase()===String(l).toLowerCase())).slice(0,12);
  let picked = restored?.data?.label || "";
  const autoLabel = ()=>{ const t=window.MailTone?.autoTone({subject:$("c-subj").value, body:$("compose-body").innerHTML})||""; return {tone:t, name:window.MailTone?.toneName(t)||""}; };
  const drawLabels = ()=>{
    const a = autoLabel(), tone = n => PRESETS.find(([x])=>x===n)?.[1] || window.MailTone?.labelTone(n) || "";
    $("c-labels").innerHTML = `<button type="button" role="radio" class="c-pill" data-label="" data-tone="${a.tone}" aria-checked="${!picked}">✨ Auto${a.name?" · "+esc(a.name):""}</button>`
      + [...PRESETS.map(([n])=>n), ...own].map(n=>`<button type="button" role="radio" class="c-pill" data-label="${esc(n)}" data-tone="${tone(n)}" aria-checked="${picked===n}">${esc(n)}</button>`).join("");
    $("c-labels").querySelectorAll("[data-label]").forEach(b=>b.addEventListener("click",()=>{ picked=b.dataset.label; drawLabels(); }));
  };
  const chosenLabel = ()=> picked || autoLabel().name;
  let labelTimer; const relabel=()=>{ if(picked) return; clearTimeout(labelTimer); labelTimer=setTimeout(drawLabels,400); };
  $("c-subj").addEventListener("input",relabel); $("compose-body").addEventListener("input",relabel);
  drawLabels();
  const collect = ()=>({ label:chosenLabel(), important:chosenLabel()==="Important", to:chips.to.value(), cc:chips.cc.value(), bcc:chips.bcc.value(), subject:$("c-subj").value,
    body:$("compose-body").innerHTML, inReplyTo:draft.inReplyTo||"", origId:draft.origId||"", replyType:draft.replyType||"", attachments:[...attachments] });

  /* The default text style (Settings → General) travels with the message, so the recipient sees it too. */
  const styled = html => /^<div data-dmail-style/.test(html) ? html : `<div data-dmail-style style="${esc(Settings.textStyle())}">${html}</div>`;
  const deliver = async (d, archiveAfter)=>{
    await Mail.send(d);
    if(draftId && !window.Live?.enabled){ try{ await Mail.deleteForever(draftId); }catch(error){ App.toast("Message accepted, but draft cleanup failed. Refresh before retrying."); } }
    if(archiveAfter){ const thread=Mail.getThread(Mail.threadId(srcId), App.ui.folder||"inbox"); const ids=thread?.folderIds?.length?thread.folderIds:[srcId]; try{ await Mail.archive(ids); }catch(_){} }
    App.refreshNav(); if(App.route==="mail" && App.ui._mail) App.ui._mail.renderList();
  };
  const send = async archiveAfter=>{
    if(pendingFiles)return;
    Object.values(chips).forEach(c=>c.commit());   // what is still being typed counts when you press Send
    const d = collect();
    if(window.Live?.enabled && draftId)d.id=draftId;
    if(!d.to.trim()){ App.toast("Add at least one recipient first."); $("c-to").focus(); return; }
    const bad = Object.values(chips).flatMap(c=>c.invalid());
    if(bad.length){ App.toast("Fix the highlighted address: "+bad[0]); return; }
    finish(); // it's being sent now: no more autosaves or leave-saves of this one
    const raw = {...d}; d.body = styled(d.body);
    const wait = Settings.ui.undoSendOn===false ? 0 : Number(Settings.ui.undoSend)||0;
    const back = archiveAfter ? "mail:"+(App.ui.folder||"inbox") : App.ui.folder ? "mail:"+App.ui.folder : "mail:inbox";
    if(!wait){
      const button=$("c-send"); button.disabled=true;
      try{ await deliver(d, archiveAfter); }catch(error){ App.toast(error.message); button.disabled=false; done=false; App.leaveGuard=()=>autosave(false); return; }
      App.go(archiveAfter?back:"mail:sent"); App.toast(/(^|\s)@joi\b/i.test(strip(d.body)) ? "Message sent ✓ Joi is copied in and will answer." : "Message sent ✓"); return;
    }
    /* Undo Send: the message waits a few seconds on this device before it goes to the server. */
    App.queueSend({deliver:()=>deliver(d, archiveAfter), restore:{data:raw, draftId, mode, srcId}, seconds:wait});
    App.go(back);
  };
  $("c-send").addEventListener("click", ()=> send(false));
  const sendArchive = $("c-send-archive"); if(sendArchive) sendArchive.addEventListener("click", ()=> send(true));
  const templates = $("c-templates");
  if(templates) templates.addEventListener("click", ev=>{
    const list = Settings.ui.templateList||[], bodyEl = $("compose-body");
    App.menu(ev.currentTarget, [
      ...list.map(t=>({label:"Insert: "+t.name, fn:()=>{ bodyEl.focus(); document.execCommand("insertHTML", false, t.body); if(t.subject && !$("c-subj").value.trim()) $("c-subj").value=t.subject; }})),
      ...(list.length?[{sep:true}]:[]),
      {label:"Save this message as a template", fn:()=> App.promptDialog("Save as template","Template name",$("c-subj").value.trim(), async name=>{
        name=String(name||"").trim(); if(!name){ App.toast("Give the template a name."); return; }
        const next=[...list.filter(t=>t.name!==name), {name, subject:$("c-subj").value.trim(), body:bodyEl.innerHTML}];
        try{ await Settings.save({ui:{templateList:next}}); App.toast("Template saved."); }catch(error){ App.toast(error.message); } })},
      {label:"Manage templates…", fn:()=> App.go("settings:advanced")}
    ]);
  });
  $("c-savedraft").addEventListener("click", async ()=>{
    if(pendingFiles)return;
    const button=$("c-savedraft"); button.disabled=true;
    let em;
    try{ em=await Mail.saveDraft(Object.assign(collect(), {id:draftId})); }
    catch(error){ App.toast(error.message); button.disabled=false; return; }
    button.disabled=false; draftId=em.id; lastSaved=JSON.stringify(collect());
    $("c-status").textContent = "Draft saved " + new Date().toLocaleTimeString();
    App.toast("Draft saved."); App.refreshNav();
  });
  $("c-discard").addEventListener("click", async ()=>{
    App.confirm("Discard this message?", async ()=>{ finish(); if(draftId) await Mail.deleteForever(draftId); App.go("mail:inbox"); });
  });
  $("c-send-top").addEventListener("click", ()=> $("c-send").click());
  /* Never lose what's written: autosave a draft every 15 s while something changed, save it when you
     go elsewhere in the app (sidebar, search, anything), and warn before the tab closes. */
  let lastSaved=JSON.stringify(collect()), saving=null, done=false;
  const typedNow=()=>{ const d=collect(); return !!(d.to.trim()||d.subject.trim()||strip($("compose-body").innerHTML)!==strip(draft.body)||attachments.length); };
  const autosave=async (quiet=true)=>{
    if(done||pendingFiles||!typedNow()) return;
    const d=collect(), snap=JSON.stringify(d);
    if(snap===lastSaved) return;
    if(saving) return saving;
    $("c-status").textContent="Saving…";
    saving=Mail.saveDraft(Object.assign(d,{id:draftId})).then(em=>{ draftId=em.id; lastSaved=snap; if($("c-status")) $("c-status").textContent="Draft saved " + new Date().toLocaleTimeString(); if(!quiet) App.toast("Saved to Drafts."); App.refreshNav(); })
      .catch(error=>{ if($("c-status")) $("c-status").textContent="Not saved: "+error.message; App.toast("Draft not saved: "+error.message); })
      .finally(()=>{ saving=null; });
    return saving;
  };
  const timer=setInterval(()=>{ if(!document.getElementById("c-subj")){ clearInterval(timer); return; } autosave(); }, 15000);
  App.leaveGuard=()=>{ clearInterval(timer); if(!done) autosave(false); };
  const unload=e=>{ if(!done && typedNow() && JSON.stringify(collect())!==lastSaved){ autosave(); e.preventDefault(); e.returnValue=""; } };
  window.addEventListener("beforeunload", unload);
  const finish=()=>{ done=true; clearInterval(timer); App.leaveGuard=null; window.removeEventListener("beforeunload", unload); };
  /* Leaving with something written keeps it as a draft, like the Gmail app's back arrow. */
  $("c-back").addEventListener("click", async ()=>{
    if(typedNow() && !pendingFiles){ await autosave(false); if(JSON.stringify(collect())!==lastSaved) return; }
    finish();
    history.length>1 ? history.back() : App.go("mail:inbox");
  });
  renderAtt();
  setTimeout(()=> (mode==="reply"||mode==="replyall" ? $("compose-body") : $("c-to")).focus(), 60);
};

/* Recipient field: a typed address becomes a removable chip on Enter, Space, comma, semicolon or Tab,
   or when a suggestion is picked; pasting a list adds them all. Text still being typed is never
   turned into a chip by itself (autosave reads it with value(), which changes nothing).
   value() returns the comma-separated list the server expects. */
const NAMES = new Map();   // address (lower case) -> contact name, filled by suggestions()
const ADDRESS = /^[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+$/;
/* group mentions: @all = everyone on your domain, @allS = everyone on Dejoiy Mail (DEJOIY super admins and IT) */
const GROUP = /^@alls?$/i;
const okAddress = a => ADDRESS.test(a) || GROUP.test(a);
const GROUP_LABEL = a => /^@alls$/i.test(a) ? "🌐 @allS · everyone, every domain" : "👥 @all · everyone on your domain";
function chipField(box, initial){
  const input = box.querySelector("input"), list = [];
  const draw = ()=>{
    box.querySelectorAll(".chip").forEach(c=>c.remove());
    list.forEach((address,i)=>{
      const chip=document.createElement("span"); chip.className="chip"+(okAddress(address)?"":" bad")+(GROUP.test(address)?" group":"");
      chip.title=GROUP.test(address)?"Everyone in this group gets the mail as Bcc":okAddress(address)?address:"This doesn't look like an email address";
      const name=NAMES.get(address.toLowerCase());
      chip.innerHTML=`<span>${esc(GROUP.test(address)?GROUP_LABEL(address):name||address)}</span><button type="button" aria-label="Remove ${esc(address)}">×</button>`;
      chip.querySelector("button").addEventListener("click",()=>{ list.splice(i,1); draw(); input.focus(); });
      box.insertBefore(chip,input);
    });
  };
  const add = text => { let changed=false; for(const part of String(text).split(/[,;\s]+/)){ const a=part.trim().replace(/^<|>$/g,""); if(a && !list.some(x=>x.toLowerCase()===a.toLowerCase())){ list.push(a); changed=true; } } if(changed) draw(); };
  const commit = ()=>{ if(input.value.trim()){ add(input.value); input.value=""; } };
  input.addEventListener("keydown",e=>{
    if(["Enter",",",";"].includes(e.key) || (e.key==="Tab" && input.value.trim())){ if(input.value.trim()){ e.preventDefault(); commit(); } else if(e.key==="Enter") e.preventDefault(); }
    else if(e.key===" " && input.value.includes("@")){ e.preventDefault(); if(okAddress(input.value.trim())) commit(); }   // Space finishes a whole address; a half-typed one stays as text
    else if(e.key==="Backspace" && !input.value && list.length){ list.pop(); draw(); }
  });
  // a picked suggestion becomes a chip straight away
  // (phone keyboards send Space as typed text, not as a key)
  input.addEventListener("input",e=>{ if((!e.inputType || e.inputType==="insertReplacementText" || e.data===" ") && okAddress(input.value.trim())) commit(); });
  input.addEventListener("paste",e=>{ const t=e.clipboardData?.getData("text"); if(t && /[,;\s]/.test(t.trim())){ e.preventDefault(); add(t); } });
  input.addEventListener("blur",()=>{ if(okAddress(input.value.trim())) commit(); });   // leaving the field keeps a whole address, never half of one
  box.addEventListener("click",e=>{ if(e.target===box) input.focus(); });
  add(initial||"");
  const pending = ()=> input.value.split(/[,;\s]+/).map(a=>a.trim().replace(/^<|>$/g,"")).filter(a=>a && !list.some(x=>x.toLowerCase()===a.toLowerCase()));
  return { draw, commit, value:()=>[...list, ...pending()].join(", "), invalid:()=>list.filter(a=>!okAddress(a)) };
}

/* Address suggestions: the people you write to most come first, then your other contacts, plus
   supervisors at other companies when your admin allows it. The names also label the chips. */
function suggestions(el, named){
  const dl=document.createElement("datalist"); dl.id="c-people";
  const me=(Store.state.user?.email||"").toLowerCase();
  const fill=extra=>{
    const sent=new Map();   // address -> how often you wrote to it, in the mail loaded so far
    for(const m of Store.state.emails||[]) if(m.folder==="sent") for(const a of [...(m.to||[]), ...(m.cc||[])]){ const k=String(a?.email||a||"").trim().toLowerCase(); if(ADDRESS.test(k) && k!==me) sent.set(k,(sent.get(k)||0)+1); }
    const seen=new Set(), people=[...(Store.state.contacts||[]), ...extra, ...[...sent.keys()].map(email=>({email}))]
      .filter(p=>p.email && !seen.has(p.email.toLowerCase()) && seen.add(p.email.toLowerCase()));
    const often=p=>sent.get(p.email.toLowerCase())||0;
    people.sort((x,y)=>GROUP.test(y.email)-GROUP.test(x.email) || often(y)-often(x));   // sort is stable: equal ones keep their order
    for(const p of people) if(p.name && p.name!==p.email && !GROUP.test(p.email)) NAMES.set(p.email.toLowerCase(), p.name);
    dl.innerHTML=people.slice(0,800).map(p=>`<option value="${esc(p.email)}">${esc([p.name, p.title, p.company||p.org].filter(Boolean).join(" · "))}</option>`).join("");
    named();
  };
  const u=Store.state.user||{};
  const groups=[{email:"@all", name:"Everyone on your domain"}, ...(u.canManageRoles||u.isAdmin ? [{email:"@allS", name:"Everyone on Dejoiy Mail, every domain (super admins and IT)"}] : [])];
  let extra=[]; const fillAll=()=>fill([...groups, ...extra]);
  fillAll(); el.appendChild(dl);
  if(window.Live?.enabled){
    // contacts used to load only when the Contacts page was opened, so Compose had nobody to suggest
    Live.request("contacts").then(r=>{ Store.state.contacts=r.contacts; fillAll(); }).catch(()=>{});
    if(window.Contacts) Contacts.supervisors().then(more=>{ extra=more; fillAll(); });
  }
  el.querySelectorAll(".chip-field input").forEach(i=>i.setAttribute("list","c-people"));
}

function strip(h){ return (new DOMParser().parseFromString(h||"","text/html").body.textContent||"").replace(/\s+/g," ").trim(); }
function fmtSize(b){ return b>1048576 ? (b/1048576).toFixed(1)+" MB" : b>1024 ? Math.round(b/1024)+" KB" : b+" B"; }
})();
