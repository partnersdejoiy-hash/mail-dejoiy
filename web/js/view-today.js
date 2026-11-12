/* ============ Dejoiy Mail — view-today.js : Home ============
   The first page of the day, like AOL's "Today" but without ads or outside news: how much mail is
   waiting, what Dejoiy and your company posted (a strip of cards), and your newest unread mail. */
(function(){
"use strict";

Views.today = function(el){
  const s = Store.state, c = Mail.counts(), live = !!window.Live?.enabled;
  const hr = new Date().getHours();
  const greet = hr<12 ? "Good morning" : hr<17 ? "Good afternoon" : "Good evening";
  const todayStr = new Date().toLocaleDateString([], {weekday:"long", day:"numeric", month:"long"});
  const first = String(s.user?.name||"").split(" ")[0] || "there";
  const unread = Mail.threadList("inbox").filter(e=>e.unreadCount>0).slice(0,5);

  el.innerHTML = `<div class="home">
    <header class="home-head">
      <div><h1>${greet}, ${esc(first)}</h1><p>${esc(todayStr)}</p></div>
      <button class="home-unread" data-go="mail:inbox"><b>${c.unread||0}</b><span>unread ${c.unread===1?"message":"messages"}</span><i aria-hidden="true">${Icons.get("next")}</i></button>
    </header>

    <section aria-labelledby="home-upd-h">
      <div class="home-row"><h2 id="home-upd-h">What's new</h2>
        <div class="home-arrows"><button class="icon-btn sm" id="home-prev" aria-label="Earlier updates">${Icons.get("back")}</button><button class="icon-btn sm" id="home-next" aria-label="More updates">${Icons.get("next")}</button></div></div>
      <div class="home-strip" id="home-strip" tabindex="0" aria-label="Updates from Dejoiy and your company"><div class="home-card is-skel"></div><div class="home-card is-skel"></div><div class="home-card is-skel"></div></div>
    </section>

    <section aria-labelledby="home-mail-h">
      <div class="home-row"><h2 id="home-mail-h">Waiting for you</h2><button class="btn sm" data-go="mail:unread">All unread</button></div>
      <div class="home-mail">${unread.length ? unread.map(e=>`
        <button class="home-mail-row" data-open="${esc(e.latest.id)}">
          ${Profile.avatar(e.latest.from?.email, e.latest.from?.name, "m-avatar")}
          <span class="hm-main"><b>${esc(e.latest.from?.name||e.latest.from?.email||"")}</b><span>${esc(e.subject||"(no subject)")}</span></span>
          <time>${fmtDate(e.date)}</time>
        </button>`).join("") : `<p class="home-empty">You're all caught up.</p>`}</div>
    </section>

    <p class="home-foot">Want a picture behind your mail? <button class="home-link" id="home-theme">Pick a background</button></p>
  </div>`;

  el.querySelectorAll("[data-go]").forEach(b=> b.addEventListener("click", ()=> App.go(b.dataset.go)));
  el.querySelectorAll("[data-open]").forEach(b=> b.addEventListener("click", ()=>{ const id=b.dataset.open; App.go("mail:inbox");
    setTimeout(()=>{ if(App.ui._mail) App.ui._mail.openTab(id); }, 80); }));
  el.querySelector("#home-theme").addEventListener("click", ()=> document.getElementById("theme-btn")?.click());

  const strip = el.querySelector("#home-strip");
  const step = dir => strip.scrollBy({left: dir*Math.max(280, strip.clientWidth*0.8), behavior: matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth"});
  el.querySelector("#home-prev").addEventListener("click", ()=> step(-1));
  el.querySelector("#home-next").addEventListener("click", ()=> step(1));

  Updates.load().then(v=>{
    if(App.route!=="today") return;
    const company = v.company?.name || "Your company";
    const posts = [...(v.dejoiy||[]).map(p=>({...p, from:"Dejoiy", go:"news"})), ...((v.company?.posts)||[]).map(p=>({...p, from:company, go:"company"}))]
      .sort((a,b)=>(b.pinned?1:0)-(a.pinned?1:0) || b.date-a.date).slice(0,12);
    strip.innerHTML = posts.length ? posts.map(p=>{ const K=Updates.KINDS[p.kind]||Updates.KINDS.news, img=Updates.cover(p);
      return `<button class="home-card" data-kind="${esc(p.kind||"news")}" data-go="${p.go}">
        <span class="hc-cover">${img?`<img src="${esc(img)}" alt="" loading="lazy" onerror="this.remove()">`:""}<span class="hc-emoji" aria-hidden="true">${K.emoji}</span></span>
        <span class="hc-body"><small>${esc(p.from)} · ${K.label}${p.pinned?" · Pinned":""}</small><b>${esc(p.title)}</b><span>${esc(String(p.body||"").slice(0,110))}</span></span>
      </button>`; }).join("") : `<p class="home-empty">No updates yet. Posts from Dejoiy and your company show up here.</p>`;
    strip.querySelectorAll("[data-go]").forEach(b=> b.addEventListener("click", ()=> App.go(b.dataset.go)));
  }).catch(()=>{ if(App.route==="today") strip.innerHTML = `<p class="home-empty">Updates couldn't load right now.</p>`; });
};
})();
