/* ============ Dejoiy Mail — view-account-settings.js : Settings, mobile first ============
   Phones get a list of sections that each open full screen with a back arrow, like a phone
   mail app; wider screens get a row of tabs. Every option is saved to the mailbox (see
   settings.js), so it applies on every device. */
(function(){
"use strict";

const TABS = [
  ["general","General","settings","Language, page size, undo send, signature and more"],
  ["labels","Labels","tag","Show, hide and organise labels"],
  ["inbox","Inbox","inbox","Inbox order and reading pane"],
  ["accounts","Accounts","contacts","Name, password, reply-to and storage"],
  ["filters","Filters and blocked addresses","spam","Sort incoming mail automatically and block senders"],
  ["forwarding","Forwarding and POP/IMAP","forward","Forward mail and use other mail apps"],
  ["vacation","Out of office","calendar","Automatic replies while you are away"],
  ["advanced","Advanced","more","Auto-advance, templates and unread badge"],
  ["themes","Themes","palette","Colours, photos and brightness"],
  ["shortcuts","Keyboard shortcuts","help","Keys for working faster"]
];
const phone = ()=> !!(window.matchMedia && matchMedia("(max-width:680px)").matches);
const live = ()=> !!(window.Live && Live.enabled);

Views.accountSettings = function(el, tab){
  if(!TABS.some(t=>t[0]===tab)) tab = phone() ? "" : "general";
  el.innerHTML = `<div class="st">
    <div class="st-head">${tab && phone() ? `<button class="icon-btn st-back" id="st-back" aria-label="All settings">${Icons.get("back")}</button>` : ""}
      <h1>${tab && phone() ? esc(TABS.find(t=>t[0]===tab)[1]) : "Settings"}</h1></div>
    ${phone() ? "" : `<nav class="st-tabs" aria-label="Settings sections">${TABS.map(([id,label])=>`<button data-stab="${id}" class="${tab===id?"on":""}" ${tab===id?'aria-current="page"':""}>${esc(label)}</button>`).join("")}</nav>`}
    <div class="st-body" id="st-body"></div></div>`;
  const back = el.querySelector("#st-back"); if(back) back.addEventListener("click", ()=> App.go("settings"));
  el.querySelectorAll("[data-stab]").forEach(b=> b.addEventListener("click", ()=> App.go("settings:"+b.dataset.stab)));
  const body = el.querySelector("#st-body");
  if(!tab){ renderHome(body); return; }
  const tabs = el.querySelector(".st-tabs .on"); if(tabs && tabs.scrollIntoView) tabs.scrollIntoView({block:"nearest", inline:"center"});
  ({general, labels, inbox, accounts, filters, forwarding, vacation, advanced,
    themes:b=>Views.settingsParts.renderThemes(b), shortcuts})[tab](body);
};

function renderHome(body){
  const u = Store.state.user;
  body.innerHTML = `<button class="st-me" data-go="accounts">${Profile.avatar(u.email, u.name, "st-me-avatar")}<span><b>${esc(u.name||u.email)}</b><small>${esc(u.email)}</small></span></button>
    <div class="st-list">${TABS.map(([id,label,icon,hint])=>`<button class="st-item" data-go="${id}"><span class="st-ico">${Icons.get(icon)}</span><span><b>${esc(label)}</b><small>${esc(hint)}</small></span><span class="st-chev">${Icons.get("chevron")}</span></button>`).join("")}</div>`;
  body.querySelectorAll("[data-go]").forEach(b=> b.addEventListener("click", ()=> App.go("settings:"+b.dataset.go)));
}

/* ---------- small building blocks ---------- */
const get = key=>{ const [scope,name]=key.split("."); return (scope==="mb"?Settings.mailbox:Settings.ui)[name]; };
const enc = v=> typeof v==="boolean" ? (v?"true":"false") : String(v);
const radio = (key, options)=> `<div class="st-radios" role="radiogroup">${options.map(([value,label,hint])=>`<label class="st-radio"><input type="radio" name="${key}" data-key="${key}" value="${esc(enc(value))}" ${enc(get(key))===enc(value)?"checked":""}><span><b>${label}</b>${hint?` <small>${hint}</small>`:""}</span></label>`).join("")}</div>`;
const select = (key, options, label)=> `<select data-key="${key}" aria-label="${esc(label||key)}">${options.map(([value,text])=>`<option value="${esc(enc(value))}" ${enc(get(key))===enc(value)?"selected":""}>${esc(text)}</option>`).join("")}</select>`;
const row = (title, control, hint)=> `<div class="st-row"><div class="st-label">${title}${hint?`<small>${hint}</small>`:""}</div><div class="st-control">${control}</div></div>`;
const saveBar = ()=> `<div class="st-save"><button class="btn primary" id="st-save" type="button">Save changes</button><button class="btn ghost" id="st-cancel" type="button">Cancel</button><span class="st-status" role="status"></span></div>`;
const parse = (input)=>{ const v=input.value; if(v==="true")return true; if(v==="false")return false; if(/^\d+$/.test(v) && input.dataset.num) return +v; return v; };
function collect(scope){
  const out={mailbox:{}, ui:{}};
  scope.querySelectorAll("[data-key]").forEach(input=>{
    if(input.type==="radio" && !input.checked) return;
    const [s,name]=input.dataset.key.split("."), value = input.type==="checkbox" ? input.checked : parse(input);
    if(enc(value)!==enc(get(input.dataset.key))) (s==="mb"?out.mailbox:out.ui)[name]=value;
  });
  if(!Object.keys(out.mailbox).length) delete out.mailbox; if(!Object.keys(out.ui).length) delete out.ui;
  return out;
}
/* Wires Save/Cancel; extra() may save things that are not plain settings (signature, name). */
function bindSave(body, rerender, extra, validate){
  const status = body.querySelector(".st-status"), saveBtn = body.querySelector("#st-save");
  const dirty = ()=> body.querySelector(".st-save").classList.add("dirty");
  body.addEventListener("input", dirty); body.addEventListener("change", dirty);
  body.querySelector("#st-cancel").addEventListener("click", ()=> rerender(body));
  saveBtn.addEventListener("click", async ()=>{
    const problem = validate && validate(); if(problem){ status.textContent = problem; return; }
    const change = collect(body); saveBtn.disabled = true; status.textContent = "Saving…";
    try{
      if(change.ui && "undoSend" in change.ui) change.ui.undoSendOn = change.ui.undoSend>0;
      if(change.mailbox || change.ui) await Settings.save(change);
      if(extra) await extra();
      status.textContent = ""; App.toast("Settings saved."); App.refreshNav(); rerender(body);
    }catch(error){ status.textContent = error.message; saveBtn.disabled = false; }
  });
}
const needLive = body=>{ body.innerHTML = `<div class="st-card"><p>This section works with a connected business mailbox. Sign in to your Dejoiy Mail account to use it.</p></div>`; };
const failed = (body, error, retry)=>{ body.innerHTML = `<div class="st-card st-error"><p>${esc(error.message)}</p><button class="btn" type="button">Try again</button></div>`; body.querySelector("button").addEventListener("click", ()=> retry(body)); };

/* ---------- General ---------- */
const FONTS = [["arial, helvetica, sans-serif","Sans Serif"],["times new roman, new york, times, serif","Serif"],["courier new, courier, monaco, monospace","Fixed width"],["georgia, serif","Georgia"],["verdana, helvetica, sans-serif","Verdana"],["tahoma, verdana, sans-serif","Tahoma"],["trebuchet ms, helvetica, sans-serif","Trebuchet"],["comic sans ms, comic sans, sans-serif","Comic Sans"]];
const ZONES = [["Asia/Kolkata","(GMT+05:30) India — Kolkata, New Delhi"],["Asia/Dubai","(GMT+04:00) Dubai"],["Asia/Karachi","(GMT+05:00) Karachi"],["Asia/Kathmandu","(GMT+05:45) Kathmandu"],["Asia/Dhaka","(GMT+06:00) Dhaka"],["Asia/Singapore","(GMT+08:00) Singapore"],["Asia/Shanghai","(GMT+08:00) Beijing, Shanghai"],["Asia/Tokyo","(GMT+09:00) Tokyo"],["Australia/Sydney","(GMT+10:00) Sydney"],["Pacific/Auckland","(GMT+12:00) Auckland"],["Europe/London","(GMT+00:00) London"],["Europe/Berlin","(GMT+01:00) Berlin"],["Europe/Paris","(GMT+01:00) Paris"],["Africa/Lagos","(GMT+01:00) Lagos"],["Africa/Johannesburg","(GMT+02:00) Johannesburg"],["America/Sao_Paulo","(GMT-03:00) São Paulo"],["America/New_York","(GMT-05:00) New York"],["America/Chicago","(GMT-06:00) Chicago"],["America/Denver","(GMT-07:00) Denver"],["America/Los_Angeles","(GMT-08:00) Los Angeles"],["UTC","(GMT+00:00) Coordinated Universal Time"]];
function general(body){
  const u = Store.state.user, mb = Settings.mailbox, photo = Profile.photo(u.email);
  const notif = !("Notification" in window) ? "This browser cannot show notifications." : Notification.permission==="granted" ? "Notifications are allowed in this browser." : Notification.permission==="denied" ? "Notifications are blocked for this site. Allow them in your browser's site settings." : `<button class="btn sm" type="button" id="sg-notify">Allow notifications in this browser</button>`;
  body.innerHTML = `<div class="st-card">
    ${row("Language", select("mb.locale",[["","English"],["en_GB","English (UK)"],["en_US","English (US)"],["hi","हिन्दी (Hindi)"]],"Language"), "Used by the mail server for automatic replies and notices. The app is shown in English for now.")}
    ${row("Time zone", select("mb.timeZone", ZONES.some(z=>z[0]===mb.timeZone)?ZONES:[[mb.timeZone,mb.timeZone],...ZONES], "Time zone"), "Used for out-of-office dates and server notices.")}
    ${row("Maximum page size", `<span class="st-inline">Show ${select("mb.pageSize",[["10","10"],["25","25"],["50","50"],["100","100"]],"Page size")} conversations per page</span>`)}
    ${row("Undo Send", `<span class="st-inline">Send cancellation period: <select data-key="ui.undoSend" data-num="1" aria-label="Send cancellation period">${[[0,"Off"],[5,"5"],[10,"10"],[20,"20"],[30,"30"]].map(([v,t])=>`<option value="${v}" ${Number(Settings.ui.undoSendOn===false?0:Settings.ui.undoSend)===v?"selected":""}>${t}</option>`).join("")}</select> seconds</span>`, "After you press Send, you have this long to change your mind.")}
    ${row("Default reply behaviour", radio("ui.defaultReply",[["reply","Reply"],["replyall","Reply all"]]))}
    ${row("Hover actions", radio("ui.hoverActions",[[true,"Enable hover actions","Archive, delete and mark as read appear when you point at a conversation."],[false,"Disable hover actions"]]), "On computers with a mouse.")}
    ${row("Send and Archive", radio("ui.sendArchive",[[true,'Show "Send &amp; Archive" button in reply'],[false,'Hide "Send &amp; Archive" button in reply']]))}
    ${row("Default text style", `<div class="st-inline st-wrap">${select("mb.fontFamily",FONTS,"Font")} ${select("mb.fontSize",[["10pt","Small"],["12pt","Normal"],["14pt","Large"],["18pt","Huge"]],"Text size")} <label class="st-color">Colour <input type="color" data-key="mb.fontColor" value="${esc(mb.fontColor)}"></label></div><p class="st-preview" id="sg-preview" style="${esc(Settings.textStyle())}">This is what your body text will look like.</p>`)}
    ${row("Images", radio("mb.externalImages",[[true,"Always display external images"],[false,"Ask before displaying external images","Pictures from the internet stay hidden, so senders cannot tell when you open their mail."]]))}
    ${row("Spelling", radio("ui.spellcheck",[[true,"Spelling suggestions on"],[false,"Spelling suggestions off"]]))}
    ${row("Auto-correct", radio("ui.autocorrect",[[true,"Auto-correct on"],[false,"Auto-correct off"]]), "Phones and tablets correct and capitalise as you type.")}
    ${row("Conversation view", radio("mb.conversationView",[["conversation","Conversation view on"],["message","Conversation view off"]]), "Sets whether emails of the same topic are grouped together.")}
    ${row("Desktop notifications", radio("ui.notifications",[["all","New mail notifications on","Notify me when any new message arrives in my inbox"],["important","Important mail notifications on","Notify me only when an important message arrives"],["off","Mail notifications off"]])+`<p class="st-note">${notif}</p>`, "Pop-up notices when new mail arrives while Dejoiy Mail is open in the background.")}
    ${row("Check for new mail", `<span class="st-inline">Every ${select("mb.pollInterval",[["1m","1 minute"],["2m","2 minutes"],["5m","5 minutes"],["10m","10 minutes"],["15m","15 minutes"],["30m","30 minutes"]],"Check for new mail")}</span>`)}
    ${row("Keyboard shortcuts", radio("mb.keyboardShortcuts",[[false,"Keyboard shortcuts off"],[true,"Keyboard shortcuts on"]]))}
    ${row("Button labels", radio("ui.buttonLabels",[["icons","Icons"],["text","Text"]]))}
    ${row("My picture", `<div class="st-photo">${Profile.avatar(u.email, u.name, "profile-avatar")}<div><div class="btn-row"><label class="btn sm" style="cursor:pointer">${photo?"Change picture":"Upload picture"}<input type="file" id="sg-photo" accept="image/png,image/jpeg,image/webp" class="sr"></label>${photo?`<button class="btn sm ghost" id="sg-photo-remove" type="button">Remove</button>`:""}</div><small>Your picture is shown on your messages and to colleagues at your company.</small></div></div>`)}
    ${row("Create contacts for auto-complete", radio("mb.autoAddContacts",[[true,"When I send a message to a new person, add them to my contacts so that I can auto-complete to them next time"],[false,"I'll add contacts myself"]]))}
    ${row("Signature", signatureEditor(), "Added at the end of new messages, and above the quoted text in replies and forwards.")}
    ${row("Personal level indicators", radio("ui.indicators",[[false,"No indicators"],[true,"Show indicators","An arrow ( › ) by messages sent to my address, and a double arrow ( » ) by messages sent only to me."]]))}
    ${row("Snippets", radio("mb.snippets",[[true,"Show snippets","Show a preview of each message in the list."],[false,"No snippets","Show the subject only."]]))}
    ${row("Density", radio("ui.density",[["comfortable","Comfortable"],["compact","Compact","Fits more conversations on the screen."]]))}
    ${row("Sounds", `<label class="st-check"><input type="checkbox" id="sg-sounds" ${Store.state.prefs.sounds?"checked":""}> Play a sound for new and sent mail</label>`)}
    ${row("Out-of-office auto-reply", `<p class="st-note">${mb.vacationOn?"<b>On</b>"+(mb.vacationUntil?" until "+esc(mb.vacationUntil):""):"Off"}</p><button class="btn sm" type="button" data-goto="vacation">Set up out of office</button>`)}
  </div>${saveBar()}`;
  const preview = body.querySelector("#sg-preview");
  body.querySelectorAll('[data-key="mb.fontFamily"],[data-key="mb.fontSize"],[data-key="mb.fontColor"]').forEach(i=> i.addEventListener("input", ()=>{
    preview.style.fontFamily = body.querySelector('[data-key="mb.fontFamily"]').value; preview.style.fontSize = body.querySelector('[data-key="mb.fontSize"]').value; preview.style.color = body.querySelector('[data-key="mb.fontColor"]').value; }));
  const notifyBtn = body.querySelector("#sg-notify");
  if(notifyBtn) notifyBtn.addEventListener("click", async ()=>{ try{ await Settings.askNotificationPermission(); App.toast("Notifications allowed."); }catch(error){ App.toast(error.message); } general(body); });
  body.querySelector('[data-goto="vacation"]').addEventListener("click", ()=> App.go("settings:vacation"));
  bindPhoto(body, general);
  const sig = bindSignature(body), original = sig.innerHTML;
  bindSave(body, general, async ()=>{
    const sounds = body.querySelector("#sg-sounds").checked;
    if(sounds!==!!Store.state.prefs.sounds){ Store.state.prefs.sounds = sounds; Store.save(); }
    if(sig.innerHTML!==original) await saveProfile(u.name, sig);
  });
}
function signatureEditor(){
  return `<div class="sig-editor">
    <div class="fmt-bar sig-bar" role="toolbar" aria-label="Signature formatting">
      ${[["bold","B","Bold"],["italic","I","Italic"],["underline","U","Underline"],["createLink","🔗","Link"]].map(([c,l,t])=>`<button class="icon-btn sm" type="button" data-sfmt="${c}" title="${t}" aria-label="${t}"><b>${l}</b></button>`).join("")}
      <label class="icon-btn sm sig-image-btn" title="Add an image (logo, scanned signature)" style="cursor:pointer">${Icons.get("photo")}<span>Image</span><input type="file" id="sg-sig-image" accept="image/png,image/jpeg,image/gif" class="sr"></label>
      <span style="flex:1"></span><button class="btn sm ghost" type="button" id="sg-sig-clear">Clear</button>
    </div>
    <div id="sg-sig" class="sig-body" contenteditable="true" role="textbox" aria-multiline="true" aria-label="Signature" data-ph="Your name, title, phone… add your logo with Image.">${Profile.signatureHtml()}</div></div>`;
}
function bindSignature(body){
  const sig = body.querySelector("#sg-sig");
  body.querySelectorAll("[data-sfmt]").forEach(b=> b.addEventListener("click", ()=>{
    sig.focus();
    if(b.dataset.sfmt==="createLink"){ const url=prompt("Link URL:","https://"); if(url && /^(https?:\/\/|mailto:)/i.test(url)) document.execCommand("createLink",false,url); }
    else document.execCommand(b.dataset.sfmt,false,null);
    sig.dispatchEvent(new Event("input",{bubbles:true}));
  }));
  body.querySelector("#sg-sig-clear").addEventListener("click", ()=>{ sig.innerHTML=""; sig.focus(); sig.dispatchEvent(new Event("input",{bubbles:true})); });
  body.querySelector("#sg-sig-image").addEventListener("change", async ev=>{
    const file=ev.target.files[0]; ev.target.value=""; if(!file) return;
    const label=ev.target.closest("label"); label.classList.add("busy");
    try{ const {url,width}=await Profile.signatureImage(file); sig.focus(); document.execCommand("insertHTML",false,`<img src="${esc(url)}" width="${width}" alt="">`); sig.dispatchEvent(new Event("input",{bubbles:true})); }
    catch(error){ App.toast(error.message); }finally{ label.classList.remove("busy"); }
  });
  return sig;
}
async function saveProfile(name, sig){
  const u = Store.state.user;
  const signatureHtml = sig ? (sig.textContent.trim()||sig.querySelector("img") ? sig.innerHTML : "") : (u.signatureHtml||"");
  const signature = sig ? (signatureHtml ? sig.innerText.trim() : "") : (u.signature||"");
  if(live()){
    await Live.request("preferences",{op:"profile",name,signature,signatureHtml});
    const saved = await Live.request("preferences"); u.name=name; u.signature=saved.signature; u.signatureHtml=saved.signatureHtml||"";
  } else { u.name=name; u.signature=signature; u.signatureHtml=signatureHtml; Store.save(); }
}
function bindPhoto(body, rerender){
  const u = Store.state.user, input = body.querySelector("#sg-photo"), remove = body.querySelector("#sg-photo-remove");
  if(input) input.addEventListener("change", async ()=>{ const file=input.files[0]; input.value=""; if(!file) return;
    try{ await Profile.setPhoto(file); App.toast("Profile picture updated."); App.refreshNav(); rerender(body); }catch(error){ App.toast(error.message); } });
  if(remove) remove.addEventListener("click", async ()=>{ try{ await Profile.setPhoto(null); App.toast("Profile picture removed."); App.refreshNav(); rerender(body); }catch(error){ App.toast(error.message); } });
}

/* ---------- Labels ---------- */
const SYSTEM = [["inbox","Inbox"],["starred","Starred"],["sent","Sent"],["drafts","Drafts"],["archive","Archive"],["spam","Spam"],["trash","Bin"],["unread","Unread"],["attach","Has attachments"],["important","Important"]];
const LABEL_COLOURS = [[0,"Default","#9aa0a6"],[1,"Blue","#1a73e8"],[2,"Cyan","#12b5cb"],[3,"Green","#1e8e3e"],[4,"Purple","#9334e6"],[5,"Red","#d93025"],[6,"Yellow","#f9ab00"],[7,"Pink","#e52592"],[8,"Grey","#5f6368"],[9,"Orange","#e8710a"]];
async function labels(body){
  const hidden = new Set(Settings.ui.hiddenFolders||[]);
  body.innerHTML = `<div class="st-card"><h2>System labels</h2><p class="st-note">Choose which folders and views appear in your label list.</p>
    <div class="st-table">${SYSTEM.map(([id,name])=>`<div class="st-trow"><span>${esc(name)}</span><span class="st-seg">${id==="inbox"?`<b>show</b>`:`<button type="button" data-show="${id}" class="${hidden.has(id)?"":"on"}">show</button><button type="button" data-hide="${id}" class="${hidden.has(id)?"on":""}">hide</button>`}</span></div>`).join("")}</div></div>
    <div class="st-card"><div class="st-cardhead"><h2>Labels</h2><button class="btn sm primary" id="lb-new" type="button">Create new label</button></div>
    <div id="lb-list"><p class="st-note">Loading labels…</p></div><p class="st-note">Removing a label will not remove the messages with that label.</p></div>`;
  const setHidden = async (id, hide)=>{ const next=new Set(Settings.ui.hiddenFolders||[]); hide?next.add(id):next.delete(id);
    try{ await Settings.save({ui:{hiddenFolders:[...next]}}); App.refreshNav(); labels(body); }catch(error){ App.toast(error.message); } };
  body.querySelectorAll("[data-show]").forEach(b=> b.addEventListener("click", ()=> setHidden(b.dataset.show,false)));
  body.querySelectorAll("[data-hide]").forEach(b=> b.addEventListener("click", ()=> setHidden(b.dataset.hide,true)));
  const listEl = body.querySelector("#lb-list");
  if(!live()){ listEl.innerHTML = `<p class="st-note">Labels are stored on your mail server once you sign in to a business mailbox.</p>`; body.querySelector("#lb-new").disabled=true; return; }
  const draw = items=>{
    listEl.innerHTML = items.length ? `<div class="st-table">${items.map(l=>`<div class="st-trow"><span class="lb-name"><i class="lb-dot" style="background:${(LABEL_COLOURS.find(c=>String(c[0])===String(l.color))||LABEL_COLOURS[0])[2]}"></i>${esc(l.name)} <small>${l.count} message${l.count===1?"":"s"}</small></span>
      <span class="st-actions"><button class="btn sm ghost" type="button" data-lrename="${l.id}">Rename</button><button class="btn sm ghost" type="button" data-lcolour="${l.id}">Colour</button><button class="btn sm ghost danger" type="button" data-ldel="${l.id}">Remove</button></span></div>`).join("")}</div>` : `<p class="st-note">You have no labels yet. Labels you add to messages appear here.</p>`;
    const act = async (data, message)=>{ try{ const r=await Live.request("labels",data); draw(r.labels); if(message) App.toast(message); }catch(error){ App.toast(error.message); } };
    listEl.querySelectorAll("[data-lrename]").forEach(b=> b.addEventListener("click", ()=>{ const l=items.find(x=>x.id===b.dataset.lrename);
      App.promptDialog("Rename label","New name",l.name, name=> name.trim() && act({op:"rename",id:l.id,name:name.trim()},"Label renamed.")); }));
    listEl.querySelectorAll("[data-lcolour]").forEach(b=> b.addEventListener("click", ev=> App.menu(ev.currentTarget, LABEL_COLOURS.map(([n,name])=>({label:name, fn:()=>act({op:"color",id:b.dataset.lcolour,color:n})})))));
    listEl.querySelectorAll("[data-ldel]").forEach(b=> b.addEventListener("click", ()=>{ const l=items.find(x=>x.id===b.dataset.ldel);
      App.confirm(`Remove the label "${l.name}"? Messages keep everything else.`, ()=> act({op:"delete",id:l.id},"Label removed.")); }));
  };
  body.querySelector("#lb-new").addEventListener("click", ()=> App.promptDialog("New label","Label name","", async name=>{
    name=String(name||"").trim(); if(!name) return; try{ const r=await Live.request("labels",{op:"create",name}); draw(r.labels); App.toast("Label created."); }catch(error){ App.toast(error.message); } }));
  try{ draw((await Live.request("labels")).labels); }catch(error){ listEl.innerHTML=`<p class="st-error">${esc(error.message)}</p>`; }
}

/* ---------- Inbox ---------- */
function inbox(body){
  body.innerHTML = `<div class="st-card">
    ${row("Inbox type", radio("ui.inboxType",[["default","Default","Newest conversations first."],["unread","Unread first"],["starred","Starred first"],["important","Important first"]]))}
    ${row("Reading pane", radio("ui.readingPane",[["off","No split","Conversations open in place of the list."],["right","Right of inbox"],["bottom","Below inbox"]]), "On phones a conversation always opens full screen.")}
    ${row("Importance markers", radio("ui.importanceMarkers",[[true,"Show markers","Show a marker by messages marked as important."],[false,"No markers"]]))}
  </div>${saveBar()}`;
  bindSave(body, inbox);
}

/* ---------- Accounts ---------- */
function accounts(body){
  const u = Store.state.user, a = Settings.account, mb = Settings.mailbox;
  const used = a ? a.used/1048576 : 0, quota = a && a.quota ? a.quota/1048576 : 0, pct = quota ? Math.min(100, used/quota*100) : 0;
  const size = mbs => mbs>=1024 ? (mbs/1024).toFixed(mbs>=10240?0:1)+" GB" : mbs.toFixed(1)+" MB";
  body.innerHTML = `<div class="st-card">
    ${row("Send mail as", `<div class="st-field"><label for="ac-name">Your name</label><input type="text" id="ac-name" value="${esc(u.name)}" maxlength="256" autocomplete="name"></div><p class="st-note">Messages you send show <b id="ac-from">${esc(u.name)} &lt;${esc(u.email)}&gt;</b></p><p class="st-note">To send from another address, ask your company administrator to add it to your account.</p>`)}
    ${row("Reply-to address", `<label class="st-check"><input type="checkbox" data-key="mb.replyToEnabled" ${mb.replyToEnabled?"checked":""}> Ask people to reply to a different address</label><div class="st-field"><input type="email" data-key="mb.replyTo" value="${esc(mb.replyTo)}" placeholder="name@company.com" autocomplete="email"></div>`)}
    ${row("Storage", a && quota ? `<div class="st-meter" role="meter" aria-valuenow="${pct.toFixed(0)}" aria-valuemin="0" aria-valuemax="100"><i style="width:${pct.toFixed(1)}%"></i></div><p class="st-note">${size(used)} of ${size(quota)} used (${pct.toFixed(pct<1?1:0)}%)</p>` : `<p class="st-note">${a?size(used)+" used":"—"}</p>`)}
  </div>${saveBar()}
  <form class="st-card" id="ac-pw" autocomplete="on"><h2>Change password</h2>
    ${a && a.features && a.features.changePassword===false ? `<p class="st-note">Your administrator manages passwords for this account.</p>` : `
    <input type="text" name="username" value="${esc(u.email)}" autocomplete="username" hidden>
    <div class="st-field"><label for="ac-cur">Current password</label><input type="password" id="ac-cur" autocomplete="current-password" required></div>
    <div class="st-field"><label for="ac-new">New password</label><input type="password" id="ac-new" autocomplete="new-password" minlength="${a?a.passwordMinLength:6}" required></div>
    <div class="st-field"><label for="ac-new2">Confirm new password</label><input type="password" id="ac-new2" autocomplete="new-password" required></div>
    <p class="st-note">At least ${a?a.passwordMinLength:6} characters. Mail apps on your other devices will ask for the new password.</p>
    <p class="st-error" role="alert"></p><button class="btn primary" ${live()?"":"disabled"}>Change password</button>`}
  </form>
  <div class="st-card"><h2>Sign out</h2><p class="st-note">Sign out of Dejoiy Mail on this device.</p><button class="btn" id="ac-out" type="button">Sign out</button></div>`;
  const nameInput = body.querySelector("#ac-name");
  nameInput.addEventListener("input", ()=>{ body.querySelector("#ac-from").textContent = `${nameInput.value.trim()||u.email} <${u.email}>`; });
  bindSave(body, accounts, async ()=>{ const name=nameInput.value.trim(); if(!name) throw new Error("Enter your name."); if(name!==u.name) await saveProfile(name, null); });
  const form = body.querySelector("#ac-pw");
  if(form.querySelector("#ac-cur")) form.addEventListener("submit", async ev=>{
    ev.preventDefault(); const alert=form.querySelector("[role=alert]"), button=form.querySelector("button");
    const current=form.querySelector("#ac-cur").value, next=form.querySelector("#ac-new").value;
    if(next!==form.querySelector("#ac-new2").value){ alert.textContent="The new passwords do not match."; return; }
    button.disabled=true; alert.textContent="";
    try{ await Live.request("password",{current,password:next}); form.reset(); App.toast("Password changed."); }
    catch(error){ alert.textContent=error.message; }finally{ button.disabled=false; }
  });
  body.querySelector("#ac-out").addEventListener("click", async ()=>{ if(live()) await Live.logout(); else App.toast("Demo build — there is no server session to sign out of."); });
}

/* ---------- Filters and blocked addresses ---------- */
const BLANK = ()=>({name:"",active:true,match:"all",from:"",to:"",subject:"",hasWords:"",doesntHave:"",hasAttachment:false,sizeOver:0,actions:{folder:"",markRead:false,star:false,label:"",forward:"",delete:false,stop:true}});
const describe = f=>{
  const c=[]; if(f.from)c.push(`from: ${f.from}`); if(f.to)c.push(`to: ${f.to}`); if(f.subject)c.push(`subject: ${f.subject}`); if(f.hasWords)c.push(`has: ${f.hasWords}`); if(f.doesntHave)c.push(`doesn't have: ${f.doesntHave}`); if(f.hasAttachment)c.push("has attachment"); if(f.sizeOver)c.push(`larger than ${f.sizeOver} KB`);
  const a=f.actions, d=[]; if(a.folder==="archive")d.push("Skip the inbox (archive)"); if(a.folder==="spam")d.push("Send to Spam"); if(a.folder==="inbox")d.push("Keep in inbox"); if(a.delete)d.push("Delete it"); if(a.markRead)d.push("Mark as read"); if(a.star)d.push("Star it"); if(a.label)d.push(`Apply label "${a.label}"`); if(a.forward)d.push(`Forward to ${a.forward}`);
  return {when:c.join(f.match==="any"?" OR ":", ")||"any message", then:d.join(", ")||"no action"};
};
async function filters(body){
  if(!live()){ Views.settingsParts.renderFilters(body); return; }
  body.innerHTML = `<div class="st-card"><p class="st-note">Loading filters…</p></div>`;
  let state;
  try{ state = await Live.request("filters"); }catch(error){ failed(body, error, filters); return; }
  const sel = new Set(), blockSel = new Set();
  const commit = async (next, message)=>{
    try{ state = await Live.request("filters", {filters:next.filters, blocked:next.blocked}); sel.clear(); blockSel.clear(); draw(); if(message) App.toast(message); return true; }
    catch(error){ App.toast(error.message); return false; }
  };
  const draw = ()=>{
    body.innerHTML = `<div class="st-card"><h2>Filters</h2><p class="st-note">The following filters are applied to all incoming mail by the mail server, even when Dejoiy Mail is closed.</p>
      <div class="st-toolbar"><span>Select: <button type="button" class="st-link" id="fl-all">All</button>, <button type="button" class="st-link" id="fl-none">None</button></span>
        <button class="btn sm" type="button" id="fl-export">Export</button><button class="btn sm danger" type="button" id="fl-delete">Delete</button></div>
      <div class="st-table">${state.filters.map((f,i)=>{ const d=describe(f); return `<div class="st-trow st-filter"><label class="st-check"><input type="checkbox" data-fsel="${i}" ${sel.has(i)?"checked":""} aria-label="Select ${esc(f.name)}"></label>
        <span class="st-ftext"><b>${esc(f.name)}</b>${f.active?"":` <span class="chip">paused</span>`}<small>Matches: ${esc(d.when)}</small><small>Do this: ${esc(d.then)}</small></span>
        <span class="st-actions"><button class="btn sm ghost" type="button" data-fedit="${i}">Edit</button><button class="btn sm ghost" type="button" data-ftoggle="${i}">${f.active?"Pause":"Resume"}</button></span></div>`; }).join("") || `<p class="st-note">You have no filters yet.</p>`}</div>
      ${state.unmanaged?`<p class="st-note">${state.unmanaged} more filter${state.unmanaged===1?" was":"s were"} created in another mail app; ${state.unmanaged===1?"it is":"they are"} kept as they are.</p>`:""}
      <div class="btn-row"><button class="btn primary" type="button" id="fl-new">Create a new filter</button><label class="btn" style="cursor:pointer">Import filters<input type="file" id="fl-import" accept="application/json,.json" class="sr"></label></div></div>
    <div class="st-card"><h2>Blocked addresses</h2><p class="st-note">Messages from these addresses or domains go straight to Spam.</p>
      <form class="st-addrow" id="bl-form"><input type="text" id="bl-in" placeholder="name@example.com or example.com" aria-label="Address or domain to block" autocomplete="off"><button class="btn">Block</button></form>
      ${state.blocked.length ? `<div class="st-toolbar"><span>Select: <button type="button" class="st-link" id="bl-all">All</button>, <button type="button" class="st-link" id="bl-none">None</button></span><button class="btn sm" type="button" id="bl-unblock">Unblock selected addresses</button></div>
      <div class="st-table">${state.blocked.map((a,i)=>`<label class="st-trow st-check"><input type="checkbox" data-bsel="${i}" ${blockSel.has(i)?"checked":""}> ${esc(a)}</label>`).join("")}</div>` : `<p class="st-note">You currently have no blocked addresses.</p>`}</div>`;
    const q = s=> body.querySelector(s);
    body.querySelectorAll("[data-fsel]").forEach(c=> c.addEventListener("change", ()=>{ c.checked?sel.add(+c.dataset.fsel):sel.delete(+c.dataset.fsel); }));
    q("#fl-all").addEventListener("click", ()=>{ state.filters.forEach((_,i)=>sel.add(i)); draw(); });
    q("#fl-none").addEventListener("click", ()=>{ sel.clear(); draw(); });
    q("#fl-delete").addEventListener("click", ()=>{ if(!sel.size){ App.toast("Select the filters to delete."); return; }
      App.confirm(`Delete ${sel.size} filter${sel.size===1?"":"s"}?`, ()=>{ commit({filters:state.filters.filter((_,i)=>!sel.has(i)), blocked:state.blocked}, "Filters deleted."); }); });
    q("#fl-export").addEventListener("click", ()=>{
      const chosen = sel.size ? state.filters.filter((_,i)=>sel.has(i)) : state.filters;
      if(!chosen.length){ App.toast("There are no filters to export."); return; }
      const url = URL.createObjectURL(new Blob([JSON.stringify({dmailFilters:1, filters:chosen}, null, 2)], {type:"application/json"}));
      const link = document.createElement("a"); link.href=url; link.download="dmail-filters.json"; document.body.appendChild(link); link.click(); link.remove(); setTimeout(()=>URL.revokeObjectURL(url), 1000);
    });
    q("#fl-import").addEventListener("change", async ev=>{
      const file = ev.target.files[0]; ev.target.value=""; if(!file) return;
      try{ const data = JSON.parse(await file.text()); const list = Array.isArray(data) ? data : data.filters;
        if(!Array.isArray(list) || !list.length) throw new Error("This file has no filters.");
        const names = new Set(state.filters.map(f=>f.name));
        const added = list.map(f=>({...BLANK(), ...f, actions:{...BLANK().actions, ...(f.actions||{})}})).map(f=>{ let n=f.name||"Imported filter", k=2; while(names.has(n)) n=`${f.name||"Imported filter"} (${k++})`; names.add(n); return {...f, name:n}; });
        await commit({filters:[...state.filters, ...added], blocked:state.blocked}, `${added.length} filter${added.length===1?"":"s"} imported.`);
      }catch(error){ App.toast(error instanceof SyntaxError ? "This is not a filters file." : error.message); }
    });
    body.querySelectorAll("[data-ftoggle]").forEach(b=> b.addEventListener("click", ()=>{ const i=+b.dataset.ftoggle; const next=state.filters.map((f,j)=>j===i?{...f,active:!f.active}:f); commit({filters:next, blocked:state.blocked}, next[i].active?"Filter resumed.":"Filter paused."); }));
    body.querySelectorAll("[data-fedit]").forEach(b=> b.addEventListener("click", ()=> filterDialog(state.filters[+b.dataset.fedit], f=> commit({filters:state.filters.map((x,j)=>j===+b.dataset.fedit?f:x), blocked:state.blocked}, "Filter saved."))));
    q("#fl-new").addEventListener("click", ()=> filterDialog(null, f=> commit({filters:[...state.filters, f], blocked:state.blocked}, "Filter created.")));
    q("#bl-form").addEventListener("submit", ev=>{ ev.preventDefault(); const v=q("#bl-in").value.trim().toLowerCase();
      if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) && !/^@?[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(v)){ App.toast("Enter an email address or a domain such as example.com."); return; }
      if(state.blocked.includes(v.replace(/^@/,""))){ App.toast("Already blocked."); return; }
      commit({filters:state.filters, blocked:[...state.blocked, v.replace(/^@/,"")]}, "Blocked. New messages from them go to Spam."); });
    if(state.blocked.length){
      body.querySelectorAll("[data-bsel]").forEach(c=> c.addEventListener("change", ()=>{ c.checked?blockSel.add(+c.dataset.bsel):blockSel.delete(+c.dataset.bsel); }));
      q("#bl-all").addEventListener("click", ()=>{ state.blocked.forEach((_,i)=>blockSel.add(i)); draw(); });
      q("#bl-none").addEventListener("click", ()=>{ blockSel.clear(); draw(); });
      q("#bl-unblock").addEventListener("click", ()=>{ if(!blockSel.size){ App.toast("Select the addresses to unblock."); return; }
        commit({filters:state.filters, blocked:state.blocked.filter((_,i)=>!blockSel.has(i))}, "Unblocked."); });
    }
  };
  draw();
}
function filterDialog(existing, done){
  const f = existing ? JSON.parse(JSON.stringify(existing)) : BLANK(), a = f.actions;
  const text = (k,label,ph,type)=>`<div class="st-field"><label for="ff-${k}">${label}</label><input type="${type||"text"}" id="ff-${k}" value="${esc(f[k]||"")}" placeholder="${ph||""}" autocomplete="off"></div>`;
  App.dialog({title: existing?"Edit filter":"Create a filter", wide:true, body:`
    ${text("name","Filter name","e.g. Newsletters")}
    <div class="st-dsec">Match messages</div>
    <div class="st-grid">${text("from","From","name@example.com")}${text("to","To","")}${text("subject","Subject","")}${text("hasWords","Has the words","")}${text("doesntHave","Doesn't have","")}
      <div class="st-field"><label for="ff-size">Larger than (KB)</label><input type="number" id="ff-size" min="0" max="100000" value="${f.sizeOver||""}" inputmode="numeric"></div></div>
    <label class="st-check"><input type="checkbox" id="ff-att" ${f.hasAttachment?"checked":""}> Has attachment</label>
    <label class="st-check"><input type="checkbox" id="ff-any" ${f.match==="any"?"checked":""}> Match if <b>any</b> of these is true (otherwise all must be)</label>
    <div class="st-dsec">When a message arrives that matches</div>
    <div class="st-field"><label for="ff-folder">Move it</label><select id="ff-folder">${[["","Leave it where it lands"],["archive","Skip the inbox (archive it)"],["spam","Send it to Spam"],["inbox","Keep it in the inbox (never Spam)"]].map(([v,t])=>`<option value="${v}" ${a.folder===v?"selected":""}>${t}</option>`).join("")}</select></div>
    ${[["markRead","Mark as read"],["star","Star it"],["delete","Delete it"]].map(([k,l])=>`<label class="st-check"><input type="checkbox" data-fa="${k}" ${a[k]?"checked":""}> ${l}</label>`).join("")}
    <div class="st-grid"><div class="st-field"><label for="ff-label">Apply the label</label><input type="text" id="ff-label" value="${esc(a.label||"")}" placeholder="e.g. Work" maxlength="64"></div>
      <div class="st-field"><label for="ff-fwd">Forward it to</label><input type="email" id="ff-fwd" value="${esc(a.forward||"")}" placeholder="name@example.com"></div></div>
    <label class="st-check"><input type="checkbox" id="ff-stop" ${a.stop!==false?"checked":""}> Don't apply later filters to these messages</label>
    <label class="st-check"><input type="checkbox" id="ff-active" ${f.active!==false?"checked":""}> Filter is on</label>`,
    actions:[{label:"Cancel"},{label:existing?"Save":"Create filter", primary:true, fn:()=>{
      const v = id=> document.getElementById(id).value.trim();
      const next = {name:v("ff-name")||(v("ff-from")?`From ${v("ff-from")}`:"My filter"), active:document.getElementById("ff-active").checked, match:document.getElementById("ff-any").checked?"any":"all",
        from:v("ff-from"), to:v("ff-to"), subject:v("ff-subject"), hasWords:v("ff-hasWords"), doesntHave:v("ff-doesntHave"), hasAttachment:document.getElementById("ff-att").checked, sizeOver:parseInt(v("ff-size"),10)||0,
        actions:{folder:v("ff-folder"), label:v("ff-label"), forward:v("ff-fwd"), stop:document.getElementById("ff-stop").checked, markRead:false, star:false, delete:false}};
      document.querySelectorAll("[data-fa]").forEach(c=>{ next.actions[c.dataset.fa]=c.checked; });
      if(!next.from && !next.to && !next.subject && !next.hasWords && !next.doesntHave && !next.hasAttachment && !next.sizeOver){ App.toast("Add at least one thing to match."); return false; }
      if(!next.actions.folder && !next.actions.label && !next.actions.forward && !next.actions.markRead && !next.actions.star && !next.actions.delete){ App.toast("Choose at least one action."); return false; }
      done(next);
    }}]});
}

/* ---------- Forwarding and POP/IMAP ---------- */
function forwarding(body){
  const mb = Settings.mailbox, a = Settings.account, f = (a && a.features) || {}, host = esc(Settings.server.host || location.hostname), email = esc(Store.state.user.email);
  body.innerHTML = `<div class="st-card">
    ${row("Forwarding", f.forwarding===false ? `<p class="st-note">Your administrator has turned off forwarding for this account.</p>` :
      `<div class="st-field"><label for="fw-to">Forward a copy of incoming mail to</label><input type="text" id="fw-to" data-key="mb.forwardTo" value="${esc(mb.forwardTo)}" placeholder="name@example.com" autocomplete="email" inputmode="email"></div>
       <p class="st-note">Separate up to five addresses with commas. Leave empty to stop forwarding.</p>
       ${radio("mb.forwardKeepCopy",[[true,"Keep Dejoiy Mail's copy in the Inbox"],[false,"Don't keep a copy","Messages are only delivered to the forwarding address."]])}`,
      "Tip: you can also forward only some of your mail by creating a filter.")}
    ${row("POP download", `<p class="st-note">Status: <b>${f.pop?"POP is enabled":"POP is disabled by your administrator"}</b></p>
      <div class="st-field"><label>When messages are downloaded with POP</label>${select("mb.popDelete",[["keep","Keep Dejoiy Mail's copy in the Inbox"],["read","Mark Dejoiy Mail's copy as read"],["trash","Move Dejoiy Mail's copy to the Bin"],["delete","Delete Dejoiy Mail's copy"]],"POP download action")}</div>
      <details class="st-details"><summary>Configuration instructions</summary><dl class="st-dl"><dt>Incoming server (POP3)</dt><dd>${host}</dd><dt>Port</dt><dd>995, SSL/TLS</dd><dt>Outgoing server (SMTP)</dt><dd>${host}, port 587 (STARTTLS) or 465 (SSL/TLS)</dd><dt>User name</dt><dd>${email}</dd><dt>Password</dt><dd>Your Dejoiy Mail password</dd></dl></details>`)}
    ${row("IMAP access", `<p class="st-note">Status: <b>${f.imap===false?"IMAP is disabled by your administrator":"IMAP is available"}</b> — use Dejoiy Mail in Outlook, Thunderbird, Apple Mail or your phone's mail app.</p>
      <details class="st-details"><summary>Configuration instructions</summary><dl class="st-dl"><dt>Incoming server (IMAP)</dt><dd>${host}</dd><dt>Port</dt><dd>993, SSL/TLS</dd><dt>Outgoing server (SMTP)</dt><dd>${host}, port 587 (STARTTLS) or 465 (SSL/TLS), sign-in required</dd><dt>User name</dt><dd>${email}</dd><dt>Password</dt><dd>Your Dejoiy Mail password</dd></dl></details>`)}
  </div>${saveBar()}`;
  bindSave(body, forwarding);
}

/* ---------- Out of office ---------- */
function vacation(body){
  const mb = Settings.mailbox, today = new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,10);
  body.innerHTML = `<div class="st-card">
    ${row("Out-of-office auto-reply", radio("mb.vacationOn",[[false,"Out-of-office auto-reply off"],[true,"Out-of-office auto-reply on"]]), "Sends an automatic reply to incoming messages.")}
    ${row("First day", `<input type="date" data-key="mb.vacationFrom" value="${esc(mb.vacationFrom)}" min="${mb.vacationFrom&&mb.vacationFrom<today?esc(mb.vacationFrom):today}">`, "Optional. Replies start on this day.")}
    ${row("Last day", `<input type="date" data-key="mb.vacationUntil" value="${esc(mb.vacationUntil)}" min="${today}">`, "Optional. Replies stop after this day.")}
    ${row("Message", `<textarea data-key="mb.vacationMessage" rows="6" maxlength="8192" placeholder="Thanks for your email. I'm away until … and will reply when I'm back.">${esc(mb.vacationMessage)}</textarea>`)}
    ${row("Who gets the reply", radio("mb.vacationAudience",[["everyone","Everyone"],["company","Only people in my company"],["contacts","Only people in my company or my contacts"]]))}
    <div id="vc-external">${row("Reply to people outside my company", `<label class="st-check"><input type="checkbox" data-key="mb.vacationExternalOn" ${mb.vacationExternalOn?"checked":""}> Send them a different message</label><textarea data-key="mb.vacationExternalMessage" rows="4" maxlength="8192" placeholder="Message for people outside your company">${esc(mb.vacationExternalMessage)}</textarea>`)}</div>
    ${row("Frequency", `<span class="st-inline">Reply to the same person at most once every ${select("mb.vacationEvery",[["1d","day"],["4d","4 days"],["7d","7 days"]],"Reply frequency")}</span>`)}
  </div>${saveBar()}`;
  const ext = body.querySelector("#vc-external"), sync = ()=>{ ext.hidden = body.querySelector('[name="mb.vacationAudience"]:checked')?.value!=="everyone"; };
  body.querySelectorAll('[name="mb.vacationAudience"]').forEach(r=> r.addEventListener("change", sync)); sync();
  bindSave(body, vacation, async ()=>{ Store.state.vacation = {on:Settings.mailbox.vacationOn, message:Settings.mailbox.vacationMessage}; }, ()=>{
    const on = body.querySelector('[name="mb.vacationOn"]:checked').value==="true", message = body.querySelector('[data-key="mb.vacationMessage"]').value.trim();
    const from = body.querySelector('[data-key="mb.vacationFrom"]').value, until = body.querySelector('[data-key="mb.vacationUntil"]').value;
    if(on && !message) return "Write the message people will receive.";
    if(from && until && until<from) return "The last day must be on or after the first day.";
  });
}

/* ---------- Advanced ---------- */
function advanced(body){
  const ui = Settings.ui, list = ui.templateList||[];
  body.innerHTML = `<div class="st-card">
    ${row("Auto-advance", radio("ui.autoAdvanceOn",[[true,"Enable"],[false,"Disable"]])+`<div class="st-field"><label>After you archive, delete or mute a conversation, show</label>${select("ui.autoAdvance",[["next","the next (older) conversation"],["previous","the previous (newer) conversation"]],"Auto-advance direction")}</div>`, "Show the next conversation instead of your inbox after you archive or delete one.")}
    ${row("Templates", radio("ui.templates",[[true,"Enable"],[false,"Disable"]]), "Turn frequent messages into templates. Insert them from the Templates button in Compose.")}
    ${row("Unread message icon and badge", radio("ui.unreadBadge",[[true,"Enable"],[false,"Disable"]]), "Show how many unread messages are in your inbox on the browser tab and on the installed app's icon.")}
  </div>${saveBar()}
  <div class="st-card"><div class="st-cardhead"><h2>Your templates</h2><button class="btn sm primary" type="button" id="tp-new">New template</button></div>
    ${list.length ? `<div class="st-table">${list.map((t,i)=>`<div class="st-trow"><span class="st-ftext"><b>${esc(t.name)}</b><small>${esc((t.subject?t.subject+" — ":"")+(new DOMParser().parseFromString(t.body,"text/html").body.textContent||"").slice(0,90))}</small></span><span class="st-actions"><button class="btn sm ghost" type="button" data-tedit="${i}">Edit</button><button class="btn sm ghost danger" type="button" data-tdel="${i}">Delete</button></span></div>`).join("")}</div>` : `<p class="st-note">No templates yet. Create one here, or save a message as a template from Compose.</p>`}
  </div>`;
  bindSave(body, advanced);
  const saveList = async (next, message)=>{ try{ await Settings.save({ui:{templateList:next}}); App.toast(message); advanced(body); }catch(error){ App.toast(error.message); } };
  const edit = i=>{
    const t = i===null ? {name:"",subject:"",body:""} : list[i];
    App.dialog({title:i===null?"New template":"Edit template", wide:true, body:`<div class="st-field"><label for="tp-name">Name</label><input type="text" id="tp-name" value="${esc(t.name)}" maxlength="100"></div>
      <div class="st-field"><label for="tp-subj">Subject (optional)</label><input type="text" id="tp-subj" value="${esc(t.subject||"")}" maxlength="300"></div>
      <div class="st-field"><label id="tp-body-l">Message</label><div id="tp-body" class="sig-body tp-body" contenteditable="true" role="textbox" aria-multiline="true" aria-labelledby="tp-body-l">${t.body}</div></div>`,
      actions:[{label:"Cancel"},{label:"Save", primary:true, fn:()=>{
        const name=document.getElementById("tp-name").value.trim(); if(!name){ App.toast("Give the template a name."); return false; }
        const item={name, subject:document.getElementById("tp-subj").value.trim(), body:document.getElementById("tp-body").innerHTML};
        const next = list.filter((x,j)=>j!==i && x.name!==name); next.splice(i===null?next.length:Math.min(i,next.length),0,item);
        saveList(next, "Template saved.");
      }}]});
  };
  body.querySelector("#tp-new").addEventListener("click", ()=> edit(null));
  body.querySelectorAll("[data-tedit]").forEach(b=> b.addEventListener("click", ()=> edit(+b.dataset.tedit)));
  body.querySelectorAll("[data-tdel]").forEach(b=> b.addEventListener("click", ()=> App.confirm(`Delete the template "${list[+b.dataset.tdel].name}"?`, ()=> saveList(list.filter((_,j)=>j!==+b.dataset.tdel), "Template deleted."))));
}

/* ---------- Keyboard shortcuts ---------- */
function shortcuts(body){
  const rows = [["C","Compose"],["/","Search mail"],["J / K","Older / newer conversation"],["X","Select conversation"],["S","Star / unstar"],["E","Archive"],["#","Delete"],["R","Reply"],["F","Forward"],["?","Open this list"],["Esc","Close a dialog"]];
  body.innerHTML = `<div class="st-card"><p class="st-note">Keyboard shortcuts are <b>${Settings.mailbox.keyboardShortcuts===false?"off":"on"}</b>. Change this in <button type="button" class="st-link" id="sc-gen">General</button>.</p>
    ${rows.map(([k,d])=>`<div class="sc-row"><span>${d}</span><span class="kbd">${k}</span></div>`).join("")}</div>`;
  body.querySelector("#sc-gen").addEventListener("click", ()=> App.go("settings:general"));
}

/* ---------- block a sender from a message ---------- */
Views.blockSender = async function(address){
  address = String(address||"").trim().toLowerCase();
  if(!live() || !address) return;
  const state = await Live.request("filters");
  if(state.blocked.includes(address)){ App.toast(address+" is already blocked."); return; }
  await Live.request("filters", {filters:state.filters, blocked:[...state.blocked, address]});
  App.toast(`Blocked ${address}. New messages from them will go to Spam.`, {label:"Undo", fn:async ()=>{
    const now = await Live.request("filters"); await Live.request("filters", {filters:now.filters, blocked:now.blocked.filter(a=>a!==address)}); App.toast("Unblocked."); }});
};
})();
