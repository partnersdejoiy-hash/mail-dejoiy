/* ============ Dejoiy Mail — presence.js : Active / Away dots and written status, shared with Shine ============
   Like Gmail: a green dot when a colleague is Active, amber when Away, red for Do not disturb, nothing when offline.
   Like WhatsApp: a short written status under their name. Both live in Shine, so the two apps always agree.
   Any avatar Profile.avatar() draws gets a dot; any element with data-ps="email" gets that person's status text. */
(function(){
"use strict";

const IDLE_MS = 5*60e3, BEAT_MS = 45e3, STALE_MS = 60e3;
const LABEL = {online:"Active", away:"Away", busy:"Do not disturb", offline:"Offline"};
const CHOICES = [
  ["auto","Automatic","Active, or Away after 5 minutes idle"],
  ["busy","Do not disturb","Colleagues see you're busy"],
  ["away","Set as away","Show Away even when you're here"],
  ["invisible","Appear offline","Others see you as offline"],
];
const PRESETS = ["Available","📅 In a meeting","📞 On a call","🏡 Working from home","🎯 Focusing","🚗 Commuting","🤒 Out sick","🌴 On leave"];

const cache = new Map();      // email -> {status, text, at}
let enabled = null;           // null = not known yet, false = Shine not connected for this mailbox
let mine = {choice:"auto", text:""};
let lastInput = Date.now(), wasIdle = false, pending = null;

const me = ()=> String(Store.state.user.email||"").toLowerCase();
const idle = ()=> document.hidden || Date.now()-lastInput > IDLE_MS;
const shownAs = (choice, isIdle)=> choice==="invisible" ? "offline" : choice==="busy" ? "busy" : (choice==="away"||isIdle) ? "away" : "online";

function remember(r, isIdle){
  enabled = !!r.enabled;
  if(!r.enabled) return;
  mine = {choice:r.choice||"auto", text:r.text||""};
  cache.set(me(), {status:shownAs(mine.choice, isIdle), text:mine.text, at:Date.now()});
  paint(true);
}

const Presence = {
  get enabled(){ return enabled; },
  get mine(){ return mine; },
  label(email){ return LABEL[(cache.get(String(email||"").toLowerCase())||{}).status||"offline"]; },

  /* the dot inside an avatar */
  dot(email){ return email ? `<i class="pres-dot" data-pe="${esc(String(email).toLowerCase())}" aria-hidden="true"></i>` : ""; },

  async beat(extra){
    if(!window.Live?.enabled || enabled===false) return;
    const isIdle = idle(); wasIdle = isIdle;
    try{ remember(await Live.request("presence", {idle:isIdle, ...(extra||{})}), isIdle); }catch(_){ /* Shine unreachable: try again next beat */ }
  },

  async set(change){
    const r = await Live.request("presence", {idle:idle(), ...change});
    if(!r.enabled) throw new Error("Status needs Shine to be connected to your mailbox.");
    remember(r, idle());
    return mine;
  },

  /* your status and presence, from the account menu */
  open(){
    const body = `<div class="pres-sheet">
        <label class="field"><span>Status</span>
          <div class="pres-input"><input id="ps-text" maxlength="140" placeholder="What's your status?" value="${esc(mine.text)}"><button type="button" class="icon-btn sm" id="ps-clear" aria-label="Clear status">×</button></div></label>
        <div class="pres-presets">${PRESETS.map(p=>`<button type="button" data-preset="${esc(p)}" class="${mine.text===p?"on":""}">${esc(p)}</button>`).join("")}</div>
        <fieldset class="pres-choices"><legend>Show me as</legend>
          ${CHOICES.map(([v,l,h])=>`<label><input type="radio" name="ps-choice" value="${v}" ${mine.choice===v?"checked":""}>
            <i class="pres-dot" data-state="${shownAs(v,false)}"></i><span><b>${l}</b><small>${h}</small></span></label>`).join("")}
        </fieldset>
        <p class="pres-note">Colleagues see this in Dejoiy Mail and in Shine.</p></div>`;
    App.dialog({title:"Your status", body, actions:[{label:"Cancel"},{label:"Save", primary:true, fn:()=>{
      const text=document.getElementById("ps-text").value.trim(), choice=document.querySelector('input[name="ps-choice"]:checked')?.value||"auto";
      Presence.set({text, choice}).then(()=>{ App.toast(text?"Status updated.":"Status saved."); App.refreshNav?.(); }).catch(e=>App.toast(e.message));
    }}]});
    const input=document.getElementById("ps-text");
    document.getElementById("ps-clear").addEventListener("click", ()=>{ input.value=""; input.focus(); });
    document.querySelectorAll("[data-preset]").forEach(b=> b.addEventListener("click", ()=>{
      input.value=b.dataset.preset; document.querySelectorAll("[data-preset]").forEach(x=>x.classList.toggle("on", x===b)); }));
  },
};

/* Fill every dot and status line on the page; fetch people we don't know yet (or not lately) in one batch. */
async function paint(onlyCached){
  const dots=[...document.querySelectorAll("[data-pe]")], lines=[...document.querySelectorAll("[data-ps]")];
  if(!dots.length && !lines.length) return;
  if(!onlyCached && window.Live?.enabled && enabled!==false){
    const want=[...new Set([...dots.map(d=>d.dataset.pe), ...lines.map(l=>l.dataset.ps)])]
      .filter(e=>e && e!==me() && (!cache.has(e) || Date.now()-cache.get(e).at > STALE_MS)).slice(0,200);
    if(want.length){
      try{
        const r=await Live.request("people-status", {emails:want});
        if(r.enabled===false) enabled=false;
        const now=Date.now();
        want.forEach(e=> cache.set(e, {...(r.people?.[e]||{status:"offline", text:""}), at:now}));
      }catch(_){}
    }
  }
  dots.forEach(d=>{ const p=cache.get(d.dataset.pe); d.dataset.state=p?.status||"offline"; d.title=p?LABEL[p.status]||"":""; });
  lines.forEach(l=>{ const p=cache.get(l.dataset.ps); l.textContent=p?.text||""; l.hidden=!p?.text; });
}
const schedule = ()=>{ clearTimeout(pending); pending=setTimeout(()=>paint(false), 250); };

document.addEventListener("DOMContentLoaded", ()=>{
  new MutationObserver(muts=>{ if(muts.some(m=>m.addedNodes.length)) schedule(); }).observe(document.body, {childList:true, subtree:true});
  ["pointerdown","keydown","wheel","touchstart"].forEach(t=> window.addEventListener(t, ()=>{
    lastInput=Date.now(); if(wasIdle && !document.hidden) Presence.beat(); }, {passive:true}));
  document.addEventListener("visibilitychange", ()=>Presence.beat());
  setInterval(()=>Presence.beat(), BEAT_MS);
  setInterval(()=>paint(false), STALE_MS);
});

window.Presence = Presence;
})();
