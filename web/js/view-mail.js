/* ============ Dejoiy Mail — view-mail.js : folders, message list, tabs, reader ============ */
(function(){
"use strict";

/* Phones, and tablets used by touch, get the Gmail-app behaviours: tap an avatar or long-press to
   select, swipe to archive, pull to refresh. */
const compact = ()=> !!window.matchMedia?.("(max-width:680px), (max-width:1199px) and (pointer:coarse)").matches;

Views.mail = function(el, folder){
  const ui = App.ui;
  document.documentElement.dataset.mailLayout=Store.state.prefs.messageLayout||'list';
  if(folder && folder!==ui.folder) ui.page = 0;
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
  <div class="mail-heading"><div><div class="mail-title-line"><h1>${esc(Mail.folderName(ui.folder))}</h1><span class="folder-total">${list.length}</span></div><p class="mail-subtitle">A little clarity for your day.</p></div><div class="mail-controls"><label><span class="sr">Sort messages</span><select id="mail-sort" aria-label="Sort messages">${[['dateDesc','Newest first'],['dateAsc','Oldest first'],['sender','Sender A–Z'],['subject','Subject A–Z']].map(([v,n])=>`<option value="${v}" ${Store.state.prefs.mailSort===v?'selected':''}>${n}</option>`).join('')}</select></label><label><span class="sr">Reading pane</span><select id="mail-layout" aria-label="Reading pane">${[['list','No split'],['right','Right of inbox'],['bottom','Below inbox']].map(([v,n])=>`<option value="${v}" ${document.documentElement.dataset.mailLayout===v?'selected':''}>${n}</option>`).join('')}</select></label></div></div>
  <div class="mail-filterbar" aria-label="Filter messages">${[['all','All messages'],['unread','Unread'],['starred','Starred'],['attachments','With attachments']].map(([key,label])=>`<button data-mail-filter="${key}" class="${(ui.quickFilter||'all')===key?'active':''}" aria-pressed="${(ui.quickFilter||'all')===key}">${label}</button>`).join('')}<span class="mail-filter-hint">Your day, in order.</span></div>
  <div class="mail-wrap">
    <div class="folder-col">
      ${Mail.FOLDERS.map(folderBtn).join("")}
      <div class="nav-sep">Smart views</div>
      ${Mail.SMART.map(folderBtn).join("")}
    </div>
    <div class="list-col">
      <div class="list-toolbar">
        <button class="icon-btn sm" id="tb-clear" title="Clear selection"></button>
        <input type="checkbox" id="sel-all" aria-label="Select all" style="width:16px;height:16px;accent-color:var(--accent)">
        <button class="icon-btn sm" id="tb-refresh" title="Refresh">↻</button>
        <button class="icon-btn sm" id="tb-archive" title="Archive (E)">🗄️</button>
        <button class="icon-btn sm" id="tb-spam" title="Report spam">🚫</button>
        <button class="icon-btn sm" id="tb-trash" title="Delete (#)">🗑️</button>
        <button class="icon-btn sm" id="tb-read" title="Mark read/unread">✉️</button>
        <button class="icon-btn sm" id="tb-label" title="Label">🏷️</button>
        <span id="selection-status" class="selection-status"></span>
      </div>
      <div class="ptr" id="ptr" aria-hidden="true"></div>
      <div class="msg-list" id="msg-list"></div>
    </div>
    <div class="reader-col">
      <div class="msg-tabs" id="msg-tabs"></div>
      <div class="r-toolbar" id="reader-bar" style="display:none"></div>
      <div class="reader" id="reader"></div>
    </div>
  </div>`;

  el.querySelector('#mail-sort').addEventListener('change',event=>{Store.state.prefs.mailSort=event.target.value;Store.save();renderList();});
  el.querySelector('#mail-layout').addEventListener('change',event=>{const value=event.target.value;document.documentElement.dataset.mailLayout=value;Store.state.prefs.messageLayout=value;Store.save();
    Settings.save({ui:{readingPane:value==='list'?'off':value}}).catch(error=>App.toast(error.message));});
  const toolbarIcons={'tb-refresh':'refresh','tb-archive':'archive','tb-spam':'spam','tb-trash':'trash','tb-read':'unread','tb-label':'tag'};
  for(const [id,icon] of Object.entries(toolbarIcons)){const button=el.querySelector('#'+id);button.innerHTML=Icons.get(icon)+(id==='tb-refresh'?'':`<span>${({archive:'Archive',spam:'Spam',trash:'Delete',unread:'Read',tag:'Label'})[icon]}</span>`);button.setAttribute('aria-label',button.title);}
  el.querySelector('#tb-clear').innerHTML=Icons.get('close');el.querySelector('#tb-clear').setAttribute('aria-label','Clear selection');
  el.querySelector('#ptr').innerHTML=Icons.get('refresh');
  el.querySelectorAll('[data-mail-filter]').forEach(button=>button.addEventListener('click',()=>{
    ui.quickFilter=button.dataset.mailFilter;ui.sel.clear();ui.page=0;renderList();
    el.querySelectorAll('[data-mail-filter]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));});
  }));
  /* Inbox type (Settings → Inbox) brings unread, starred or important conversations to the top. */
  const rank=e=>{const type=Settings.ui.inboxType;return ui.folder!=='inbox'||type==='default'?0:type==='unread'?(e.unreadCount>0?0:1):type==='starred'?(e.messages.some(m=>m.starred)?0:1):(e.important?0:1);};
  const visibleItems=()=>Mail.threadList(ui.folder).filter(e=>ui.quickFilter==='unread'?e.unreadCount>0:ui.quickFilter==='starred'?e.messages.some(m=>m.starred):ui.quickFilter==='attachments'?e.hasAttachment:true)
    .map((e,i)=>[rank(e),i,e]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]).map(x=>x[2]);
  ui.page=ui.page||0;
  const pageItems=()=>{const all=visibleItems(),size=Settings.pageSize(),pages=Math.max(1,Math.ceil(all.length/size));ui.page=Math.min(ui.page,pages-1);return {all,items:all.slice(ui.page*size,(ui.page+1)*size),pages,size};};
  const updateSelection=()=>{
    const items=visibleItems(),visible=new Set(items.map(e=>e.id));for(const id of ui.sel)if(!visible.has(id))ui.sel.delete(id);
    const n=items.filter(e=>ui.sel.has(e.id)).length,checkbox=el.querySelector('#sel-all'),pg=pageItems();
    const onPage=pg.items.filter(e=>ui.sel.has(e.id)).length;checkbox.checked=pg.items.length>0&&onPage===pg.items.length;checkbox.indeterminate=onPage>0&&onPage<pg.items.length;
    el.querySelector('#selection-status').textContent=n?`${n} selected`:items.length>pg.size?`${ui.page*pg.size+1}–${ui.page*pg.size+pg.items.length} of ${items.length}`:`${items.length} messages`;
    el.querySelectorAll('#tb-archive,#tb-spam,#tb-trash,#tb-read,#tb-label').forEach(b=>b.disabled=!n);
    document.body.classList.toggle('selecting',n>0);
  };
  /* ---- folder nav ---- */
  el.querySelectorAll("[data-folder]").forEach(b=> b.addEventListener("click", async ()=>{
    ui.folder = b.dataset.folder; ui.sel.clear(); ui.activeTab = null; ui.page = 0;
    document.body.classList.remove("reader-open"); Views.mail(el, ui.folder); App.refreshNav();
  }));

  /* ---- message list ---- */
  const listEl = el.querySelector("#msg-list");
  const renderList = ()=>{
    const {all, items, pages} = pageItems();
    const me=(Store.state.user.email||"").toLowerCase(), showIndicators=Settings.ui.indicators && !['sent','drafts'].includes(ui.folder);
    const indicator=e=>{ if(!showIndicators) return ""; const m=e.latest, to=(m.to||[]).map(a=>a.toLowerCase()), cc=(m.cc||[]);
      return to.includes(me) ? `<span class="m-ind" title="${to.length===1&&!cc.length?'Sent only to you':'Sent to you'}">${to.length===1&&!cc.length?'»':'›'}</span>` : `<span class="m-ind"></span>`; };
    const hover=Settings.ui.hoverActions && !compact();
    let previousGroup="";
    listEl.innerHTML = items.length ? items.map(e=>{
      const date=new Date(e.date),now=new Date(),yesterday=new Date();yesterday.setDate(now.getDate()-1);
      const group=date.toDateString()===now.toDateString()?'Today':date.toDateString()===yesterday.toDateString()?'Yesterday':date.toLocaleDateString([],{month:'long',year:'numeric'});
      const grouped=!['sender','subject'].includes(Store.state.prefs.mailSort)&&group!==previousGroup;
      previousGroup=group;
      return `${grouped?`<div class="message-group">${esc(group)}</div>`:''}
      <div class="msg-row ${e.read?"":"unread"} ${ui.activeTab===e.latest.id||ui.sel.has(e.id)?"selected":""}" data-id="${e.id}" data-latest-id="${e.latest.id}" role="button" tabindex="0">
        ${Profile.avatar(e.latest.from?.email, e.latest.from?.name, "m-avatar")}
        <input type="checkbox" class="m-check" data-check="${e.id}" ${ui.sel.has(e.id)?"checked":""} aria-label="Select message">
        <button class="star ${e.starred?"on":""}" data-star="${e.id}" aria-label="${e.starred?'Unstar message':'Star message'}" aria-pressed="${!!e.starred}">${Icons.get("star")}</button>
        <div class="m-main">
          <div class="m-top">${indicator(e)}<span class="m-from">${esc(listName(e))}${e.messages.length>1?` <span class="m-count">${e.messages.length}</span>`:""}</span>
            <span class="m-flags">${e.important?Icons.get("important"):""}${e.hasAttachment?Icons.get("paperclip"):""}</span>
            <span class="m-date">${fmtDate(e.date)}</span>${hover?`<span class="m-hover"><button data-hact="archive" title="Archive" aria-label="Archive">${Icons.get("archive")}</button><button data-hact="trash" title="Delete" aria-label="Delete">${Icons.get("trash")}</button><button data-hact="read" title="${e.read?'Mark as unread':'Mark as read'}" aria-label="${e.read?'Mark as unread':'Mark as read'}">${Icons.get("unread")}</button></span>`:""}</div>
          <div class="m-subj">${esc(e.subject)}</div>
          <div class="m-snip">${esc(strip(e.latest.body)).slice(0,90)}</div>
          ${(e.labels||[]).length?`<span class="m-labels">${e.labels.map(l=>`<span class="lbl">${esc(l)}</span>`).join(" ")}</span>`:""}
        </div>
      </div>`;}).join("") + (pages>1||(window.Live&&Live.enabled&&Live.more&&ui.page===pages-1)?`<div class="list-pager"><button class="btn sm" id="pg-prev" ${ui.page?"":"disabled"}>${Icons.get("back")} Newer</button><span>${ui.page*Settings.pageSize()+1}–${ui.page*Settings.pageSize()+items.length} of ${all.length}${window.Live&&Live.enabled&&Live.more?"+":""}</span><button class="btn sm" id="pg-next" ${ui.page<pages-1||(window.Live&&Live.enabled&&Live.more)?"":"disabled"}>Older ${Icons.get("forward")}</button></div>`:"")
      : `<div class="empty-note mailbox-empty"><span class="empty-icon">${Icons.get(ui.search?'search':'inbox')}</span><h2>${ui.search?'No matching messages':'A little breathing room.'}</h2><p>${ui.search?'Try a different name or keyword.':ui.quickFilter&&ui.quickFilter!=='all'?'No messages match this view.':ui.folder==='inbox'?"You're all caught up. New messages will appear here.":'No messages in this folder.'}</p><button class="btn" id="empty-action">${ui.search?'Clear search':'Write a message'}</button></div>`;
    const prev=el.querySelector('#pg-prev'),next=el.querySelector('#pg-next');
    if(prev) prev.addEventListener('click',()=>{ui.page=Math.max(0,ui.page-1);renderList();listEl.scrollTop=0;});
    if(next) next.addEventListener('click',async ()=>{
      if(ui.page<pages-1){ui.page++;renderList();listEl.scrollTop=0;return;}
      next.disabled=true;try{await Live.sync(Live.nextOffset);App.refreshNav();ui.page++;renderList();listEl.scrollTop=0;}catch(error){App.toast(error.message);next.disabled=false;}
    });
    const emptyAction=el.querySelector('#empty-action');if(emptyAction)emptyAction.addEventListener('click',()=>{if(ui.search){ui.search='';document.getElementById('global-search').value='';renderList();}else App.go('compose:new');});
    updateSelection();
    bindRows();
  };
  const toggleSel = row=>{
    const id=row.dataset.id, on=!ui.sel.has(id);
    on ? ui.sel.add(id) : ui.sel.delete(id);
    row.classList.toggle("selected",on); const cb=row.querySelector("[data-check]"); if(cb) cb.checked=on;
    updateSelection();
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
    listEl.querySelectorAll("[data-hact]").forEach(button=> button.addEventListener("click", async ev=>{
      ev.stopPropagation(); const row=button.closest(".msg-row"), thread=visibleItems().find(t=>t.id===row.dataset.id); if(!thread) return;
      try{
        if(button.dataset.hact==="archive"){ await Mail.archive(thread.ids); App.toast("Archived.",{label:"Undo",fn:async ()=>{ await Mail.moveTo(thread.ids,ui.folder); renderList(); App.refreshNav(); }}); }
        else if(button.dataset.hact==="trash"){ await Mail.trash(thread.ids); App.toast("Moved to Trash.",{label:"Undo",fn:async ()=>{ await Mail.moveTo(thread.ids,ui.folder); renderList(); App.refreshNav(); }}); }
        else await Mail.setRead(thread.messages.map(m=>m.id), !thread.read);
      }catch(error){ App.toast(error.message); }
      renderList(); App.refreshNav();
    }));
    listEl.querySelectorAll(".msg-row").forEach(row=> {
      const open = ()=> ui.folder==="drafts"?App.go("compose:draft:"+row.dataset.id):openTab(row.dataset.latestId);
      row.querySelector(".m-avatar").addEventListener("click", ev=>{ ev.stopPropagation(); toggleSel(row); });
      row.addEventListener("click", async ev=>{
        if(ev.target.closest("input,button")) return;
        if(row.dataset.held){ delete row.dataset.held; return; }
        if(compact() && ui.sel.size){ toggleSel(row); return; }
        open();
      });
      row.addEventListener("keydown", async ev=>{ if(ev.target===row&&(ev.key==="Enter"||ev.key===" ")){ev.preventDefault();open();} });
      bindHold(row); if(ui.folder==="inbox") bindSwipe(row);
    });
  };
  /* Long-press selects, like the Gmail app. */
  const bindHold = row=>{
    let timer=null, start=null;
    const cancel=()=>{ clearTimeout(timer); timer=null; };
    row.addEventListener("pointerdown", ev=>{ if(ev.pointerType!=="touch") return; start=[ev.clientX,ev.clientY];
      timer=setTimeout(()=>{ timer=null; row.dataset.held="1"; navigator.vibrate?.(15); toggleSel(row); },480); });
    row.addEventListener("pointermove", ev=>{ if(timer && Math.hypot(ev.clientX-start[0],ev.clientY-start[1])>10) cancel(); });
    for(const type of ["pointerup","pointercancel","pointerleave"]) row.addEventListener(type, cancel);
    row.addEventListener("contextmenu", ev=>{ if(compact()) ev.preventDefault(); });
  };
  /* Swipe a conversation sideways to archive it; Undo puts it back. */
  const bindSwipe = row=>{
    let x0=0, y0=0, dx=0, state="";
    row.addEventListener("touchstart", ev=>{ if(ev.touches.length!==1||ui.sel.size){ state=""; return; } x0=ev.touches[0].clientX; y0=ev.touches[0].clientY; dx=0; state="maybe"; },{passive:true});
    row.addEventListener("touchmove", ev=>{
      if(!state) return;
      const mx=ev.touches[0].clientX-x0, my=ev.touches[0].clientY-y0;
      if(state==="maybe"){ if(Math.abs(mx)<12&&Math.abs(my)<12) return; if(Math.abs(my)>=Math.abs(mx)){ state=""; return; } state="swipe"; row.classList.add("swiping"); }
      dx=mx; row.style.setProperty("--dx",dx+"px"); row.dataset.swipe=dx>0?"right":"left";
    },{passive:true});
    const end=async ()=>{
      if(state!=="swipe"){ state=""; return; }
      state=""; row.dataset.held="1"; setTimeout(()=>delete row.dataset.held,350);
      if(Math.abs(dx)<row.offsetWidth*.35){ row.classList.remove("swiping"); row.style.removeProperty("--dx"); return; }
      row.classList.add("swiped"); row.style.setProperty("--dx",(dx>0?1:-1)*row.offsetWidth+"px");
      const ids=visibleItems().find(t=>t.id===row.dataset.id)?.ids||[];
      try{ await Mail.archive(ids); }catch(error){ App.toast(error.message); }
      renderList(); App.refreshNav();
      App.toast("Archived.",{label:"Undo",fn:async ()=>{ await Mail.moveTo(ids,"inbox"); renderList(); App.refreshNav(); }});
    };
    row.addEventListener("touchend", end); row.addEventListener("touchcancel", end);
  };
  renderList();

  /* ---- toolbar ---- */
  const selIds = ()=> [...new Set([...ui.sel].flatMap(threadId=>visibleItems().find(thread=>thread.id===threadId)?.ids||[threadId]))];
  const needSel = ()=>{ if(!selIds().length){ App.toast("Select at least one message first."); return false; } return true; };
  const refresh = async ()=>{ const em = await Mail.checkMail(); renderList(); App.refreshNav();
    App.toast(em.folder==="inbox" ? "New mail: "+em.subject : "New mail filtered."); };
  el.querySelector("#sel-all").addEventListener("change", async ev=>{
    ui.sel.clear();
    if(ev.target.checked) pageItems().items.forEach(e=>ui.sel.add(e.id));
    renderList();
  });
  el.querySelector("#tb-clear").addEventListener("click", ()=>{ ui.sel.clear(); renderList(); });
  el.querySelector("#tb-refresh").addEventListener("click", refresh);
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

  /* Pull down at the top of the list to check for new mail; the Compose button shrinks while scrolling down. */
  const ptr=el.querySelector("#ptr"); let pull=null, lastTop=0;
  listEl.addEventListener("touchstart", ev=>{ pull = listEl.scrollTop<=0 && ev.touches.length===1 && compact() ? {y:ev.touches[0].clientY,dy:0} : null; },{passive:true});
  listEl.addEventListener("touchmove", ev=>{ if(!pull) return; pull.dy=ev.touches[0].clientY-pull.y;
    ptr.classList.toggle("show",pull.dy>8); ptr.classList.toggle("ready",pull.dy>70); ptr.style.setProperty("--pull",Math.max(0,Math.min(pull.dy,90))+"px"); },{passive:true});
  listEl.addEventListener("touchend", async ()=>{ if(!pull) return; const go=pull.dy>70; pull=null; ptr.style.removeProperty("--pull");
    if(go){ ptr.classList.add("busy"); try{ await refresh(); }catch(error){ App.toast(error.message); } }
    ptr.classList.remove("show","ready","busy"); });
  listEl.addEventListener("scroll", ()=>{ const top=listEl.scrollTop; if(Math.abs(top-lastTop)>6){ document.body.classList.toggle("fab-mini", top>lastTop && top>40); lastTop=top; } },{passive:true});

  /* ---- tabs + reader ---- */
  const tabsEl = el.querySelector("#msg-tabs"), readerEl = el.querySelector("#reader"), barEl = el.querySelector("#reader-bar");
  /* Messages that were unread when the conversation opened stay expanded, like Gmail. */
  async function markThreadRead(id){
    const thread=Mail.getThread(Mail.threadId(id));
    ui.fresh=new Set((thread?.messages||[]).filter(m=>!m.read).map(m=>m.id)); ui.unfolded=false;
    await Mail.setRead(thread?.ids||[id], true);
  }
  async function openTab(id){
    if(!Store.state.prefs.messageTabs) ui.tabs=[];
    if(!ui.tabs.includes(id)) ui.tabs.push(id);
    ui.activeTab = id;
    await markThreadRead(id);
    renderTabs(); renderReader(); renderList(); App.refreshNav();
    document.body.classList.add("reader-open");
    if(compact() && !(history.state&&history.state.dmailReader)) history.pushState({dmailReader:true}, "");
  }
  /* Leaving the conversation forgets it, so a later re-render (for example after the server
     confirms "mark as read") does not pop it open again. */
  function closeReader(){
    ui.tabs=[]; ui.activeTab=null; document.body.classList.remove("reader-open");
    renderTabs(); renderReader(); renderList();
  }
  function closeTab(id){
    ui.tabs = ui.tabs.filter(t=>t!==id);
    if(ui.activeTab===id) ui.activeTab = ui.tabs[ui.tabs.length-1] || null;
    renderTabs(); renderReader(); renderList();
    if(!ui.activeTab){ document.body.classList.remove("reader-open"); if(history.state&&history.state.dmailReader) history.back(); }
  }
  function renderTabs(){
    tabsEl.innerHTML = ui.tabs.map(id=>{ const e = Mail.getThread(Mail.threadId(id)); if(!e) return "";
      return `<div class="msg-tab ${ui.activeTab===id?"active":""}" data-tab="${id}">
        <span style="overflow:hidden;text-overflow:ellipsis">${esc(e.subject)}${e.count>1?` · ${e.count}`:""}</span>
        <button class="t-x" data-xtab="${id}" aria-label="Close tab">×</button></div>`; }).join("");
    tabsEl.querySelectorAll("[data-tab]").forEach(t=> t.addEventListener("click", async ev=>{
      if(ev.target.closest("[data-xtab]")) return;
      ui.activeTab = t.dataset.tab; await markThreadRead(ui.activeTab); renderTabs(); renderReader(); renderList();
    }));
    tabsEl.querySelectorAll("[data-xtab]").forEach(x=> x.addEventListener("click", async ev=>{ ev.stopPropagation(); closeTab(x.dataset.xtab); }));
  }
  const me = ()=> (Store.state.user.email||"").toLowerCase();
  const recipients = m=> [...(m.to||[]),...(m.cc||[])].map(a=>a.toLowerCase()===me()?"me":a).join(", ") || "undisclosed recipients";
  const messageHtml = (m, open)=>`<article class="thread-message ${open?"open":""}" data-mid="${esc(m.id)}">
      <div class="tm-head" role="button" tabindex="0" aria-expanded="${open}">
        ${Profile.avatar(m.from.email, m.from.name, "r-avatar")}
        <div class="tm-who"><div class="tm-line"><b>${esc(m.from.name||m.from.email)}</b> <span class="tm-email">&lt;${esc(m.from.email)}&gt;</span></div>
          <div class="tm-to">to ${esc(recipients(m))}</div>
          <div class="tm-snip">${esc(strip(m.body)).slice(0,160)}</div></div>
        <div class="tm-side">${m.hasAttachment?Icons.get("paperclip"):""}<span class="tm-date">${fmtDate(m.date)}</span>
          <button class="icon-btn sm tm-act" data-mreply="${esc(m.id)}" title="Reply" aria-label="Reply">${Icons.get("reply")}</button>
          <button class="icon-btn sm tm-act" data-mmore="${esc(m.id)}" title="More" aria-label="More options">${Icons.get("more")}</button></div>
      </div>
      <div class="tm-content">
        ${(m.labels||[]).length?`<div class="thread-labels">${m.labels.map(l=>`<span class="lbl">${esc(l)}</span>`).join(" ")}</div>`:""}
        ${(m.attachments||[]).length ? `<div class="thread-attachments">${m.attachments.map(a=>window.Live?.enabled && a.mid && a.part?`<a class="attach-chip" href="/api/attachment?mid=${encodeURIComponent(a.mid)}&amp;part=${encodeURIComponent(a.part)}&amp;name=${encodeURIComponent(a.name)}" download>📎 ${esc(a.name)} <span style="color:var(--ink-3)">${esc(a.size)} bytes</span></a>`:`<span class="attach-chip">📎 ${esc(a.name)} <span style="color:var(--ink-3)">${esc(a.size)}</span></span>`).join("")}</div>`:""}
        <div class="r-body">${m.body}</div>
      </div>
    </article>`;
  function renderReader(){
    const id = ui.activeTab, anchor = id && Mail.get(id), thread = id && Mail.getThread(Mail.threadId(id)), e = thread?.latest||anchor;
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
      <button class="icon-btn sm" id="r-print" title="Print">🖨️</button>
      <button class="icon-btn sm" id="r-more" title="More">⋯</button>`;
    const readerIcons={'r-back':'back','r-reply':'reply','r-replyall':'replyall','r-fwd':'forward','r-archive':'archive','r-spam':'spam','r-trash':'trash','r-star':'star','r-unread':'unread','r-print':'print','r-more':'more'};
    for(const [buttonId,icon] of Object.entries(readerIcons)){const button=barEl.querySelector('#'+buttonId);button.innerHTML=Icons.get(icon);button.setAttribute('aria-label',button.title);}

    /* Gmail-style conversation: older messages collapse to one line, the newest (and any that
       were unread) stay open, and long threads fold their middle behind a count. */
    const messages = thread?.messages||[e], last = messages.length-1, fresh = ui.fresh||new Set();
    const isOpen = (m,i)=> i===last || fresh.has(m.id);
    const middle = messages.slice(1, Math.max(1,last-1));
    const fold = !ui.unfolded && messages.length>4 && !middle.some(m=>fresh.has(m.id)) ? middle : [];
    readerEl.innerHTML = `
      <div class="r-subject">${esc(e.subject)}${thread?.count>1?` <span class="thread-count">${thread.count} messages</span>`:""}</div>
      <div class="thread-messages">${messages.map((m,i)=>{
        if(fold.length && i===1) return `<button class="thread-fold" id="thread-fold"><span>${fold.length}</span> older messages</button>`;
        if(fold.includes(m)) return "";
        return messageHtml(m, isOpen(m,i));
      }).join("")}</div>
      <div class="thread-actions">
        ${(()=>{ const many=[...(e.to||[]),...(e.cc||[])].length>1, all=`<button class="btn" data-treply="replyall">${Icons.get("replyall")} Reply all</button>`, one=`<button class="btn" data-treply="reply">${Icons.get("reply")} Reply</button>`;
          return !many ? one : Settings.ui.defaultReply==="replyall" ? all+one : one+all; })()}
        <button class="btn" data-treply="forward">${Icons.get("forward")} Forward</button>
      </div>`;
    readerEl.querySelectorAll(".r-body").forEach(foldQuote);
    readerEl.scrollTop = 0;
    const foldBtn=readerEl.querySelector("#thread-fold");
    if(foldBtn) foldBtn.addEventListener("click", ()=>{ ui.unfolded=true; renderReader(); });
    readerEl.querySelectorAll(".thread-message").forEach(article=>{
      const head=article.querySelector(".tm-head");
      const toggle=()=>{ const open=!article.classList.contains("open"); article.classList.toggle("open",open); head.setAttribute("aria-expanded",String(open)); };
      head.addEventListener("click", ev=>{ if(!ev.target.closest("button")) toggle(); });
      head.addEventListener("keydown", ev=>{ if(ev.target===head&&(ev.key==="Enter"||ev.key===" ")){ ev.preventDefault(); toggle(); } });
    });
    readerEl.querySelectorAll("[data-mreply]").forEach(b=> b.addEventListener("click", ()=> App.go("compose:reply:"+b.dataset.mreply)));
    readerEl.querySelectorAll("[data-mmore]").forEach(b=> b.addEventListener("click", ev=>{ ev.stopPropagation(); const mid=b.dataset.mmore;
      App.menu(b,[{label:"↩ Reply",fn:()=>App.go("compose:reply:"+mid)},{label:"↩↩ Reply all",fn:()=>App.go("compose:replyall:"+mid)},{label:"↪ Forward",fn:()=>App.go("compose:forward:"+mid)}]); }));
    readerEl.querySelectorAll("[data-treply]").forEach(b=> b.addEventListener("click", ()=> App.go("compose:"+b.dataset.treply+":"+e.id)));

    const b = id2 => barEl.querySelector("#"+id2);
    const back = b("r-back"); if(back) back.addEventListener("click", ()=>{ if(history.state&&history.state.dmailReader) history.back(); else closeReader(); });
    const multi=[...(e.to||[]),...(e.cc||[])].length>1, defaultReply=Settings.ui.defaultReply==="replyall"&&multi?"replyall":"reply";
    b("r-reply").addEventListener("click", ()=> App.go("compose:"+defaultReply+":"+e.id));
    b("r-replyall").addEventListener("click", ()=> App.go("compose:replyall:"+e.id));
    b("r-fwd").addEventListener("click", ()=> App.go("compose:forward:"+e.id));
    const moveIds = thread?.folderIds?.length ? thread.folderIds : [id];
    /* Auto-advance (Settings → Advanced) opens the next conversation instead of going back to the list. */
    const neighbour = ()=>{ if(!Settings.ui.autoAdvanceOn) return null; const items=visibleItems(), i=items.findIndex(t=>t.id===Mail.threadId(id));
      const n=i<0?null:items[Settings.ui.autoAdvance==="previous"?i-1:i+1]; return n ? n.latest.id : null; };
    const leave = next=>{ if(next){ ui.tabs=ui.tabs.filter(t=>t!==id); openTab(next); } else closeTab(id); };
    const archive = async ()=>{ const next=neighbour(); await Mail.archive(moveIds); leave(next); renderList(); App.refreshNav(); App.toast("Archived."); };
    const spam = async ()=>{ const next=neighbour(); await Mail.spam(moveIds); leave(next); renderList(); App.refreshNav(); App.toast("Reported as spam."); };
    b("r-archive").addEventListener("click", archive);
    b("r-spam").addEventListener("click", spam);
    b("r-trash").addEventListener("click", async ()=>{ const next=neighbour(); await Mail.trash(moveIds); leave(next); renderList(); App.refreshNav(); App.toast("Moved to Trash."); });
    b("r-star").addEventListener("click", async ()=>{ await Promise.all((thread?.ids||[id]).map(messageId=>Mail.toggleStar(messageId))); renderReader(); renderList(); App.refreshNav(); });
    b("r-unread").addEventListener("click", async ()=>{ await Mail.setRead(thread?.ids||[id], false); closeTab(id); renderList(); App.refreshNav(); });
    b("r-print").addEventListener("click", ()=> window.print());
    b("r-more").addEventListener("click", ev=> App.menu(ev.currentTarget,[
      {label:"↩ Reply", fn:()=>App.go("compose:reply:"+e.id)},{label:"↩↩ Reply all", fn:()=>App.go("compose:replyall:"+e.id)},
      {label:"↪ Forward", fn:()=>App.go("compose:forward:"+e.id)},{sep:true},{label:"🚫 Report spam", fn:spam},
      ...(window.Live?.enabled && e.from?.email && e.from.email.toLowerCase()!==me() ? [{label:"⛔ Block "+e.from.email, fn:()=>Views.blockSender(e.from.email).catch(error=>App.toast(error.message))}] : []),
      {label:"🖨️ Print", fn:()=>window.print()}]));
  }
  renderTabs(); renderReader();
  if(ui.activeTab && Mail.get(ui.activeTab))document.body.classList.add("reader-open");

  /* expose for keyboard shortcuts */
  ui._mail = { openTab, closeTab, closeReader, renderList,
    moveSel(d){ const rows=[...listEl.querySelectorAll(".msg-row")]; if(!rows.length)return;
      let i = rows.findIndex(r=>r.dataset.latestId===ui.activeTab);
      i = Math.max(0, Math.min(rows.length-1, (i<0?0:i)+d));
      openTab(rows[i].dataset.latestId); rows[i].scrollIntoView({block:"nearest"}); } };
};

/* Sent mail and drafts are listed by who they went to. */
function listName(thread){
  const folder=App.ui.folder;
  if(folder!=="sent" && folder!=="drafts") return thread.from.name || thread.from.email;
  const me=(Store.state.user.email||"").toLowerCase();
  const people=[...new Set(thread.messages.filter(m=>m.folder===folder).flatMap(m=>m.to||[]))]
    .map(a=>a.toLowerCase()===me?"me":a.split("@")[0]);
  return people.length ? "To: "+people.join(", ") : folder==="drafts" ? "Draft" : "(no recipient)";
}

/* The phone's Back button closes an open conversation instead of leaving the app. */
window.addEventListener("popstate", ()=>{
  if(document.body.classList.contains("reader-open") && !(history.state&&history.state.dmailReader) && App.ui._mail) App.ui._mail.closeReader();
});

/* Gmail trims the quoted history at the end of a reply behind a "•••" button. Only a trailing
   quote is folded: a quote with the sender's own words after it is part of what they wrote. */
function foldQuote(body){
  const quote=[...body.querySelectorAll("blockquote")].find(q=>!q.parentElement.closest("blockquote"));
  if(!quote) return;
  const after=document.createRange(); after.setStartAfter(quote); after.setEnd(body, body.childNodes.length);
  if(after.toString().trim()) return;
  const parts=[quote], intro=quote.previousElementSibling;
  if(intro && /wrote:\s*$/i.test(intro.textContent||"")) parts.unshift(intro);
  const button=document.createElement("button"); button.type="button"; button.className="quote-toggle";
  button.title="Show trimmed content"; button.setAttribute("aria-label","Show trimmed content"); button.setAttribute("aria-expanded","false"); button.textContent="•••";
  parts[0].before(button); parts.forEach(p=>p.classList.add("quoted-hidden"));
  button.addEventListener("click", ()=>{ const show=button.getAttribute("aria-expanded")!=="true"; button.setAttribute("aria-expanded",String(show)); parts.forEach(p=>p.classList.toggle("quoted-hidden",!show)); });
}

function strip(h){ const d=new DOMParser().parseFromString((h||"").replace(/<br\s*\/?>|<\/(p|div|li|tr|h[1-6])>/gi,"$& "),"text/html"); d.querySelectorAll("blockquote").forEach(q=>{ const intro=q.previousElementSibling; if(intro&&/wrote:\s*$/i.test(intro.textContent||"")) intro.remove(); q.remove(); }); return (d.body.textContent||"").replace(/\s+/g," ").trim(); }
})();
