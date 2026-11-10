/* ============ Dejoiy Mail — view-calendar.js : calendar and booking link ============
   Live mode reads and writes the mailbox's Zimbra calendar (/api/calendar), so invites go to guests
   and phones can sync it. The demo keeps events on this device. Phones open on the agenda; wide
   screens on the month. */
(function(){
"use strict";

const COLOURS = ["#FF4FA3","#FFD23F","#3DDC84","#4DA3FF","#B892FF","#FF8A3D"];
const DOW = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
const REPEAT = [["","Doesn't repeat"],["daily","Every day"],["weekly","Every week"],["monthly","Every month"],["yearly","Every year"]];
const REMIND = [[-1,"No reminder"],[0,"At start"],[10,"10 min before"],[30,"30 min before"],[60,"1 hour before"],[1440,"1 day before"]];
const DAY = 86400000;
const tz = ()=> { try{ return Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Kolkata"; }catch(e){ return "Asia/Kolkata"; } };
const pad = n => String(n).padStart(2,"0");
const ymd = d => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
const hm = d => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
const at = (date, time) => { const [y,m,d]=date.split("-").map(Number), [h,mi]=(time||"00:00").split(":").map(Number); return new Date(y,m-1,d,h||0,mi||0).getTime(); };
const startOfDay = ms => { const d=new Date(ms); d.setHours(0,0,0,0); return d.getTime(); };
const timeLabel = ms => new Date(ms).toLocaleTimeString([], {hour:"numeric", minute:"2-digit"});
const colour = e => e.booked ? "#4DA3FF" : COLOURS[[...String(e.title)].reduce((n,c)=>(n*31+c.charCodeAt(0))>>>0,7) % COLOURS.length];
const minutesLabel = m => { const d=new Date(2000,0,1,Math.floor(m/60),m%60); return d.toLocaleTimeString([], {hour:"numeric", minute:"2-digit"}); };

/* ---------- data: live server or this device ---------- */
const demo = {
  list(){ const s=Store.state;
    if(!s.calEvents){ s.calEvents=(s.events||[]).map(e=>{ const start=at(e.date, /^\d{1,2}:\d{2}$/.test(e.time||"")?e.time:"10:00");
      return {id:e.id, title:e.title, start, end:start+3600000, allDay:!e.time, notes:e.notes||"", guests:"", location:"", repeat:""}; }); Store.save(); }
    return s.calEvents; },
  expand(from, to){
    const out=[];
    for(const e of demo.list()){
      const step={daily:DAY, weekly:7*DAY}[e.repeat], n=e.repeat?(e.count||52):1;
      for(let i=0;i<n;i++){
        let s=e.start;
        if(step) s=e.start+i*step; else if(e.repeat==="monthly"){ const d=new Date(e.start); d.setMonth(d.getMonth()+i); s=d.getTime(); }
        else if(e.repeat==="yearly"){ const d=new Date(e.start); d.setFullYear(d.getFullYear()+i); s=d.getTime(); }
        if(s>to) break;
        if(s+(e.end-e.start)>=from) out.push({...e, invId:e.id, start:s, end:s+(e.end-e.start), repeats:!!e.repeat, organizer:true});
      }
    }
    return out.sort((a,b)=>a.start-b.start);
  }
};
const api = {
  events:(from,to)=> Live.enabled ? Live.request(`calendar?start=${from}&end=${to}`).then(r=>r.events) : Promise.resolve(demo.expand(from,to)),
  detail:e=> Live.enabled ? Live.request(`calendar/event?id=${encodeURIComponent(e.id)}`) : Promise.resolve(demo.list().find(x=>x.id===e.id)||{}),
  save(data){
    if(Live.enabled) return Live.request("calendar", data);
    const list=demo.list(), id=data.invId||uid("e"), row={...data, id, guests:data.guests||""}; delete row.invId;
    const i=list.findIndex(x=>x.id===id); if(i>=0) list[i]=row; else list.push(row); Store.save(); return Promise.resolve({ok:true});
  },
  remove(data){
    if(Live.enabled) return Live.request("calendar", {...data, op:"delete"});
    Store.state.calEvents=demo.list().filter(x=>x.id!==data.invId); Store.save(); return Promise.resolve({ok:true});
  },
  booking:()=> Live.enabled ? Live.request("booking") : Promise.resolve({enabled:false, title:"Meet with me", duration:30, days:[1,2,3,4,5], from:600, to:1080, notice:4, window:14, buffer:0,
    tz:tz(), description:"", location:"", slug:"you", url:location.origin+"/book/you", ready:false, ...(Store.state.booking||{})}),
  saveBooking:data=> Live.enabled ? Live.request("booking", data) : (Store.state.booking=data, Store.save(), api.booking())
};

Views.calendar = function(el){
  const wide = ()=> matchMedia("(min-width:900px)").matches;
  let mode = wide() ? "month" : "agenda", cursor = new Date(), selected = startOfDay(Date.now()), events = [], loading = true;

  function range(){
    if(mode==="month"){ const first=new Date(cursor.getFullYear(), cursor.getMonth(), 1), from=startOfDay(first.getTime()-first.getDay()*DAY); return [from, from+42*DAY]; }
    const from=startOfDay(selected-((new Date(selected).getDay())*DAY)); return [from, from+35*DAY];
  }
  async function load(){
    loading=true; draw();
    const [from,to]=range();
    try{ events = await api.events(from,to); }catch(error){ events=[]; App.toast(error.message); }
    loading=false; draw();
  }
  const on = day => events.filter(e=> e.start < day+DAY && e.end > day && !(e.allDay && e.end===day));

  function chip(e){ return `<button type="button" class="cal-chip${e.allDay?" all":""}" data-ev="${esc(e.id)}|${e.start}" style="--c:${colour(e)}">
    ${e.allDay?"":`<b>${esc(timeLabel(e.start))}</b>`}<span>${esc(e.title)}</span></button>`; }
  function card(e){ const guests=e.guests||"";
    return `<button type="button" class="cal-card" data-ev="${esc(e.id)}|${e.start}" style="--c:${colour(e)}">
      <span class="cal-card-time">${e.allDay?"All day":`${esc(timeLabel(e.start))}<small>${esc(timeLabel(e.end))}</small>`}</span>
      <span class="cal-card-main"><b>${esc(e.title)}</b>
        ${e.location?`<small>📍 ${esc(e.location)}</small>`:""}${e.repeats?`<small>🔁 Repeats</small>`:""}${e.booked?`<small>🔗 Booked through your link</small>`:""}</span></button>`; }

  function draw(){
    const title = mode==="month" ? cursor.toLocaleDateString([], {month:"long", year:"numeric"}) : new Date(selected).toLocaleDateString([], {month:"long", year:"numeric"});
    el.innerHTML = `<div class="cal cal-${mode}">
      <header class="cal-head">
        <div class="cal-title"><h1>${esc(title)}</h1>${loading?`<span class="cal-spin" aria-label="Loading"></span>`:""}</div>
        <div class="cal-tools">
          <div class="cal-seg" role="radiogroup" aria-label="View">${[["agenda","Agenda"],["month","Month"]].map(([m,l])=>`<button type="button" role="radio" data-mode="${m}" aria-checked="${mode===m}">${l}</button>`).join("")}</div>
          <button type="button" class="icon-btn" id="cal-prev" aria-label="Previous">‹</button><button type="button" class="cal-today" id="cal-today">Today</button><button type="button" class="icon-btn" id="cal-next" aria-label="Next">›</button>
          <button type="button" class="cal-link-btn" id="cal-booking">🔗 <span>Booking link</span></button>
          <button type="button" class="cal-add" id="cal-add">＋ <span>Event</span></button>
        </div>
      </header>
      ${mode==="month" ? month() : agenda()}
    </div>`;
    wire();
  }

  function month(){
    const [from]=range(), today=startOfDay(Date.now()), m=cursor.getMonth();
    let cells="";
    for(let i=0;i<42;i++){ const day=from+i*DAY, d=new Date(day), list=on(day);
      cells+=`<div class="cal-cell${d.getMonth()!==m?" out":""}${day===today?" today":""}${day===selected?" sel":""}" data-day="${day}" role="button" tabindex="0" aria-label="${d.toDateString()}, ${list.length} events">
        <span class="cal-n">${d.getDate()}</span>${list.slice(0,3).map(chip).join("")}${list.length>3?`<span class="cal-more">+${list.length-3} more</span>`:""}
        <span class="cal-dots">${list.slice(0,4).map(e=>`<i style="--c:${colour(e)}"></i>`).join("")}</span></div>`; }
    const list=on(selected);
    return `<div class="cal-month"><div class="cal-grid">${DOW.map(d=>`<div class="cal-dow">${d}</div>`).join("")}${cells}</div>
      <aside class="cal-side"><h2>${esc(new Date(selected).toLocaleDateString([], {weekday:"long", day:"numeric", month:"long"}))}</h2>
        ${list.length?list.map(card).join(""):`<div class="cal-empty">Nothing planned. <button type="button" class="cal-add-day" data-addday="${selected}">＋ Add an event</button></div>`}</aside></div>`;
  }

  function agenda(){
    const [from]=range(), today=startOfDay(Date.now());
    const strip=Array.from({length:35},(_,i)=>from+i*DAY).map(day=>{ const d=new Date(day), n=on(day).length;
      return `<button type="button" class="cal-day${day===selected?" sel":""}${day===today?" today":""}" data-pick="${day}" aria-pressed="${day===selected}">
        <small>${DOW[d.getDay()]}</small><b>${d.getDate()}</b><i>${"•".repeat(Math.min(n,3))}</i></button>`; }).join("");
    const days=Array.from({length:21},(_,i)=>selected+i*DAY).filter(day=>day<from+35*DAY).map(day=>{ const list=on(day); if(!list.length && day!==selected) return "";
      return `<section class="cal-agenda-day"><h2>${day===today?"Today · ":""}${esc(new Date(day).toLocaleDateString([], {weekday:"long", day:"numeric", month:"short"}))}</h2>
        ${list.length?list.map(card).join(""):`<div class="cal-empty">Nothing planned. <button type="button" class="cal-add-day" data-addday="${day}">＋ Add an event</button></div>`}</section>`; }).join("");
    return `<div class="cal-strip" id="cal-strip">${strip}</div><div class="cal-agenda">${days}</div>`;
  }

  function wire(){
    el.querySelectorAll("[data-mode]").forEach(b=>b.addEventListener("click",()=>{ mode=b.dataset.mode; if(mode==="month") cursor=new Date(selected); load(); }));
    el.querySelector("#cal-prev").addEventListener("click",()=>step(-1));
    el.querySelector("#cal-next").addEventListener("click",()=>step(1));
    el.querySelector("#cal-today").addEventListener("click",()=>{ cursor=new Date(); selected=startOfDay(Date.now()); load(); });
    el.querySelector("#cal-add").addEventListener("click",()=>editor(null, selected));
    el.querySelector("#cal-booking").addEventListener("click", bookingSheet);
    el.querySelectorAll("[data-day]").forEach(c=>{ const pick=()=>{ selected=+c.dataset.day; draw(); };
      c.addEventListener("click",ev=>{ if(!ev.target.closest("[data-ev]")) pick(); }); c.addEventListener("keydown",ev=>{ if(ev.key==="Enter") pick(); });
      c.addEventListener("dblclick",()=>editor(null,+c.dataset.day)); });
    el.querySelectorAll("[data-pick]").forEach(b=>b.addEventListener("click",()=>{ selected=+b.dataset.pick; draw(); }));
    el.querySelectorAll("[data-addday]").forEach(b=>b.addEventListener("click",()=>editor(null,+b.dataset.addday)));
    el.querySelectorAll("[data-ev]").forEach(b=>b.addEventListener("click",ev=>{ ev.stopPropagation(); const [id,start]=b.dataset.ev.split("|");
      editor(events.find(e=>e.id===id && e.start===+start)); }));
    const strip=el.querySelector("#cal-strip .sel"); if(strip) strip.scrollIntoView({inline:"center", block:"nearest"});
  }
  function step(n){
    if(mode==="month"){ cursor=new Date(cursor.getFullYear(), cursor.getMonth()+n, 1); }
    else { selected=startOfDay(selected+n*7*DAY); }
    load();
  }

  /* ---------- the event sheet ---------- */
  async function editor(e, day){
    let detail={};
    if(e){ try{ detail=await api.detail(e); }catch(error){ App.toast(error.message); } }
    // A repeating event is edited as a series, from its first date.
    const series=e?.repeats && detail.start && !e.allDay, start=series?detail.start:e?e.start:day+10*3600000, end=series&&detail.end?detail.end:e?e.end:start+3600000, all=e?e.allDay:false;
    const guests=(detail.guests||(typeof e?.guests==="string"?e.guests.split(/[,\s]+/):[])||[]).filter(Boolean);
    const replies=detail.replies||{};
    App.dialog({title:e?"Event":"New event", body:`<form class="cal-form" id="cal-form" novalidate>
      <input name="title" class="cal-f-title" maxlength="200" placeholder="Add a title" value="${esc(e?.title||"")}" required aria-label="Title">
      <label class="cal-switch"><input type="checkbox" name="allDay" ${all?"checked":""}> All day</label>
      <div class="cal-when">
        <label>Starts<input type="date" name="sd" value="${ymd(new Date(start))}"><input type="time" name="st" value="${hm(new Date(start))}" ${all?"hidden":""}></label>
        <label>Ends<input type="date" name="ed" value="${ymd(new Date(all?end-1:end))}"><input type="time" name="et" value="${hm(new Date(end))}" ${all?"hidden":""}></label>
      </div>
      <div class="cal-row2"><label>Repeat<select name="repeat">${REPEAT.map(([v,l])=>`<option value="${v}" ${(detail.repeat??e?.repeat??"")===v?"selected":""}>${l}</option>`).join("")}</select></label>
        <label>Reminder<select name="reminder">${REMIND.map(([v,l])=>`<option value="${v}" ${(detail.reminder??(e?-1:10))===v?"selected":""}>${l}</option>`).join("")}</select></label></div>
      <label>Location or video link<input name="location" maxlength="300" value="${esc(e?.location||"")}" placeholder="Office, or a meeting link"></label>
      ${Live.enabled&&!/\/meet\//.test(e?.location||"")?`<button type="button" class="cal-shine" data-shine-meet><span aria-hidden="true">📹</span> Add a Shine video meeting</button>`:""}
      <label>Guests<input name="guests" type="email" multiple value="${esc(guests.join(", "))}" placeholder="priya@company.com, rahul@gmail.com"></label>
      ${guests.length&&Object.keys(replies).length?`<ul class="cal-guests">${guests.map(g=>`<li><span>${esc(g)}</span><em data-r="${esc(replies[g]||"NE")}">${({AC:"Going",DE:"Not going",TE:"Maybe"})[replies[g]]||"Invited"}</em></li>`).join("")}</ul>`:""}
      <label>Notes<textarea name="notes" rows="3" maxlength="10000">${esc(detail.notes??e?.notes??"")}</textarea></label>
      <p class="cal-hint">${series?"🔁 Changes apply to every repeat. ":""}Guests get an email invite they can accept from Gmail, Outlook or any mail app.</p>
      <p class="cal-error" role="alert"></p></form>`,
      actions:[...(e&&e.organizer!==false?[{label:"Delete", fn:()=>{ remove(e, guests); return false; }}]:[]), {label:"Cancel"}, {label:e?"Save":"Add event", primary:true, fn:()=>{ save(e); return false; }}]});
    const form=document.getElementById("cal-form");
    form.elements.allDay.addEventListener("change",()=>{ form.elements.st.hidden=form.elements.et.hidden=form.elements.allDay.checked; });
    form.elements.sd.addEventListener("change",()=>{ if(form.elements.ed.value<form.elements.sd.value) form.elements.ed.value=form.elements.sd.value; });
    form.querySelector("[data-shine-meet]")?.addEventListener("click", ev=>addShineMeeting(ev.currentTarget));
    if(!e) setTimeout(()=>form.elements.title.focus(),60);
  }
  /* "Add a Shine video meeting": Shine makes a room for this event; its link goes in Location, so guests get it in the invite */
  async function addShineMeeting(button){
    const f=document.getElementById("cal-form").elements, err=document.querySelector("#cal-form .cal-error"), all=f.allDay.checked;
    const start=all?at(f.sd.value,"09:00"):at(f.sd.value,f.st.value), end=all?start+3600000:at(f.ed.value,f.et.value);
    button.disabled=true; button.textContent="Making the meeting…"; err.textContent="";
    try{
      const out=await Live.request("shine/meeting",{title:f.title.value.trim()||"Meeting", start, end, guests:f.guests.value});
      f.location.value=out.url;
      if(!f.notes.value.includes(out.url)) f.notes.value=(f.notes.value?f.notes.value+"\n\n":"")+`Join on Shine: ${out.url}`;
      button.remove(); App.toast("Shine meeting added. Save to send the invites.");
    }catch(error){ err.textContent=error.message; button.disabled=false; button.innerHTML='<span aria-hidden="true">📹</span> Add a Shine video meeting'; }
  }
  async function save(e){
    const f=document.getElementById("cal-form").elements, err=document.querySelector("#cal-form .cal-error"), all=f.allDay.checked;
    const start=all?at(f.sd.value,"00:00"):at(f.sd.value,f.st.value), end=all?at(f.ed.value,"00:00")+DAY:at(f.ed.value,f.et.value);
    if(!f.title.value.trim()){ err.textContent="Add a title."; return; }
    if(end<=start){ err.textContent="The event has to end after it starts."; return; }
    const button=document.querySelector(".dlg-foot .btn.primary"); if(button) button.disabled=true;
    try{
      await api.save({invId:e?.invId||undefined, title:f.title.value, allDay:all, start, end, repeat:f.repeat.value, reminder:+f.reminder.value,
        location:f.location.value, guests:f.guests.value, notes:f.notes.value, tz:tz()});
      App.closeDialog(); App.toast(f.guests.value.trim()?"Saved. Invites sent.":"Saved."); selected=startOfDay(start); if(mode==="month") cursor=new Date(start); load();
    }catch(error){ err.textContent=error.message; if(button) button.disabled=false; }
  }
  function remove(e, guests){
    App.confirm(guests.length?`Delete "${e.title}" and tell ${guests.length} ${guests.length===1?"guest":"guests"}?`:`Delete "${e.title}"?`, async ()=>{
      try{ await api.remove({invId:e.invId, title:e.title, guests}); App.toast("Event deleted."); load(); }catch(error){ App.toast(error.message); }
    });
  }

  /* ---------- the booking link ---------- */
  async function bookingSheet(){
    let b; try{ b=await api.booking(); }catch(error){ App.toast(error.message); return; }
    const times=Array.from({length:96},(_,i)=>i*15).filter(m=>m>=300&&m<=1425);
    const sel=(name,list,value)=>`<select name="${name}">${list.map(([v,l])=>`<option value="${v}" ${+value===+v?"selected":""}>${l}</option>`).join("")}</select>`;
    App.dialog({title:"Your booking link", wide:true, body:`<form class="cal-form cal-book" id="book-form" novalidate>
      <div class="cal-book-hero"><label class="cal-switch big"><input type="checkbox" name="enabled" ${b.enabled?"checked":""}> People can book time with me</label>
        <div class="cal-book-url"><code id="book-url">${esc(b.url)}</code>
          <button type="button" class="btn sm" id="book-copy">Copy</button>${navigator.share?`<button type="button" class="btn sm" id="book-share">Share</button>`:""}<a class="btn sm" href="${esc(b.url)}" target="_blank" rel="noopener">Open</a></div>
        ${b.ready===false&&Live.enabled?`<p class="cal-warn">Booking needs the service admin account on the server (PROVISION_ADMIN). Ask your Dejoiy admin to set it.</p>`:""}</div>
      <label>Page title<input name="title" maxlength="80" value="${esc(b.title)}"></label>
      <label>Your link<span class="cal-slug"><span>${esc(location.host)}/book/</span><input name="slug" maxlength="40" value="${esc(b.slug)}" pattern="[a-z0-9-]{3,40}"></span></label>
      <fieldset><legend>Meeting length</legend><div class="cal-chips">${[15,20,30,45,60,90].map(m=>`<label><input type="radio" name="duration" value="${m}" ${b.duration===m?"checked":""}><span>${m<60?m+" min":m/60+" h"}${m===90?"":""}</span></label>`).join("")}</div></fieldset>
      <fieldset><legend>Days</legend><div class="cal-chips">${DOW.map((d,i)=>`<label><input type="checkbox" name="days" value="${i}" ${b.days.includes(i)?"checked":""}><span>${d}</span></label>`).join("")}</div></fieldset>
      <div class="cal-row2"><label>From${sel("from",times.map(m=>[m,minutesLabel(m)]),b.from)}</label><label>To${sel("to",times.map(m=>[m+15,minutesLabel(m+15)]),b.to)}</label></div>
      <div class="cal-row3"><label>Notice${sel("notice",[[0,"None"],[1,"1 hour"],[2,"2 hours"],[4,"4 hours"],[12,"12 hours"],[24,"1 day"],[48,"2 days"]],b.notice)}</label>
        <label>Book up to${sel("window",[[7,"1 week"],[14,"2 weeks"],[30,"1 month"],[60,"2 months"]],b.window)}</label>
        <label>Break after${sel("buffer",[[0,"None"],[5,"5 min"],[10,"10 min"],[15,"15 min"],[30,"30 min"]],b.buffer)}</label></div>
      <label>Where we'll meet<input name="location" maxlength="300" value="${esc(b.location)}" placeholder="Office address or a video link"></label>
      <label>About the meeting<textarea name="description" rows="2" maxlength="500" placeholder="What people should know before booking">${esc(b.description)}</textarea></label>
      <p class="cal-hint">Times are in ${esc(tz())}. Busy times in your calendar are never offered. Every booking lands in your calendar and the guest gets an invite.</p>
      <p class="cal-error" role="alert"></p></form>`,
      actions:[{label:"Close"},{label:"Save", primary:true, fn:()=>{ saveBooking(); return false; }}]});
    const copy=document.getElementById("book-copy");
    copy.addEventListener("click",async()=>{ try{ await navigator.clipboard.writeText(b.url); copy.textContent="Copied ✓"; }catch(e){ App.toast(b.url); } });
    document.getElementById("book-share")?.addEventListener("click",()=>navigator.share({title:b.title, url:b.url}).catch(()=>{}));
  }
  async function saveBooking(){
    const form=document.getElementById("book-form"), f=form.elements, err=form.querySelector(".cal-error");
    const data={enabled:f.enabled.checked, title:f.title.value, slug:f.slug.value.trim().toLowerCase(), duration:+form.querySelector("[name=duration]:checked")?.value,
      days:[...form.querySelectorAll("[name=days]:checked")].map(x=>+x.value), from:+f.from.value, to:+f.to.value, notice:+f.notice.value, window:+f.window.value,
      buffer:+f.buffer.value, location:f.location.value, description:f.description.value, tz:tz()};
    try{ await api.saveBooking(data); App.closeDialog(); App.toast(data.enabled?"Booking link is live.":"Booking link saved (switched off)."); }
    catch(error){ err.textContent=error.message; }
  }

  load();
};
})();
