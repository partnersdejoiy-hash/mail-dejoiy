/* ============ Dejoiy Mail — view-mail.js : folders, message list, tabs, reader ============ */
(function(){
"use strict";

Views.mail = function(el, folder){
  const ui = App.ui;
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
        <span style="margin-left:auto;font-size:12px;color:var(--ink-3)">${list.length} messages</span>
      </div>
      <div class="msg-list" id="msg-list"></div>
    </div>
    <div class="reader-col">
      <div class="msg-tabs" id="msg-tabs"></div>
      <div class="r-toolbar" id="reader-bar" style="display:none"></div>
      <div class="reader" id="reader"></div>
    </div>
  </div>`;

  /* ---- folder nav ---- */
  el.querySelectorAll("[data-folder]").forEach(b=> b.addEventListener("click", ()=>{
    ui.folder = b.dataset.folder; ui.sel.clear(); ui.activeTab = null;
    document.body.classList.remove("reader-open"); Views.mail(el, ui.folder); App.refreshNav();
  }));

  /* ---- message list ---- */
  const listEl = el.querySelector("#msg-list");
  const renderList = ()=>{
    const items = Mail.list(ui.folder);
    listEl.innerHTML = items.length ? items.map(e=>`
      <div class="msg-row ${e.read?"":"unread"} ${ui.activeTab===e.id?"selected":""}" data-id="${e.id}" role="button" tabindex="0">
        <input type="checkbox" class="m-check" data-check="${e.id}" ${ui.sel.has(e.id)?"checked":""} aria-label="Select message">
        <button class="star ${e.starred?"on":""}" data-star="${e.id}" aria-label="Star">★</button>
        <div class="m-main">
          <div class="m-top"><span class="m-from">${esc(e.from.name)}</span>
            <span class="m-flags">${e.important?"❗":""}${e.hasAttachment?"📎":""}</span>
            <span class="m-date">${fmtDate(e.date)}</span></div>
          <div class="m-subj">${esc(e.subject)}</div>
          <div class="m-snip">${esc(strip(e.body)).slice(0,90)}</div>
          ${(e.labels||[]).map(l=>`<span class="lbl">${esc(l)}</span>`).join(" ")}
        </div>
      </div>`).join("")
      : `<div class="empty-note">${ui.folder==="trash" ? "Trash is empty. ✨" : "Nothing here yet."}</div>`;
    bindRows();
  };
  const bindRows = ()=>{
    listEl.querySelectorAll("[data-check]").forEach(cb=> cb.addEventListener("click", ev=>{
      ev.stopPropagation();
      cb.checked ? ui.sel.add(cb.dataset.check) : ui.sel.delete(cb.dataset.check);
    }));
    listEl.querySelectorAll("[data-star]").forEach(st=> st.addEventListener("click", ev=>{
      ev.stopPropagation(); Mail.toggleStar(st.dataset.star); renderList(); App.refreshNav();
    }));
    listEl.querySelectorAll(".msg-row").forEach(row=> {
      const open = ()=> openTab(row.dataset.id);
      row.addEventListener("click", ev=>{ if(ev.target.closest("input,button")) return; open(); });
      row.addEventListener("keydown", ev=>{ if(ev.key==="Enter"){open();} });
    });
  };
  renderList();

  /* ---- toolbar ---- */
  const selIds = ()=> [...ui.sel];
  const needSel = ()=>{ if(!selIds().length){ App.toast("Select at least one message first."); return false; } return true; };
  el.querySelector("#sel-all").addEventListener("change", ev=>{
    ui.sel.clear();
    if(ev.target.checked) Mail.list(ui.folder).forEach(e=>ui.sel.add(e.id));
    renderList();
  });
  el.querySelector("#tb-refresh").addEventListener("click", ()=>{ const em = Mail.checkMail(); renderList(); App.refreshNav();
    App.toast(em.folder==="inbox" ? "New mail: "+em.subject : "New mail filtered."); });
  el.querySelector("#tb-archive").addEventListener("click", ()=>{ if(!needSel())return; Mail.archive(selIds()); ui.sel.clear(); renderList(); App.refreshNav(); App.toast("Archived."); });
  el.querySelector("#tb-spam").addEventListener("click", ()=>{ if(!needSel())return; Mail.spam(selIds()); ui.sel.clear(); renderList(); App.refreshNav(); App.toast("Reported as spam."); });
  el.querySelector("#tb-trash").addEventListener("click", ()=>{ if(!needSel())return; Mail.trash(selIds()); ui.sel.clear(); renderList(); App.refreshNav(); App.toast("Moved to Trash."); });
  el.querySelector("#tb-read").addEventListener("click", ()=>{ if(!needSel())return;
    const anyUnread = selIds().some(id=>!Mail.get(id).read);
    selIds().forEach(id=>Mail.setRead(id, anyUnread)); ui.sel.clear(); renderList(); App.refreshNav(); });
  el.querySelector("#tb-label").addEventListener("click", ev=>{
    if(!needSel())return;
    App.menu(ev.currentTarget, ["work","personal","finance","design"].map(l=>({label:"🏷️ "+l, fn:()=>{
      Mail.addLabel(selIds(), l); ui.sel.clear(); renderList(); App.toast("Labelled "+l+"."); }})));
  });

  /* ---- tabs + reader ---- */
  const tabsEl = el.querySelector("#msg-tabs"), readerEl = el.querySelector("#reader"), barEl = el.querySelector("#reader-bar");
  function openTab(id){
    if(!ui.tabs.includes(id)) ui.tabs.push(id);
    ui.activeTab = id;
    Mail.setRead(id, true);
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
    tabsEl.innerHTML = ui.tabs.map(id=>{ const e = Mail.get(id); if(!e) return "";
      return `<div class="msg-tab ${ui.activeTab===id?"active":""}" data-tab="${id}">
        <span style="overflow:hidden;text-overflow:ellipsis">${esc(e.subject)}</span>
        <button class="t-x" data-xtab="${id}" aria-label="Close tab">×</button></div>`; }).join("");
    tabsEl.querySelectorAll("[data-tab]").forEach(t=> t.addEventListener("click", ev=>{
      if(ev.target.closest("[data-xtab]")) return;
      ui.activeTab = t.dataset.tab; Mail.setRead(ui.activeTab, true); renderTabs(); renderReader(); renderList();
    }));
    tabsEl.querySelectorAll("[data-xtab]").forEach(x=> x.addEventListener("click", ev=>{ ev.stopPropagation(); closeTab(x.dataset.xtab); }));
  }
  function renderReader(){
    const id = ui.activeTab, e = id && Mail.get(id);
    if(!e){ barEl.style.display="none"; readerEl.innerHTML = `<div class="reader-empty">📭<br><br>Select a message to read it here.</div>`; return; }
    barEl.style.display = "flex";
    barEl.innerHTML = `
      <button class="icon-btn sm only-mobile" id="r-back" title="Back">←</button>
      <button class="icon-btn sm" id="r-reply" title="Reply (R)">↩</button>
      <button class="icon-btn sm" id="r-replyall" title="Reply all">↩↩</button>
      <button class="icon-btn sm" id="r-fwd" title="Forward (F)">↪</button>
      <button class="icon-btn sm" id="r-archive" title="Archive (E)">🗄️</button>
      <button class="icon-btn sm" id="r-spam" title="Spam">🚫</button>
      <button class="icon-btn sm" id="r-trash" title="Delete (#)">🗑️</button>
      <button class="icon-btn sm star ${e.starred?"on":""}" id="r-star" title="Star (S)">★</button>
      <button class="icon-btn sm" id="r-unread" title="Mark unread">✉️</button>
      <button class="icon-btn sm" id="r-print" title="Print">🖨️</button>`;
    readerEl.innerHTML = `
      <div class="r-subject">${esc(e.subject)}</div>
      <div class="r-meta">
        <div class="r-avatar">${initials(e.from.name)}</div>
        <div><div><b>${esc(e.from.name)}</b> <span style="color:var(--ink-2)">&lt;${esc(e.from.email)}&gt;</span></div>
        <div style="font-size:12px;color:var(--ink-3)">to ${(e.to||[]).map(esc).join(", ")} · ${fmtDate(e.date)}</div></div>
        <div style="margin-left:auto">${(e.labels||[]).map(l=>`<span class="lbl">${esc(l)}</span>`).join(" ")}</div>
      </div>
      ${(e.attachments||[]).length ? `<div style="margin-bottom:12px">${e.attachments.map(a=>`<span class="attach-chip">📎 ${esc(a.name)} <span style="color:var(--ink-3)">${esc(a.size)}</span></span>`).join("")}</div>`:""}
      <div class="r-body">${e.body}</div>`;
    const b = id2 => barEl.querySelector("#"+id2);
    const back = b("r-back"); if(back) back.addEventListener("click", ()=> document.body.classList.remove("reader-open"));
    b("r-reply").addEventListener("click", ()=> App.go("compose:reply:"+id));
    b("r-replyall").addEventListener("click", ()=> App.go("compose:replyall:"+id));
    b("r-fwd").addEventListener("click", ()=> App.go("compose:forward:"+id));
    b("r-archive").addEventListener("click", ()=>{ Mail.archive(id); closeTab(id); renderList(); App.refreshNav(); App.toast("Archived."); });
    b("r-spam").addEventListener("click", ()=>{ Mail.spam(id); closeTab(id); renderList(); App.refreshNav(); App.toast("Reported as spam."); });
    b("r-trash").addEventListener("click", ()=>{ Mail.trash(id); closeTab(id); renderList(); App.refreshNav(); App.toast("Moved to Trash."); });
    b("r-star").addEventListener("click", ()=>{ Mail.toggleStar(id); renderReader(); renderList(); App.refreshNav(); });
    b("r-unread").addEventListener("click", ()=>{ Mail.setRead(id, false); closeTab(id); renderList(); App.refreshNav(); });
    b("r-print").addEventListener("click", ()=> window.print());
  }
  renderTabs(); renderReader();

  /* expose for keyboard shortcuts */
  ui._mail = { openTab, closeTab, renderList,
    moveSel(d){ const rows=[...listEl.querySelectorAll(".msg-row")]; if(!rows.length)return;
      let i = rows.findIndex(r=>r.dataset.id===ui.activeTab);
      i = Math.max(0, Math.min(rows.length-1, (i<0?0:i)+d));
      openTab(rows[i].dataset.id); rows[i].scrollIntoView({block:"nearest"}); } };
};

function strip(h){ const d=document.createElement("div"); d.innerHTML=h||""; return d.textContent||""; }
})();
