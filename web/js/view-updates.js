/* ============ Dejoiy Mail — view-updates.js : Dejoiy Updates and the company box ============
   Dejoiy Updates: posts from the Dejoiy team (news, features, policies, notices), seen by every mailbox.
   Company box: posts from people whose role allows it, seen only inside their company.
   Posts are cards: a pinned hero, then a grid. Each can carry a link and up to 6 files. */
(function(){
"use strict";

const KINDS = {
  news:{label:"News", emoji:"📣"}, feature:{label:"New feature", emoji:"✨"}, policy:{label:"Policy", emoji:"📜"},
  notice:{label:"Notice", emoji:"🔔"}, tip:{label:"Tip", emoji:"💡"}, event:{label:"Event", emoji:"🎉"}
};
const BOX = {
  dejoiy:{title:"Dejoiy Updates", lede:"News, features and policies from the Dejoiy team."},
  company:{lede:"Updates for everyone in your company."}
};
const MAX_FILES = 6, MAX_BYTES = 10*1024*1024;
/* Where a Dejoiy Update shows: inside mailboxes, on the public home pages, or both. */
const AUDIENCES = {internal:["📬","Inside mailboxes"], external:["🌐","Home pages only"], both:["✨","Mailboxes + home pages"]};
const ago = ms => { const m=Math.round((Date.now()-ms)/60000);
  return m<1?"just now":m<60?m+" min ago":m<1440?Math.round(m/60)+" h ago":new Date(ms).toLocaleDateString([], {day:"numeric", month:"short", year:"numeric"}); };
const size = n => n<1024?n+" B":n<1048576?Math.round(n/1024)+" KB":(n/1048576).toFixed(1)+" MB";
const paragraphs = text => esc(text).split(/\n{2,}/).map(p=>`<p>${p.replace(/\n/g,"<br>")}</p>`).join("");
const fileUrl = f => f.url || "/api/updates/file?id="+encodeURIComponent(f.id);
const fileIcon = name => ({pdf:"📕", doc:"📘", docx:"📘", xls:"📗", xlsx:"📗", csv:"📗", ppt:"📙", pptx:"📙", zip:"🗜️", txt:"📄", mp4:"🎬", mp3:"🎵"})[String(name).split(".").pop().toLowerCase()] || "📎";
const safeLink = url => /^(https:\/\/|\/)/.test(url||"") ? url : "#";

/* Demo mode keeps posts on this device so the pages can be tried without a server. */
const demo = {
  get(){ const s=Store.state; s.updates = s.updates || {dejoiy:[
      {id:"d1",kind:"news",pinned:true,title:"Welcome to Dejoiy Mail :D",body:"News, features and policies from the Dejoiy team show up here.",author:"Dejoiy team",date:Date.now()-36e5,files:[]},
      {id:"d2",kind:"policy",title:"Our Terms of Service",body:"Plans, billing, what you may not send, and who owns your mail.",link:{url:"/terms",label:"Read the Terms"},author:"Dejoiy team",date:Date.now()-72e5,files:[]},
      {id:"d3",kind:"policy",title:"Privacy Policy",body:"What we collect and why. We don't sell your data or show ads.",link:{url:"/privacy",label:"Read the Privacy Policy"},author:"Dejoiy team",date:Date.now()-8e6,files:[]},
      {id:"d4",kind:"feature",title:"Every mail now has a colour",body:"Labels colour your mail cards, in the list and when you open them.",author:"Dejoiy team",date:Date.now()-9e6,files:[]}],company:[]};
    return {dejoiy:s.updates.dejoiy, company:{name:"Company updates", posts:s.updates.company}, can:{dejoiy:true, company:true}}; },
  post(data){ const s=Store.state.updates; let list=s[data.box];
    if(data.op==="post") list.unshift({id:"u"+Date.now(), kind:data.kind, title:data.title, body:data.body, link:data.link||null, author:Store.state.user?.name||"You", date:Date.now(),
      files:(data.files||[]).map((f,i)=>({id:"f"+Date.now()+i, name:f.name, size:f.size, image:/^image\/(png|jpe?g|gif|webp)$/.test(f.type), url:"data:"+(f.type||"application/octet-stream")+";base64,"+f.data}))});
    else if(data.op==="pin") list=list.map(p=>({...p, pinned:p.id===data.id && !p.pinned}));
    else list=list.filter(p=>p.id!==data.id);
    s[data.box]=list; Store.save(); return demo.get(); }
};
const load = ()=> window.Live?.enabled ? Live.request("updates") : Promise.resolve(demo.get());
const send = data => window.Live?.enabled ? Live.request("updates", data) : Promise.resolve(demo.post(data));
const readFile = file => new Promise((ok,fail)=>{ const r=new FileReader(); r.onload=()=>ok(String(r.result).split(",")[1]||""); r.onerror=()=>fail(new Error("Couldn't read "+file.name)); r.readAsDataURL(file); });

Views.updates = function(el, box){
  const route = box==="dejoiy" ? "news" : "company";
  let view = null, filter = "all", picked = [], kind = "news", audience = "both", composing = false;
  el.innerHTML = `<div class="upd"><div class="upd-skel" aria-hidden="true"><i></i><i></i><i></i></div></div>`;
  load().then(v=>{ if(App.route!==route) return; view=v; App.companyName=v.company?.name; App.refreshNav(); draw(); })
    .catch(error=>{ el.innerHTML = `<div class="empty-note">${esc(error.message)}</div>`; });

  const files = (post, cover) => {
    const images = (post.files||[]).filter(f=>f.image), others = (post.files||[]).filter(f=>!f.image);
    const rest = cover ? images.slice(1) : images;
    return (rest.length?`<div class="upd-thumbs">${rest.map(f=>`<a href="${esc(fileUrl(f))}" target="_blank" rel="noopener"><img src="${esc(fileUrl(f))}" alt="${esc(f.name)}" loading="lazy"></a>`).join("")}</div>`:"")
      + (others.length?`<div class="upd-files">${others.map(f=>`<a class="upd-file" href="${esc(fileUrl(f))}" download="${esc(f.name)}"><span>${fileIcon(f.name)}</span><b>${esc(f.name)}</b><small>${size(f.size||0)}</small></a>`).join("")}</div>`:"");
  };
  const card = (post, i, hero) => {
    const k = KINDS[post.kind] ? post.kind : "news", K = KINDS[k], cover = (post.files||[]).find(f=>f.image), mine = view.can[box];
    const long = !hero && String(post.body).length > 260;
    return `<article class="upd-card${hero?" upd-hero":""}" data-kind="${k}" style="--i:${Math.min(i,8)}">
      ${cover ? `<a class="upd-cover is-photo" href="${esc(fileUrl(cover))}" target="_blank" rel="noopener"><img src="${esc(fileUrl(cover))}" alt="${esc(cover.name)}" loading="lazy"></a>`
        : post.photo ? `<figure class="upd-cover is-photo"><img src="/api/public/photo/${encodeURIComponent(post.photo.id)}" alt="" loading="lazy" onerror="this.parentNode.classList.add('is-gone')">
            <span class="upd-sticker">${K.emoji}</span><figcaption><a href="${esc(post.photo.page)}" target="_blank" rel="noopener">Photo${post.photo.credit?" by "+esc(post.photo.credit):""} · Unsplash</a></figcaption></figure>`
        : `<div class="upd-cover" aria-hidden="true"><span class="upd-sticker">${K.emoji}</span><i></i><i></i><i></i></div>`}
      <div class="upd-body">
        <div class="upd-tags"><span class="upd-kind">${K.emoji} ${K.label}</span>${post.pinned?`<span class="upd-pin">📌 Pinned</span>`:""}${box==="dejoiy"&&mine?`<span class="upd-aud">${AUDIENCES[post.audience||"both"].join(" ")}</span>`:""}</div>
        <h2>${esc(post.title)}</h2>
        <div class="upd-text${long?" is-clamped":""}">${paragraphs(post.body)}</div>
        ${long?`<button class="upd-more" type="button">Read more</button>`:""}
        ${files(post, !!cover)}
        ${post.link?`<a class="upd-link" href="${esc(safeLink(post.link.url))}" ${/^https:/.test(post.link.url)?'target="_blank" rel="noopener"':""}>${esc(post.link.label||"Open link")} <span aria-hidden="true">→</span></a>`:""}
        <footer class="upd-meta"><span class="upd-av" aria-hidden="true">${esc((post.author||"?").trim()[0]||"?").toUpperCase()}</span>
          <span><b>${esc(post.author||"")}</b><small>${esc(ago(post.date))}</small></span>
          ${mine?`<span class="upd-acts"><button class="icon-btn sm" data-pin="${esc(post.id)}" aria-label="${post.pinned?"Unpin":"Pin to the top"}" title="${post.pinned?"Unpin":"Pin to the top"}">📌</button>
            <button class="icon-btn sm" data-del="${esc(post.id)}" aria-label="Delete this update" title="Delete">${Icons.get("trash")}</button></span>`:""}</footer>
      </div></article>`;
  };

  function draw(){
    const posts = box==="dejoiy" ? view.dejoiy : view.company.posts, mine = view.can[box];
    const title = box==="dejoiy" ? BOX.dejoiy.title : view.company.name;
    const counts = Object.fromEntries(Object.keys(KINDS).map(k=>[k, posts.filter(p=>(p.kind||"news")===k).length]));
    const shown = posts.filter(p=>filter==="all" || (p.kind||"news")===filter);
    const hero = filter==="all" ? (shown.find(p=>p.pinned) || shown[0]) : null, grid = shown.filter(p=>p!==hero);
    el.innerHTML = `<div class="upd upd-${box}">
      <header class="upd-head"><span class="upd-badge">${Icons.get(box==="dejoiy"?"megaphone":"building")}</span>
        <div><h1>${esc(title)}</h1><p>${esc(BOX[box].lede)}</p></div>
        ${mine?`<button class="upd-new-btn" id="upd-open" type="button" aria-expanded="${composing}">${composing?"Close":"＋ New update"}</button>`:""}</header>
      ${mine && composing ? composer() : ""}
      <div class="upd-filters" role="radiogroup" aria-label="Show">
        ${[["all","All",posts.length], ...Object.entries(KINDS).filter(([k])=>counts[k]).map(([k,K])=>[k,K.emoji+" "+K.label,counts[k]])]
          .map(([k,label,n])=>`<button type="button" role="radio" class="chip-filter" data-filter="${k}" aria-checked="${filter===k}">${esc(label)} <b>${n}</b></button>`).join("")}
      </div>
      ${hero ? card(hero, 0, true) : ""}
      <div class="upd-grid">${grid.map((p,i)=>card(p, i+1, false)).join("")}</div>
      ${!posts.length?`<div class="upd-empty"><span>${box==="dejoiy"?"📣":"🏢"}</span>${box==="dejoiy"?"No updates from the Dejoiy team yet.":mine?"Nothing posted yet. Your first update shows up here for everyone in your company.":"Nothing posted yet."}</div>`:""}
    </div>`;
    wire();
  }

  function composer(){
    return `<form class="upd-compose" id="upd-form" novalidate>
      <div class="upd-kinds" role="radiogroup" aria-label="Type of update">${Object.entries(KINDS).map(([k,K])=>
        `<button type="button" role="radio" class="upd-kind-pick" data-kind="${k}" aria-checked="${kind===k}">${K.emoji} ${K.label}</button>`).join("")}</div>
      ${box==="dejoiy"?`<div class="upd-kinds upd-auds" role="radiogroup" aria-label="Where it shows"><span class="upd-auds-lab">Show on</span>${Object.entries(AUDIENCES).map(([k,[e,l]])=>
        `<button type="button" role="radio" class="upd-kind-pick" data-aud="${k}" aria-checked="${audience===k}">${e} ${l}</button>`).join("")}</div>`:""}
      <input name="title" maxlength="120" placeholder="Title" required aria-label="Title">
      <textarea name="body" maxlength="4000" rows="4" placeholder="What should everyone know?" required aria-label="Update text"></textarea>
      <div class="upd-row"><input name="url" type="url" inputmode="url" placeholder="Link (optional), https://…" aria-label="Link"><input name="label" maxlength="40" placeholder="Button text" aria-label="Link button text"></div>
      <div class="upd-picked" id="upd-picked">${picked.map((f,i)=>`<span class="upd-chip">${/^image\//.test(f.type)?"🖼️":fileIcon(f.name)} ${esc(f.name)} <small>${size(f.size)}</small><button type="button" data-unpick="${i}" aria-label="Remove ${esc(f.name)}">×</button></span>`).join("")}</div>
      <p class="upd-error" role="alert"></p>
      <div class="upd-compose-foot">
        <label class="upd-attach">📎 Add files<input type="file" id="upd-files" multiple class="sr"></label>
        <span class="upd-who">${box==="dejoiy"?{internal:"Shows inside every Dejoiy Mail mailbox",external:"Shows only on mail.dejoiy.com/home and the admin home page",both:"Shows inside every mailbox and on the home pages"}[audience]:"Posting to everyone at "+esc(view.company.domain||"your company")}</span>
        <button class="upd-post-btn">Post update</button></div>
    </form>`;
  }

  function wire(){
    el.querySelector("#upd-open")?.addEventListener("click",()=>{ composing=!composing; draw(); if(composing) el.querySelector("#upd-form [name=title]")?.focus(); });
    el.querySelectorAll("[data-filter]").forEach(b=>b.addEventListener("click",()=>{ filter=b.dataset.filter; draw(); }));
    el.querySelectorAll(".upd-more").forEach(b=>b.addEventListener("click",()=>{ const t=b.previousElementSibling; t.classList.toggle("is-clamped"); b.textContent=t.classList.contains("is-clamped")?"Read more":"Show less"; }));
    el.querySelectorAll("[data-del]").forEach(b=>b.addEventListener("click",()=>App.confirm("Delete this update for everyone?", async ()=>{
      try{ view=await send({box, op:"delete", id:b.dataset.del}); draw(); }catch(error){ App.toast(error.message); } })));
    el.querySelectorAll("[data-pin]").forEach(b=>b.addEventListener("click", async ()=>{
      try{ view=await send({box, op:"pin", id:b.dataset.pin}); draw(); }catch(error){ App.toast(error.message); } }));
    const form = el.querySelector("#upd-form"); if(!form) return;
    const err = form.querySelector(".upd-error");
    // Keep what was typed when the form redraws (picking a kind or files).
    const keep = ()=>({title:form.elements.title.value, body:form.elements.body.value, url:form.elements.url.value, label:form.elements.label.value});
    const restore = v=>{ const f=el.querySelector("#upd-form"); for(const k in v) f.elements[k].value=v[k]; };
    form.querySelectorAll("[data-kind]").forEach(b=>b.addEventListener("click",()=>{ const v=keep(); kind=b.dataset.kind; draw(); restore(v); }));
    form.querySelectorAll("[data-aud]").forEach(b=>b.addEventListener("click",()=>{ const v=keep(); audience=b.dataset.aud; draw(); restore(v); }));
    form.querySelectorAll("[data-unpick]").forEach(b=>b.addEventListener("click",()=>{ const v=keep(); picked.splice(+b.dataset.unpick,1); draw(); restore(v); }));
    form.querySelector("#upd-files").addEventListener("change", ev=>{
      const v=keep(), add=[...ev.target.files];
      if(picked.length+add.length>MAX_FILES){ err.textContent=`Attach up to ${MAX_FILES} files.`; return; }
      if([...picked,...add].reduce((n,f)=>n+f.size,0)>MAX_BYTES){ err.textContent="Files must total 10 MB or less."; return; }
      picked.push(...add); draw(); restore(v);
    });
    form.addEventListener("submit", async ev=>{
      ev.preventDefault(); err.textContent="";
      const v=keep(); if(!v.title.trim() || !v.body.trim()){ err.textContent="Add a title and some text."; return; }
      if(v.url && !/^https:\/\//.test(v.url.trim())){ err.textContent="Links must start with https://"; return; }
      const button=form.querySelector(".upd-post-btn"); button.disabled=true; button.textContent=picked.length?"Uploading…":"Posting…";
      try{
        const files = await Promise.all(picked.map(async f=>({name:f.name, type:f.type, size:f.size, data:await readFile(f)})));
        view = await send({box, op:"post", kind, audience, title:v.title, body:v.body, link:v.url.trim()?{url:v.url.trim(), label:v.label}:null, files});
        picked=[]; composing=false; filter="all"; draw(); App.toast("Update posted.");
      }catch(error){ err.textContent=error.message; button.disabled=false; button.textContent="Post update"; }
    });
  }
};
})();
