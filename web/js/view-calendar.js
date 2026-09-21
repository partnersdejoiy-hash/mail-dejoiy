/* ============ Dejoiy Mail — view-calendar.js : month calendar + to-dos ============ */
(function(){
"use strict";

Views.calendar = function(el){
  const s = Store.state;
  let viewY = new Date().getFullYear(), viewM = new Date().getMonth();

  function render(){
    const first = new Date(viewY, viewM, 1), startDay = first.getDay();
    const days = new Date(viewY, viewM+1, 0).getDate();
    const todayYmd = new Date().toISOString().slice(0,10);
    let cells = "";
    for(let i=0;i<startDay;i++) cells += `<div class="cal-day dim"></div>`;
    for(let d=1;d<=days;d++){
      const ymd = `${viewY}-${String(viewM+1).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
      const evs = s.events.filter(e=>e.date===ymd);
      cells += `<div class="cal-day ${ymd===todayYmd?"today":""}" data-day="${ymd}" role="button" tabindex="0">
        <div class="d-n">${d}</div>${evs.slice(0,3).map(e=>`<div class="cal-ev">${esc(e.time||"")} ${esc(e.title)}</div>`).join("")}
        ${evs.length>3?`<div class="cal-ev">+${evs.length-3} more</div>`:""}</div>`;
    }
    el.innerHTML = `
      <div class="view-head"><h1>📅 Calendar</h1><span class="sub">${first.toLocaleDateString([], {month:"long", year:"numeric"})}</span>
        <span style="flex:1"></span>
        <div class="btn-row">
          <button class="btn sm" id="cal-prev">←</button>
          <button class="btn sm" id="cal-today">Today</button>
          <button class="btn sm" id="cal-next">→</button>
          <button class="btn sm primary" id="cal-add">+ Event</button>
        </div></div>
      <div class="grid c2" style="grid-template-columns:2fr 1fr;align-items:start">
        <div><div class="cal-grid">
          ${["Sun","Mon","Tue","Wed","Thu","Fri","Sat"].map(d=>`<div class="cal-dow">${d}</div>`).join("")}${cells}
        </div></div>
        <div>
          <div class="card" style="margin-bottom:14px"><h3>✅ To-dos</h3><div id="cal-todos"></div>
            <div class="btn-row" style="margin-top:10px"><button class="btn sm" id="cal-add-todo">+ Add to-do</button></div></div>
          <div class="card"><h3>📌 Upcoming</h3><div id="cal-upcoming"></div></div>
        </div>
      </div>`;
    el.querySelector("#cal-prev").addEventListener("click", ()=>{ viewM--; if(viewM<0){viewM=11;viewY--;} render(); });
    el.querySelector("#cal-next").addEventListener("click", ()=>{ viewM++; if(viewM>11){viewM=0;viewY++;} render(); });
    el.querySelector("#cal-today").addEventListener("click", ()=>{ const n=new Date(); viewY=n.getFullYear(); viewM=n.getMonth(); render(); });
    el.querySelector("#cal-add").addEventListener("click", ()=> eventDialog(""));
    el.querySelectorAll("[data-day]").forEach(d=>{
      const open = ()=> dayDialog(d.dataset.day);
      d.addEventListener("click", open);
      d.addEventListener("keydown", e=>{ if(e.key==="Enter") open(); });
    });
    renderTodos(); renderUpcoming();
  }

  function renderTodos(){
    el.querySelector("#cal-todos").innerHTML = s.todos.length
      ? s.todos.map(t=>`<div class="todo ${t.done?"done":""}"><input type="checkbox" data-t="${t.id}" ${t.done?"checked":""}><span>${esc(t.text)}</span><button class="t-x icon-btn sm" data-delt="${t.id}">×</button></div>`).join("")
      : `<div class="empty-note">No to-dos.</div>`;
    el.querySelectorAll("[data-t]").forEach(cb=> cb.addEventListener("change", ()=>{
      s.todos.find(x=>x.id===cb.dataset.t).done = cb.checked; Store.save(); renderTodos();
    }));
    el.querySelectorAll("[data-delt]").forEach(x=> x.addEventListener("click", ()=>{
      s.todos = s.todos.filter(t=>t.id!==x.dataset.delt); Store.save(); renderTodos();
    }));
    el.querySelector("#cal-add-todo").addEventListener("click", ()=>{
      App.promptDialog("New to-do", "What needs doing?", "", text=>{
        if(text.trim()){ s.todos.push({id:uid("t"), text:text.trim(), done:false}); Store.save(); renderTodos(); }
      });
    });
  }

  function renderUpcoming(){
    const now = new Date().toISOString().slice(0,10);
    const up = s.events.filter(e=>e.date>=now).sort((a,b)=>a.date.localeCompare(b.date)).slice(0,6);
    el.querySelector("#cal-upcoming").innerHTML = up.length
      ? up.map(e=>`<div class="todo"><span>📅 ${e.date.slice(8)}/${e.date.slice(5,7)}</span><span><b>${esc(e.title)}</b>${e.time?` <span style="color:var(--ink-3)">${esc(e.time)}</span>`:""}</span></div>`).join("")
      : `<div class="empty-note">Nothing upcoming.</div>`;
  }

  function eventDialog(date){
    App.dialog({ title:"New event", body:`
      <div class="field"><label>Title</label><input type="text" id="ev-title" placeholder="Team standup"></div>
      <div class="grid c2"><div class="field"><label>Date</label><input type="date" id="ev-date" value="${date||new Date().toISOString().slice(0,10)}"></div>
      <div class="field"><label>Time</label><input type="text" id="ev-time" placeholder="10:00"></div></div>
      <div class="field"><label>Notes</label><input type="text" id="ev-notes" placeholder="Optional"></div>`,
      actions:[{label:"Cancel"},{label:"Add event", primary:true, fn:()=>{
        const t = document.getElementById("ev-title").value.trim();
        if(!t){ App.toast("Give the event a title."); return false; }
        s.events.push({id:uid("e"), title:t, date:document.getElementById("ev-date").value,
          time:document.getElementById("ev-time").value.trim(), notes:document.getElementById("ev-notes").value.trim()});
        Store.save(); App.toast("Event added ✓"); render();
      }}]});
  }

  function dayDialog(ymd){
    const evs = s.events.filter(e=>e.date===ymd);
    App.dialog({ title:"Events — "+ymd, body:
      (evs.length ? evs.map(e=>`<div class="todo"><span>🕙 ${esc(e.time||"all day")}</span><span><b>${esc(e.title)}</b>${e.notes?` — ${esc(e.notes)}`:""}</span><button class="t-x icon-btn sm" data-delev="${e.id}">×</button></div>`).join("")
        : `<div class="empty-note">No events this day.</div>`),
      actions:[{label:"Close"},{label:"+ Add event", primary:true, fn:()=>{ eventDialog(ymd); }}]});
    document.querySelectorAll("[data-delev]").forEach(x=> x.addEventListener("click", ()=>{
      s.events = s.events.filter(e=>e.id!==x.dataset.delev); Store.save(); App.closeDialog(); render(); App.toast("Event deleted.");
    }));
  }

  render();
};
})();
