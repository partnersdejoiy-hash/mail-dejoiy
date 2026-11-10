/* ============ Dejoiy Mail — view-updates.js : Dejoiy Updates and the company box ============
   Dejoiy Updates: posts from the Dejoiy team, seen by every mailbox.
   Company box: posts from people whose role allows it, seen only inside their company. */
(function(){
"use strict";

const BOX = {
  dejoiy:{title:"Dejoiy Updates", lede:"News from the Dejoiy team: new features, tips and service notices."},
  company:{title:"", lede:"Updates for everyone in your company."}
};
const when = ms => new Date(ms).toLocaleString([], {dateStyle:"medium", timeStyle:"short"});
const paragraphs = text => esc(text).split(/\n{2,}/).map(p=>`<p>${p.replace(/\n/g,"<br>")}</p>`).join("");

/* Demo mode keeps posts on this device so the pages can be tried without a server. */
const demo = {
  get(){ const s=Store.state; s.updates = s.updates || {dejoiy:[{id:"d1",title:"Welcome to Dejoiy Mail",body:"Pick a colour on the home page and every screen follows it.\n\nLabels now colour your mail cards.",author:"Dejoiy team",date:Date.now()-864e5}],company:[]};
    return {dejoiy:s.updates.dejoiy, company:{name:"Company updates", posts:s.updates.company}, can:{dejoiy:true, company:true}}; },
  post(data){ const s=Store.state.updates, list=s[data.box];
    if(data.op==="post") list.unshift({id:"u"+Date.now(), title:data.title, body:data.body, author:Store.state.user?.name||"You", date:Date.now()});
    else s[data.box]=list.filter(p=>p.id!==data.id);
    Store.save(); return demo.get(); }
};
const load = ()=> window.Live?.enabled ? Live.request("updates") : Promise.resolve(demo.get());
const send = data => window.Live?.enabled ? Live.request("updates", data) : Promise.resolve(demo.post(data));

Views.updates = function(el, box){
  el.innerHTML = `<div class="upd"><div class="upd-skel" aria-hidden="true"><i></i><i></i><i></i></div></div>`;
  load().then(view=>{ if(App.route!==(box==="dejoiy"?"news":"company")) return; App.companyName = view.company?.name; draw(view); App.refreshNav(); })
    .catch(error=>{ el.innerHTML = `<div class="empty-note">${esc(error.message)}</div>`; });

  function draw(view){
    const posts = box==="dejoiy" ? view.dejoiy : view.company.posts, mine = view.can[box];
    const title = box==="dejoiy" ? BOX.dejoiy.title : view.company.name;
    el.innerHTML = `<div class="upd upd-${box}">
      <header class="upd-head"><span class="upd-badge">${Icons.get(box==="dejoiy"?"megaphone":"building")}</span>
        <div><h1>${esc(title)}</h1><p>${esc(BOX[box].lede)}</p></div></header>
      ${mine?`<form class="upd-new" id="upd-form">
        <input name="title" maxlength="120" placeholder="Title" required aria-label="Update title">
        <textarea name="body" maxlength="4000" rows="3" placeholder="What should everyone know?" required aria-label="Update text"></textarea>
        <div class="upd-new-foot"><span class="upd-who">Posting to ${box==="dejoiy"?"every Dejoiy Mail user":"everyone at "+esc(view.company.domain||"your company")}</span><button class="btn primary">Post update</button></div>
      </form>`:""}
      <div class="upd-list">${posts.map((p,i)=>`<article class="upd-post" style="--i:${Math.min(i,8)}">
        <div class="upd-meta"><b>${esc(p.author)}</b><span>${esc(when(p.date))}</span>${mine?`<button class="icon-btn sm" data-del="${esc(p.id)}" aria-label="Delete this update">${Icons.get("trash")}</button>`:""}</div>
        <h2>${esc(p.title)}</h2>${paragraphs(p.body)}</article>`).join("") || `<div class="upd-empty">${box==="dejoiy"?"No updates from the Dejoiy team yet.":mine?"Nothing posted yet. Your first update shows up here for everyone.":"Nothing posted yet."}</div>`}</div></div>`;
    const form = el.querySelector("#upd-form");
    if(form) form.addEventListener("submit", async ev=>{
      ev.preventDefault(); const button=form.querySelector("button"); button.disabled=true;
      try{ draw(await send({box, op:"post", title:form.elements.title.value, body:form.elements.body.value})); App.toast("Update posted."); }
      catch(error){ App.toast(error.message); button.disabled=false; }
    });
    el.querySelectorAll("[data-del]").forEach(b=>b.addEventListener("click", ()=> App.confirm("Delete this update for everyone?", async ()=>{
      try{ draw(await send({box, op:"delete", id:b.dataset.del})); }catch(error){ App.toast(error.message); }
    })));
  }
};
})();
