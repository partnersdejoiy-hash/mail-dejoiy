/* ============ Dejoiy Mail — view-mail.js : folders, message list, tabs, reader ============ */
(function(){
"use strict";

Views.mail = function(el, folder){
  const ui = App.ui;
  document.documentElement.dataset.mailLayout=Store.state.prefs.messageLayout||'list';
  ui.folder = folder || ui.folder || "inbox";
  ui.sel = ui.sel || new Set();
  ui.tabs = ui.tabs || [];
  const list = Mail.list(ui.folder);
  const c = Mail.counts();

  const folderBtn = f => `
    <button class="nav-item ${ui.folder===f.id?"active":""}" data-folder="${f.id}">
      <span class="n-ico">${f.ico}</span>${f.name}
      ${c[f.id] ? `<span class="n-count">${c[f.id]}</span>` : ""}
    </button>`;

  el.innerHTML = `
  <div class="mail-heading"><div><div class="mail-title-line"><h1>${esc(Mail.folderName(ui.folder))}</h1><span class="folder-total">${list.length}</span></div><p class="mail-subtitle">A little clarity for your day.</p></div><div class="mail-controls"><label><span class="sr">Sort messages</span><select id="mail-sort" aria-label="Sort messages">${[['dateDesc','Newest first'],['dateAsc','Oldest first'],['sender','Sender A–Z'],['subject','Subject A–Z']].map(([v,n])=>`<option value="${v}" ${Store.state.prefs.mailSort===v?'selected':''}>${n}</option>`).join('')}</select></label><label><span class="sr">Reading pane</span><select id="mail-layout" aria-label="Reading pane">${[['list','List view'],['right','Split view']].map(([v,n])=>`<option value="${v}" ${document.documentElement.dataset.mailLayout===v?'selected':''}>${n}</option>`).join('')}</select></label></div></div>
  <div class="mail-filterbar" aria-label="Filter messages">${[['all','All messages'],['unread','Unread'],['starred','Starred'],['attachments','With attachments']].map(([key,label])=>`<button data-mail-filter="${key}" class="${(ui.quickFilter||'all')===key?'active':''}" aria-pressed="${(ui.quickFilter||'all')===key}">${label}</button>`).join('')}<span class="mail-filter-hint">Your day, in order.</span></div>
  <div class="mail-wrap">
    <div class="folder-col">
      ${Mail.FOLDERS.map(folderBtn).join("")}
      <div class="nav-sep">Smart views</div>
      ${Mail.SMART.map(folderBtn).join("")}
    </div>
    <div class="list-col">
      <div class="list-toolbar">
        <input type="checkbox" id="sel-all" aria-label="Select all" style="width:16px;height:16px;accent-color:var(--accent)">
        <button class="icon-btn sm" id="tb-refresh" title="Refresh">↻</button>
        <button class="icon-btn sm" id="tb-archive" title="Archive (E)">🗄️</button>
        <button class="icon-btn sm" id="tb-spam" title="Report spam">🚫</button>
        <button class="icon-btn sm" id="tb-trash" title="Delete (#)">🗑️</button>
        <button class="icon-btn sm" id="tb-read" title="Mark read/unread">✉️</button>
        <button class="icon-btn sm" id="tb-label" title="Label">🏷️</button>
        <span id="selection-status" class="selection-status"></span>
      </div>
      <div class="msg-list" id="msg-list"></div>
    </div>
    <div class="reader-col">
      <div class="msg-tabs" id="msg-tabs"></div>
      <div class="r-toolbar" id="reader-bar" style="display:none"></div>
      <div class="reader" id="reader"></div>
    </div>
  </div>`;

  el.querySelector('#mail-sort').addEventListener('change',event=>{Store.state.prefs.mailSort=event.target.value;Store.save();renderList();});
  el.querySelector('#mail-layout').addEventListener('change',event=>{Store.state.prefs.messageLayout=event.target.value;Store.save();document.documentElement.dataset.mailLayout=event.target.value;});
  const toolbarIcons={'tb-refresh':'refresh','tb-archive':'archive','tb-spam':'spam','tb-trash':'trash','tb-read':'unread','tb-label':'tag'};
  for(const [id,icon] of Object.entries(toolbarIcons)){const button=el.querySelector('#'+id);button.innerHTML=Icons.get(icon)+(id==='tb-refresh'?'':`<span>${({archive:'Archive',spam:'Spam',trash:'Delete',unread:'Read',tag:'Label'})[icon]}</span>`);button.setAttribute('aria-label',button.title);}
  el.querySelectorAll('[data-mail-filter]').forEach(button=>button.addEventListener('click',()=>{
    ui.quickFilter=button.dataset.mailFilter;ui.sel.clear();renderList();
    el.querySelectorAll('[data-mail-filter]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));});
  }));
  const visibleItems=()=>Mail.threadList(ui.folder).filter(e=>ui.quickFilter==='unread'?e.unreadCount>0:ui.quickFilter==='starred'?e.messages.some(m=>m.starred):ui.quickFilter==='attachments'?e.hasAttachment:true);
  const updateSelection=()=>{
    const items=visibleItems(),visible=new Set(items.map(e=>e.id));for(const id of ui.sel)if(!visible.has(id))ui.sel.delete(id);
    const n=items.filter(e=>ui.sel.has(e.id)).length,checkbox=el.querySelector('#sel-all');
    checkbox.checked=items.length>0&&n===items.length;checkbox.indeterminate=n>0&&n<items.length;
    el.querySelector('#selection-status').textContent=n?`${n} selected`:`${items.length} messages`;
    el.querySelectorAll('#tb-archive,#tb-spam,#tb-trash,#tb-read,#tb-label').forEach(b=>b.disabled=!n);
  };
  /* ---- folder nav ---- */
  el.querySelectorAll("[data-folder]").forEach(b=> b.addEventListener("click", async ()=>{
    ui.folder = b.dataset.folder; ui.sel.clear(); ui.activeTab = null;
    document.body.classList.remove("reader-open"); Views.mail(el, ui.folder); App.refreshNav();
  }));

  /* ---- message list ---- */
  const listEl = el.querySelector("#msg-list");
  const renderList = ()=>{
    const items = visibleItems();
    let previousGroup="";
    listEl.innerHTML = items.length ? items.map(e=>{
      const date=new Date(e.date),now=new Date(),yesterday=new Date();yesterday.setDate(now.getDate()-1);
      const group=date.toDateString()===now.toDateString()?'Today':date.toDateString()===yesterday.toDateString()?'Yesterday':date.toLocaleDateString([],{month:'long',year:'numeric'});
      const grouped=!['sender','subject'].includes(Store.state.prefs.mailSort)&&group!==previousGroup;
      previousGroup=group;
      return `${grouped?`<div class="message-group">${esc(group)}</div>`:''}
      <div class="msg-row ${e.read?"":"unread"} ${ui.activeTab===e.latest.id||ui.sel.has(e.id)?"selected":""}" data-id="${e.id}" data-latest-id="${e.latest.id}" role="button" tabindex="0">
        <input type="checkbox" class="m-check" data-check="${e.id}" ${ui.sel.has(e.id)?"checked":""} aria-label="Select message">
        <button class="star ${e.starred?"on":""}" data-star="${e.id}" aria-label="${e.starred?'Unstar message':'Star message'}" aria-pressed="${!!e.starred}">${Icons.get("star")}</button>
        <div class="m-main">
          <div class="m-top"><span class="m-from">${esc(e.from.name)}</span>
            <span class="m-flags">${e.important?Icons.get("important"):""}${e.hasAttachment?Icons.get("paperclip"):""}</span>
            <span class="m-date">${fmtDate(e.date)}</span></div>
          <div class="m-subj">${esc(e.subject)}</div>
          <div class="m-snip">${esc(strip(e.body)).slice(0,90)}</div>
          ${(e.labels||[]).map(l=>`<span class="lbl">${esc(l)}</span>`).join(" ")}
        </div>
      </div>`;}).join("")
      : `<div class="empty-note mailbox-empty"><span class="empty-icon">${Icons.get(ui.search?'search':'inbox')}</span><h2>${ui.search?'No matching messages':'A little breathing room.'}</h2><p>${ui.search?'Try a different name or keyword.':ui.quickFilter&&ui.quickFilter!=='all'?'No messages match this view.':ui.folder==='inbox'?"You're all caught up. New messages will appear here.":'No messages in this folder.'}</p><button class="btn" id="empty-action">${ui.search?'Clear search':'Write a message'}</button></div>`;
    const emptyAction=el.querySelector('#empty-action');if(emptyAction)emptyAction.addEventListener('click',()=>{if(ui.search){ui.search='';document.getElementById('global-search').value='';renderList();}else App.go('compose:new');});
    updateSelection();
    bindRows();
  };
  const bindRows = ()=>{
    listEl.querySelectorAll("[data-check]").forEach(cb=> cb.addEventListener("click", async ev=>{
      ev.stopPropagation();
      cb.checked ? ui.sel.add(cb.dataset.check) : ui.sel.delete(cb.dataset.check);
      cb.closest(".msg-row").classList.toggle("selected",cb.checked);updateSelection();
    }));
    listEl.querySelectorAll("[data-star]").forEach(st=> st.addEventListener("click", async ev=>{
      ev.stopPropagation(); const thread=Mail.getThread(st.dataset.star);const target=!(thread?.starred);await Promise.all((thread?.ids||[st.dataset.star]).map(id=>{const message=Mail.get(id);if(Boolean(message?.starred)!==target)return Mail.toggleStar(id);}));renderList();App.refreshNav();
    }));
    listEl.querySelectorAll(".msg-row").forEach(row=> {
      const open = ()=> ui.folder==="drafts"?App.go("compose:draft:"+row.dataset.id):openTab(row.dataset.id);
      row.addEventListener("click", async ev=>{ if(ev.target.closest("input,button")) return; open(); });
      row.addEventListener("keydown", async ev=>{ if(ev.target===row&&(ev.key==="Enter"||ev.key===" ")){ev.preventDefault();open();} });
    });
  };
  renderList();

  /* ---- toolbar ---- */
  const selIds = ()=> [...new Set([...ui.sel].flatMap(threadId=>visibleItems().find(thread=>thread.id===threadId)?.ids||[threadId]))];
  const needSel = ()=>{ if(!selIds().length){ App.toast("Select at least one message first."); return false; } return true; };
  el.querySelector("#sel-all").addEventListener("change", async ev=>{
    ui.sel.clear();
    if(ev.target.checked) visibleItems().forEach(e=>ui.sel.add(e.id));
    renderList();
  });
  el.querySelector("#tb-refresh").addEventListener("click", async ()=>{ const em = await Mail.checkMail(); renderList(); App.refreshNav();
    App.toast(em.folder==="inbox" ? "New mail: "+em.subject : "New mail filtered."); });
  el.querySelector("#tb-archive").addEventListener("click", async ()=>{ if(!needSel())return; await Mail.archive(selIds()); ui.sel.clear(); renderList(); App.refreshNav(); App.toast("Archived."); });
  el.querySelector("#tb-spam").addEventListener("click", async ()=>{ if(!needSel())return; await Mail.spam(selIds()); ui.sel.clear(); renderList(); App.refreshNav(); App.toast("Reported as spam."); });
  el.querySelector("#tb-trash").addEventListener("click", async ()=>{ if(!needSel())return; await Mail.trash(selIds()); ui.sel.clear(); renderList(); App.refreshNav(); App.toast("Moved to Trash."); });
  el.querySelector("#tb-read").addEventListener("click", async ()=>{ if(!needSel())return;
    const messageIds=selIds().flatMap(threadId=>Mail.getThread(threadId)?.ids||[threadId]);
    const anyUnread=messageIds.some(id=>!Mail.get(id)?.read);
    await Promise.all(messageIds.map(id=>Mail.setRead(id, anyUnread))); ui.sel.clear(); renderList(); App.refreshNav(); });
  el.querySelector("#tb-label").addEventListener("click", async ev=>{
    if(!needSel())return;
    App.menu(ev.currentTarget, ["work","personal","finance","design"].map(l=>({label:"🏷️ "+l, fn:async ()=>{
      await Mail.addLabel(selIds(), l); ui.sel.clear(); renderList(); App.toast("Labelled "+l+"."); }})));
  });

  /* ---- tabs + reader ---- */
  const tabsEl = el.querySelector("#msg-tabs"), readerEl = el.querySelector("#reader"), barEl = el.querySelector("#reader-bar");
  async function openTab(id){
    if(!Store.state.prefs.messageTabs) ui.tabs=[];
    if(!ui.tabs.includes(id)) ui.tabs.push(id);
    ui.activeTab = id;
    const thread=Mail.getThread(Mail.get(id)?.conversationId||id);
    await Mail.setRead(thread?.ids||[id], true);
    renderTabs(); renderReader(); renderList(); App.refreshNav();
    document.body.classList.add("reader-open");
  }
  function closeTab(id){
    ui.tabs = ui.tabs.filter(t=>t!==id);
    if(ui.activeTab===id) ui.activeTab = ui.tabs[ui.tabs.length-1] || null;
    renderTabs(); renderReader(); renderList();
    if(!ui.activeTab) document.body.classList.remove("reader-open");
  }
  function renderTabs(){
    tabsEl.innerHTML = ui.tabs.map(id=>{ const e = Mail.getThread(Mail.get(id)?.conversationId||id); if(!e) return "";
      return `<div class="msg-tab ${ui.activeTab===id?"active":""}" data-tab="${id}">
        <span style="overflow:hidden;text-overflow:ellipsis">${esc(e.subject)}${e.count>1?` · ${e.count}`:""}</span>
        <button class="t-x" data-xtab="${id}" aria-label="Close tab">×</button></div>`; }).join("");
    tabsEl.querySelectorAll("[data-tab]").forEach(t=> t.addEventListener("click", async ev=>{
      if(ev.target.closest("[data-xtab]")) return;
      ui.activeTab = t.dataset.tab; const thread=Mail.getThread(Mail.get(ui.activeTab)?.conversationId||ui.activeTab); await Mail.setRead(thread?.ids||[ui.activeTab], true); renderTabs(); renderReader(); renderList();
    }));
    tabsEl.querySelectorAll("[data-xtab]").forEach(x=> x.addEventListener("click", async ev=>{ ev.stopPropagation(); closeTab(x.dataset.xtab); }));
  }
  function renderReader(){
    const id = ui.activeTab, anchor = id && Mail.get(id), thread = id && Mail.getThread(anchor?.conversationId||id), e = thread?.latest||anchor;
    if(!e){ barEl.style.display="none"; readerEl.innerHTML = `<div class="reader-empty"><span class="empty-icon">${Icons.get("mail")}</span><h2>A space to focus.</h2><p>Select a conversation to settle in.</p></div>`; return; }
    barEl.style.display = "flex";
    barEl.innerHTML = `
      <button class="icon-btn sm reader-back" id="r-back" title="Back to messages">←</button>
      <button class="icon-btn sm" id="r-reply" title="Reply (R)">↩</button>
      <button class="icon-btn sm" id="r-replyall" title="Reply all">↩↩</button>
      <button class="icon-btn sm" id="r-fwd" title="Forward (F)">↪</button>
      <button class="icon-btn sm" id="r-archive" title="Archive (E)">🗄️</button>
      <button class="icon-btn sm" id="r-spam" title="Spam">🚫</button>
      <button class="icon-btn sm" id="r-trash" title="Delete (#)">🗑️</button>
      <button class="icon-btn sm star ${e.starred?"on":""}" id="r-star" title="Star (S)">★</button>
      <button class="icon-btn sm" id="r-unread" title="Mark unread">✉️</button>
      <button class="icon-btn sm" id="r-print" title="Print">🖨️</button>`;
    const readerIcons={'r-back':'back','r-reply':'reply','r-replyall':'replyall','r-fwd':'forward','r-archive':'archive','r-spam':'spam','r-trash':'trash','r-star':'star','r-unread':'unread','r-print':'print'};
    for(const [buttonId,icon] of Object.entries(readerIcons)){const button=barEl.querySelector('#'+buttonId);button.innerHTML=Icons.get(icon);button.setAttribute('aria-label',button.title);}
    readerEl.innerHTML = `
      <div class="r-subject">${esc(e.subject)}${thread?.count>1?` <span class="thread-count">${thread.count} messages</span>`:""}</div>
      <div class="thread-messages">${(thread?.messages||[e]).map(message=>`<article class="thread-message">
        <div class="r-meta"><div class="r-avatar">${initials(message.from.name)}</div>
          <div class="thread-sender"><div><b>${esc(message.from.name)}</b> <span style="color:var(--ink-2)">&lt;${esc(message.from.email)}&gt;</span></div>
          <div class="thread-recipient">to ${(message.to||[]).map(esc).join(", ")} · ${fmtDate(message.date)}</div></div>
          <div class="thread-labels">${(message.labels||[]).map(l=>`<span class="lbl">${esc(l)}</span>`).join(" ")}</div>
        </div>
        ${(message.attachments||[]).length ? `<div class="thread-attachments">${message.attachments.map(a=>window.Live?.enabled && a.mid && a.part?`<a class="attach-chip" href="/api/attachment?mid=${encodeURIComponent(a.mid)}&amp;part=${encodeURIComponent(a.part)}&amp;name=${encodeURIComponent(a.name)}" download>📎 ${esc(a.name)} <span style="color:var(--ink-3)">${esc(a.size)} bytes</span></a>`:`<span class="attach-chip">📎 ${esc(a.name)} <span style="color:var(--ink-3)">${esc(a.size)}</span></span>`).join("")}</div>`:""}
        <div class="r-body">${message.body}</div>
      </article>`).join("")}</div>`;
    const b = id2 => barEl.querySelector("#"+id2);
    const back = b("r-back"); if(back) back.addEventListener("click", ()=> document.body.classList.remove("reader-open"));
    b("r-reply").addEventListener("click", ()=> App.go("compose:reply:"+e.id));
    b("r-replyall").addEventListener("click", ()=> App.go("compose:replyall:"+e.id));
    b("r-fwd").addEventListener("click", ()=> App.go("compose:forward:"+e.id));
    b("r-archive").addEventListener("click", async ()=>{ await Mail.archive(thread?.ids||[id]); closeTab(id); renderList(); App.refreshNav(); App.toast("Archived."); });
    b("r-spam").addEventListener("click", async ()=>{ await Mail.spam(thread?.ids||[id]); closeTab(id); renderList(); App.refreshNav(); App.toast("Reported as spam."); });
    b("r-trash").addEventListener("click", async ()=>{ await Mail.trash(thread?.ids||[id]); closeTab(id); renderList(); App.refreshNav(); App.toast("Moved to Trash."); });
    b("r-star").addEventListener("click", async ()=>{ await Promise.all((thread?.ids||[id]).map(messageId=>Mail.toggleStar(messageId))); renderReader(); renderList(); App.refreshNav(); });
    b("r-unread").addEventListener("click", async ()=>{ await Mail.setRead(thread?.ids||[id], false); closeTab(id); renderList(); App.refreshNav(); });
    b("r-print").addEventListener("click", ()=> window.print());
  }
  renderTabs(); renderReader();
  if(ui.activeTab && Mail.get(ui.activeTab))document.body.classList.add("reader-open");

  /* expose for keyboard shortcuts */
  ui._mail = { openTab, closeTab, renderList,
    moveSel(d){ const rows=[...listEl.querySelectorAll(".msg-row")]; if(!rows.length)return;
      let i = rows.findIndex(r=>r.dataset.latestId===ui.activeTab);
      i = Math.max(0, Math.min(rows.length-1, (i<0?0:i)+d));
      openTab(rows[i].dataset.latestId); rows[i].scrollIntoView({block:"nearest"}); } };
};

function strip(h){ const d=document.createElement("div"); d.innerHTML=h||""; return d.textContent||""; }
})();
