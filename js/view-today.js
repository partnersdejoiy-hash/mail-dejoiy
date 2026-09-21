/* ============ Dejoiy Mail — view-today.js : Today dashboard ============ */
(function(){
"use strict";

Views.today = function(el){
  const s = Store.state, c = Mail.counts();
  const hr = new Date().getHours();
  const greet = hr<12 ? "Good morning" : hr<17 ? "Good afternoon" : "Good evening";
  const todayStr = new Date().toLocaleDateString([], {weekday:"long", day:"numeric", month:"long", year:"numeric"});
  const todayYmd = new Date().toISOString().slice(0,10);
  const todaysEvents = s.events.filter(e=>e.date===todayYmd);
  const openTodos = s.todos.filter(t=>!t.done);

  el.innerHTML = `
    <div class="view-head"><h1>${greet}, ${esc(s.user.name.split(" ")[0])} 👋</h1><span class="sub">${todayStr}</span></div>
    <div class="grid c4" style="margin-bottom:14px">
      <div class="card"><div class="stat">${c.unread}</div><div class="stat-sub">Unread emails</div>
        <div class="btn-row" style="margin-top:8px"><button class="btn sm" data-go="mail:inbox">Open inbox</button></div></div>
      <div class="card"><div class="stat">${todaysEvents.length}</div><div class="stat-sub">Events today</div>
        <div class="btn-row" style="margin-top:8px"><button class="btn sm" data-go="calendar">Calendar</button></div></div>
      <div class="card"><div class="stat">${openTodos.length}</div><div class="stat-sub">Open to-dos</div>
        <div class="btn-row" style="margin-top:8px"><button class="btn sm" data-go="calendar">View tasks</button></div></div>
      <div class="card"><div class="stat">${s.contacts.length}</div><div class="stat-sub">Contacts</div>
        <div class="btn-row" style="margin-top:8px"><button class="btn sm" data-go="contacts">Contacts</button></div></div>
    </div>
    <div class="grid c2">
      <div class="card"><h3>📰 Today’s headlines</h3><div id="news-list" class="grid" style="gap:10px"></div></div>
      <div>
        <div class="card" style="margin-bottom:14px"><h3>📅 Today’s schedule</h3><div id="today-events"></div></div>
        <div class="card"><h3>✅ To-dos</h3><div id="today-todos"></div>
          <div class="btn-row" style="margin-top:10px"><button class="btn sm" id="today-add-todo">+ Add to-do</button></div></div>
      </div>
    </div>`;

  el.querySelector("#news-list").innerHTML = DemoData.news.map(n=>`
    <div class="news-card card" data-news="${esc(n.title)}" role="button" tabindex="0">
      <div class="news-ico">${n.ico}</div>
      <div><div class="news-src">${esc(n.src)} · ${fmtDate(n.ts)}</div>
      <div class="news-title">${esc(n.title)}</div><div class="news-sum">${esc(n.sum)}</div></div>
    </div>`).join("");
  el.querySelectorAll("[data-news]").forEach(card=>{
    card.addEventListener("click", ()=> App.toast("Demo headline — full articles arrive with the news backend."));
  });

  el.querySelector("#today-events").innerHTML = todaysEvents.length
    ? todaysEvents.map(e=>`<div class="todo"><span>🕙 ${esc(e.time||"")}</span><span><b>${esc(e.title)}</b>${e.notes?` <span style="color:var(--ink-3)">— ${esc(e.notes)}</span>`:""}</span></div>`).join("")
    : `<div class="empty-note">Nothing scheduled today. Enjoy the calm.</div>`;

  const renderTodos = ()=>{
    el.querySelector("#today-todos").innerHTML = openTodos.length
      ? openTodos.map(t=>`<div class="todo"><input type="checkbox" data-todo="${t.id}"><span>${esc(t.text)}</span></div>`).join("")
      : `<div class="empty-note">All done! 🎉</div>`;
    el.querySelectorAll("[data-todo]").forEach(cb=> cb.addEventListener("change", ()=>{
      const t = s.todos.find(x=>x.id===cb.dataset.todo); if(t){ t.done = cb.checked; Store.save(); App.refreshNav(); Views.today(el); }
    }));
  };
  renderTodos();
  el.querySelector("#today-add-todo").addEventListener("click", ()=>{
    App.promptDialog("New to-do", "What needs doing?", "", text=>{
      if(text.trim()){ s.todos.push({id:uid("t"), text:text.trim(), done:false}); Store.save(); Views.today(el); }
    });
  });
  el.querySelectorAll("[data-go]").forEach(b=> b.addEventListener("click", ()=>App.go(b.dataset.go)));
};

})();
