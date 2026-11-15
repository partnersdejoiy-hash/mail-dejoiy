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
      <button class="btn sm ghost" id="c-discard">Discard</button><button class="btn sm primary c-send-top" id="c-send-top" aria-label="Send"><span class="c-send-word">Send</span>${Icons.get("sent")}</button></div>
    <div class="c-row"><span class="c-lab">To</span><div class="chip-field" data-field="to"><input id="c-to" type="email" multiple placeholder="${matchMedia("(max-width:680px)").matches?"Name or email":"Type a name, an address or @all"}" autocomplete="off" autocapitalize="off" enterkeyhint="next" aria-label="To"></div>
      <button class="btn sm ghost" id="c-ccbtn">Cc/Bcc</button></div>
    <div class="c-row" id="c-ccrow" style="display:${draft.cc?"flex":"none"}"><span class="c-lab">Cc</span><div class="chip-field" data-field="cc"><input id="c-cc" type="email" multiple placeholder="cc@example.com" autocomplete="off" aria-label="Cc"></div></div>
    <div class="c-row" id="c-bccrow" style="display:none"><span class="c-lab">Bcc</span><div class="chip-field" data-field="bcc"><input id="c-bcc" type="email" multiple placeholder="Hidden recipients" autocomplete="off" aria-label="Bcc"></div></div>
    <div class="c-often" id="c-often" hidden></div>
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
  /* "Often with": the people your Sent mail shows you usually add beside the ones already in To */
  const often = ()=>{
    const strip=el.querySelector("#c-often"); if(!strip || !chips) return;
    const have=new Set(Object.values(chips).flatMap(c=>c.list().map(a=>a.toLowerCase())));
    const picks=companions(chips.to.list(), have);
    strip.hidden=!picks.length;
    strip.innerHTML=picks.length ? `<span class="c-often-lab">Often with</span>`+picks.map(p=>`<button type="button" class="c-often-chip" data-add="${esc(p.email)}" data-kind="${p.kind}" aria-label="Add ${esc(p.email)} as ${p.kind==="to"?"To":p.kind==="cc"?"Cc":"Bcc"}">+ ${esc(NAMES.get(p.email)||p.email)}<small>${p.kind==="to"?"To":p.kind==="cc"?"Cc":"Bcc"}</small></button>`).join("") : "";
  };
  let chips=null;
  chips = {to:chipField(el.querySelector('[data-field="to"]'), draft.to, often), cc:chipField(el.querySelector('[data-field="cc"]'), draft.cc, often), bcc:chipField(el.querySelector('[data-field="bcc"]'), draft.bcc, often)};
  el.querySelector("#c-often").addEventListener("click",e=>{
    const b=e.target.closest("[data-add]"); if(!b) return;
    if(b.dataset.kind!=="to") for(const id of ["c-ccrow","c-bccrow"]) el.querySelector("#"+id).style.display="flex";
    chips[b.dataset.kind].add(b.dataset.add);
  });
  suggestions(el, ()=>{ Object.values(chips).forEach(c=>c.draw()); });
  often();
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
    /* The real limit comes from the mail server (encoded size of the whole message), not a fixed number. */
    const limit=Settings.account?.limits?.attachmentBytes||15*1024*1024;
    if(attachments.reduce((sum,a)=>sum+(a.bytes||Number(a.size)||0),0)+files.reduce((sum,f)=>sum+f.size,0)>limit){App.toast(`Attachments must total ${fmtSize(limit)} or less: that is the most the mail server can send. Share a link for bigger files.`);return;}
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
    let hold = wait;
    /* A big message (attachments) cannot be sent reliably while the tab is closing, so during Undo Send
       it is kept in Drafts first: if the page goes away, it is still there, never silently lost. */
    if(hold && window.Live?.enabled && JSON.stringify(d).length>60000){
      try{ const em=await Mail.saveDraft(Object.assign({...raw},{id:draftId})); draftId=em.id; d.id=draftId; }
      catch(_){ hold=0; }  // could not keep a copy: send straight away instead of holding it
    }
    if(!hold){
      const button=$("c-send"); button.disabled=true;
      try{ await deliver(d, archiveAfter); }
      catch(error){ if(error.draftId) draftId=error.draftId; App.toast(error.message, {label:"OK", fn:()=>{}, duration:10000}); button.disabled=false; rearm(); return; }
      App.go(archiveAfter?back:"mail:sent"); App.toast(/(^|\s)@joi\b/i.test(strip(d.body)) ? "Message sent ✓ Joi is copied in and will answer." : "Message sent ✓"); return;
    }
    /* Undo Send: the message waits a few seconds on this device before it goes to the server. */
    App.queueSend({deliver:()=>deliver(d, archiveAfter), restore:{data:raw, draftId, mode, srcId}, seconds:hold});
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
  let timer=null;
  const unload=e=>{ if(!done && typedNow() && JSON.stringify(collect())!==lastSaved){ autosave(); e.preventDefault(); e.returnValue=""; } };
  /* (Re)start the safety net: autosave, save on leaving, warn before closing. Also after a failed send. */
  const rearm=()=>{
    done=false; clearInterval(timer);
    timer=setInterval(()=>{ if(!document.getElementById("c-subj")){ clearInterval(timer); return; } autosave(); }, 15000);
    App.leaveGuard=()=>{ clearInterval(timer); if(!done) autosave(false); };
    window.removeEventListener("beforeunload", unload); window.addEventListener("beforeunload", unload);
  };
  rearm();
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
   Suggestions are our own list under the field (the browser's built-in one does not open on Android).
   value() returns the comma-separated list the server expects. */
const NAMES = new Map();   // address (lower case) -> contact name, filled by suggestions()
let PEOPLE = [];           // everyone Compose can suggest, the ones you write to most first
let SENT = new Map();      // address -> how often you wrote to it
let PAIRS = new Map();     // address in To -> Map(other address -> {n, to, cc, bcc}) from your Sent mail
const ADDRESS = /^[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+$/;
/* group mentions: @all = everyone on your domain, @allS = everyone on Dejoiy Mail (DEJOIY super admins and IT),
   @dept:sales = one department of your company, @role:manager = everyone with that designation */
const GROUP = /^@(alls?|(dept|role):[a-z0-9][a-z0-9-]{0,59})$/i;
const okAddress = a => ADDRESS.test(a) || GROUP.test(a);
const GROUP_LABEL = a => /^@alls$/i.test(a) ? "🌐 @allS · everyone, every domain" : /^@all$/i.test(a) ? "👥 @all · everyone on your domain" : "👥 "+(NAMES.get(a.toLowerCase())||a);

/* Who to offer for what is typed: a match at the start of a name or address first, then the ones you mail most. */
function matches(typed, taken, limit=6){
  const q=typed.trim().toLowerCase();
  const free=PEOPLE.filter(p=>!taken.has(p.email.toLowerCase()));
  if(!q) return free.filter(p=>SENT.get(p.email.toLowerCase())).slice(0,limit);   // nothing typed yet: the people you usually write to
  const rank=p=>{ const e=p.email.toLowerCase(), n=(p.name||"").toLowerCase();
    return e.startsWith(q) || n.startsWith(q) || n.split(/\s+/).some(w=>w.startsWith(q)) ? 0 : e.includes(q) || n.includes(q) ? 1 : 2; };
  return free.map(p=>[rank(p),p]).filter(([r])=>r<2).sort((x,y)=>x[0]-y[0]).slice(0,limit).map(([,p])=>p);   // PEOPLE is already most-mailed first; sort is stable
}

/* The people you usually add beside these To addresses: seen together at least twice, most often first. */
function companions(toList, have, limit=4){
  const score=new Map();
  for(const t of toList) for(const [other,c] of PAIRS.get(t.toLowerCase())||[]){
    if(c.n<2 || have.has(other)) continue;
    const s=score.get(other)||{email:other,n:0,to:0,cc:0,bcc:0}; s.n+=c.n; s.to+=c.to; s.cc+=c.cc; s.bcc+=c.bcc; score.set(other,s);
  }
  return [...score.values()].sort((x,y)=>y.n-x.n).slice(0,limit).map(s=>({email:s.email, kind:s.bcc>=s.cc&&s.bcc>=s.to&&s.bcc?"bcc":s.cc>=s.to&&s.cc?"cc":"to"}));
}

function chipField(box, initial, changed=()=>{}){
  const input = box.querySelector("input"), list = [];
  const menu=document.createElement("div"); menu.className="c-suggest"; menu.setAttribute("role","listbox"); menu.hidden=true;
  menu.id="sg-"+box.dataset.field; box.closest(".c-row").appendChild(menu);
  input.setAttribute("role","combobox"); input.setAttribute("aria-autocomplete","list"); input.setAttribute("aria-controls",menu.id); input.setAttribute("aria-expanded","false");
  let shown=[], active=-1;
  const close=()=>{ menu.hidden=true; shown=[]; active=-1; input.setAttribute("aria-expanded","false"); input.removeAttribute("aria-activedescendant"); };
  const mark=()=>{ menu.querySelectorAll("[role=option]").forEach((o,i)=>o.setAttribute("aria-selected",String(i===active)));
    if(active>=0){ input.setAttribute("aria-activedescendant",menu.id+"-"+active); menu.children[active]?.scrollIntoView({block:"nearest"}); } else input.removeAttribute("aria-activedescendant"); };
  const suggest=()=>{
    shown=document.activeElement===input ? matches(input.value, new Set(list.map(a=>a.toLowerCase()))) : [];
    if(!shown.length) return close();
    active=input.value.trim()?0:-1;
    menu.innerHTML=shown.map((p,i)=>`<button type="button" role="option" id="${menu.id}-${i}" class="c-suggest-item" data-i="${i}" tabindex="-1">${Profile.avatar(GROUP.test(p.email)?"":p.email, p.name||p.email, "c-suggest-av")}<span><b>${esc(p.name||p.email)}</b><small>${esc(GROUP.test(p.email)?p.email:[p.email, p.title, p.company||p.org].filter(Boolean).join(" · "))}</small></span></button>`).join("");
    menu.hidden=false; input.setAttribute("aria-expanded","true"); mark();
  };
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
    changed();
  };
  const add = text => { let changed=false; for(const part of String(text).split(/[,;\s]+/)){ const a=part.trim().replace(/^<|>$/g,""); if(a && !list.some(x=>x.toLowerCase()===a.toLowerCase())){ list.push(a); changed=true; } } if(changed) draw(); };
  const commit = ()=>{ if(input.value.trim()){ add(input.value); input.value=""; } close(); };
  const pick = i=>{ const p=shown[i]; if(!p) return; add(p.email); input.value=""; input.focus(); close(); };   // the list comes back when you type again: left open it would cover "Often with"
  input.addEventListener("keydown",e=>{
    if(!menu.hidden && (e.key==="ArrowDown" || e.key==="ArrowUp")){ e.preventDefault(); active=(active+(e.key==="ArrowDown"?1:-1)+shown.length)%shown.length; mark(); return; }
    if(!menu.hidden && e.key==="Escape"){ e.preventDefault(); e.stopPropagation(); close(); return; }
    if(!menu.hidden && active>=0 && (e.key==="Enter" || e.key==="Tab") && !okAddress(input.value.trim())){ e.preventDefault(); pick(active); return; }   // a whole typed address wins over the highlighted suggestion
    if(["Enter",",",";"].includes(e.key) || (e.key==="Tab" && input.value.trim())){ if(input.value.trim()){ e.preventDefault(); commit(); } else if(e.key==="Enter") e.preventDefault(); }
    else if(e.key===" " && input.value.includes("@")){ e.preventDefault(); if(okAddress(input.value.trim())) commit(); }   // Space finishes a whole address; a half-typed one stays as text
    else if(e.key==="Backspace" && !input.value && list.length){ list.pop(); draw(); suggest(); }
  });
  // (phone keyboards send Space as typed text, not as a key)
  input.addEventListener("input",e=>{ if(e.data===" " && okAddress(input.value.trim())) commit(); else suggest(); });
  input.addEventListener("focus",suggest);
  input.addEventListener("paste",e=>{ const t=e.clipboardData?.getData("text"); if(t && /[,;\s]/.test(t.trim())){ e.preventDefault(); add(t); } });
  input.addEventListener("blur",()=>{ if(okAddress(input.value.trim())) commit(); else close(); });   // leaving the field keeps a whole address, never half of one
  menu.addEventListener("pointerdown",e=>e.preventDefault());   // a tap on the list must not take the cursor out of the field
  menu.addEventListener("click",e=>{ const o=e.target.closest("[data-i]"); if(o) pick(+o.dataset.i); });
  box.addEventListener("click",e=>{ if(e.target===box) input.focus(); });
  add(initial||"");
  const pending = ()=> input.value.split(/[,;\s]+/).map(a=>a.trim().replace(/^<|>$/g,"")).filter(a=>a && !list.some(x=>x.toLowerCase()===a.toLowerCase()));
  return { draw, commit, add, list:()=>[...list], value:()=>[...list, ...pending()].join(", "), invalid:()=>list.filter(a=>!okAddress(a)) };
}

/* What Compose knows about your people: contacts, supervisors at other companies when your admin allows it,
   and what your Sent mail shows (who you write to most, and who you usually add beside whom). */
function suggestions(el, named){
  const me=(Store.state.user?.email||"").toLowerCase();
  const fill=extra=>{
    SENT=new Map(); PAIRS=new Map();
    const clean=list=>[...new Set((list||[]).map(a=>String(a?.email||a||"").trim().toLowerCase()).filter(k=>ADDRESS.test(k) && k!==me))];
    for(const m of Store.state.emails||[]){ if(m.folder!=="sent") continue;
      const to=clean(m.to), cc=clean(m.cc), bcc=clean(m.bcc);
      for(const k of [...to, ...cc, ...bcc]) SENT.set(k,(SENT.get(k)||0)+1);
      for(const t of to){ const row=PAIRS.get(t)||new Map(); PAIRS.set(t,row);
        for(const [kind,group] of [["to",to],["cc",cc],["bcc",bcc]]) for(const o of group){ if(o===t) continue; const c=row.get(o)||{n:0,to:0,cc:0,bcc:0}; c.n++; c[kind]++; row.set(o,c); } }
    }
    const seen=new Set(), people=[...(Store.state.contacts||[]), ...extra, ...[...SENT.keys()].map(email=>({email}))]
      .filter(p=>p.email && !seen.has(p.email.toLowerCase()) && seen.add(p.email.toLowerCase()));
    const often=p=>SENT.get(p.email.toLowerCase())||0;
    people.sort((x,y)=>often(y)-often(x) || GROUP.test(y.email)-GROUP.test(x.email));   // sort is stable: equal ones keep their order
    for(const p of people) if(p.name && p.name!==p.email && (!GROUP.test(p.email) || p.team)) NAMES.set(p.email.toLowerCase(), p.name);
    PEOPLE=people.slice(0,800);
    named();
  };
  const u=Store.state.user||{};
  const groups=[{email:"@all", name:"Everyone on your domain"}, ...(u.canManageRoles||u.isAdmin ? [{email:"@allS", name:"Everyone on Dejoiy Mail, every domain (super admins and IT)"}] : [])];
  let extra=[]; const fillAll=()=>fill([...groups, ...extra]);
  const noEveryone=()=>{ const i=groups.findIndex(g=>g.email==="@all"); if(i>=0) groups.splice(i,1); };   // the role has no "Mail the whole company
  fillAll();
  if(window.Live?.enabled){
    // contacts used to load only when the Contacts page was opened, so Compose had nobody to suggest
    Live.request("contacts").then(r=>{ Store.state.contacts=r.contacts; fillAll(); }).catch(()=>{});
    if(window.Contacts) Contacts.supervisors().then(more=>{ extra=[...extra, ...more]; fillAll(); });
    // your company's departments and designations, each as one address
    Live.request("groups").then(r=>{ if(r.everyone===false) noEveryone(); extra=[...extra, ...(r.groups||[]).map(g=>({email:g.mention, team:true, name:`${g.name} ${g.kind==="dept"?"department":"(everyone with this designation)"} · ${g.count} ${g.count===1?"person":"people"}`}))]; fillAll(); }).catch(()=>{});
  }
}

function strip(h){ return (new DOMParser().parseFromString(h||"","text/html").body.textContent||"").replace(/\s+/g," ").trim(); }
function fmtSize(b){ return b>1048576 ? (b/1048576).toFixed(1)+" MB" : b>1024 ? Math.round(b/1024)+" KB" : b+" B"; }
})();
