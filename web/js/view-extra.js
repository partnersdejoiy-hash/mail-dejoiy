/* ============ Dejoiy Mail — view-extra.js : Notepad + Chat ============ */
(function(){
"use strict";

/* ---------------- Notepad ---------------- */
Views.notes = function(el){
  const s = Store.state;
  let active = s.notes[0] && s.notes[0].id;

  function render(){
    const n = s.notes.find(x=>x.id===active) || s.notes[0];
    active = n && n.id;
    el.innerHTML = `
      <div class="view-head"><h1>📝 Notepad</h1><span class="sub">autosaves as you type</span><span style="flex:1"></span>
        <button class="btn sm primary" id="nt-new">+ New note</button></div>
      <div class="grid" style="grid-template-columns:240px 1fr;align-items:start">
        <div class="card" style="padding:8px">${s.notes.map(x=>`
          <button class="nav-item ${x.id===active?"active":""}" data-note="${x.id}">
            <span class="n-ico">📄</span><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(x.title||"Untitled")}</span>
          </button>`).join("") || `<div class="empty-note">No notes.</div>`}</div>
        <div class="card">${n ? `
          <div class="field"><input type="text" id="nt-title" value="${esc(n.title)}" placeholder="Note title" style="font-weight:700;font-size:15px"></div>
          <div class="field"><textarea id="nt-body" rows="16" placeholder="Write here…">${esc(n.body)}</textarea></div>
          <div class="btn-row"><span style="font-size:12px;color:var(--ink-3)">Saved ✓</span><span style="flex:1"></span>
          <button class="btn sm danger" id="nt-del">Delete note</button></div>`
          : `<div class="empty-note">Create your first note →</div>`}</div>
      </div>`;
    el.querySelectorAll("[data-note]").forEach(b=> b.addEventListener("click", ()=>{ active=b.dataset.note; render(); }));
    el.querySelector("#nt-new").addEventListener("click", ()=>{
      const nn = {id:uid("n"), title:"Untitled", body:"", ts:Date.now()};
      s.notes.unshift(nn); active = nn.id; Store.save(); render();
      el.querySelector("#nt-title").focus();
    });
    if(n){
      el.querySelector("#nt-title").addEventListener("input", ev=>{ n.title = ev.target.value; Store.save(); });
      el.querySelector("#nt-body").addEventListener("input", ev=>{ n.body = ev.target.value; n.ts = Date.now(); Store.save(); });
      el.querySelector("#nt-del").addEventListener("click", ()=>{
        App.confirm("Delete this note?", ()=>{ s.notes = s.notes.filter(x=>x.id!==n.id); Store.save(); render(); });
      });
    }
  }
  render();
};

/* ---------------- Chat (local demo) ---------------- */
Views.chat = function(el, contactId){
  const s = Store.state;
  const people = s.contacts;
  let active = contactId || people[0].id;
  if(!s.chats[active]) s.chats[active] = seedChat(active);

  function seedChat(cid){
    return [{from:"them", text:"Hey! This is a local demo chat — messages stay in your browser.", ts:Date.now()-36e5}];
  }
  function render(){
    const p = people.find(x=>x.id===active);
    const msgs = s.chats[active] || (s.chats[active]=seedChat(active));
    el.innerHTML = `
    <div class="view-head"><h1>💬 Chat</h1><span class="sub">demo — stored locally</span></div>
    <div class="chat-wrap">
      <div class="chat-list">${people.map(c=>`
        <button class="chat-person ${c.id===active?"active":""}" data-chat="${c.id}">
          <span class="presence ${c.presence}"></span>
          <span class="r-avatar" style="width:34px;height:34px;font-size:13px">${initials(c.name)}</span>
          <span><b style="font-size:13.5px">${esc(c.name)}</b><br><span style="font-size:11.5px;color:var(--ink-3)">${esc(c.presence==="online"?"Online":c.presence==="away"?"Away":"Offline")}</span></span>
        </button>`).join("")}</div>
      <div class="chat-main">
        <div class="chat-head"><button class="icon-btn sm only-mobile" id="ch-back">←</button>
          <span class="presence ${p.presence}"></span> ${esc(p.name)}</div>
        <div class="chat-body" id="ch-body">${msgs.map(m=>`
          <div class="bubble ${m.from==="me"?"me":"them"}">${esc(m.text)}<div class="b-t">${new Date(m.ts).toLocaleTimeString([], {hour:"numeric",minute:"2-digit"})}</div></div>`).join("")}</div>
        <div class="chat-input"><input type="text" id="ch-text" placeholder="Message ${esc(p.name)}…" autocomplete="off">
          <button class="btn primary" id="ch-send">Send</button></div>
      </div>
    </div>`;
    const body = el.querySelector("#ch-body"); body.scrollTop = body.scrollHeight;
    el.querySelectorAll("[data-chat]").forEach(b=> b.addEventListener("click", ()=>{
      active = b.dataset.chat; document.body.classList.add("chat-open"); render();
    }));
    const back = el.querySelector("#ch-back");
    if(back) back.addEventListener("click", ()=> document.body.classList.remove("chat-open"));
    const send = ()=>{
      const inp = el.querySelector("#ch-text"), t = inp.value.trim(); if(!t) return;
      msgs.push({from:"me", text:t, ts:Date.now()}); Store.save(); render();
      setTimeout(()=>{ /* simulated reply */
        msgs.push({from:"them", text:DemoData.cannedReplies[Math.floor(Math.random()*DemoData.cannedReplies.length)], ts:Date.now()});
        Store.save(); if(App.route==="chat") render(); App.sound("mail");
      }, 1200);
    };
    el.querySelector("#ch-send").addEventListener("click", send);
    el.querySelector("#ch-text").addEventListener("keydown", e=>{ if(e.key==="Enter") send(); });
  }
  render();
};
})();
