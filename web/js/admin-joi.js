/* ============ Dejoiy Mail Admin — admin-joi.js : Joi as the admin's helper ============
   The "Ask Joi" button loads Joi's own embed (joi.js) for the "mail-admin" app: on her server that app is a
   Dejoiy Mail admin guide (how to do things in this console, plans, roles, DNS, outgoing mail). She is told
   which page is open and which company, never any mailbox content. */
(function(){
"use strict";
let ready = null;
async function load(){
  if(ready) return ready;
  ready = (async()=>{
    let cfg = {};
    try{ const r = await fetch("/api/joi?app=admin", {credentials:"same-origin"}); if(r.ok) cfg = await r.json(); }catch(_){}
    const url = (cfg.url || "https://joi-ai.dejoiy.com").replace(/\/+$/,"");
    await new Promise((resolve,reject)=>{
      const s=document.createElement("script"); s.src=url+"/joi.js"; s.async=true;
      Object.assign(s.dataset,{app:"mail-admin", api:cfg.api||url, launcher:"none"});
      s.onload=resolve; s.onerror=()=>reject(new Error("Joi can't be reached right now. Try again in a bit."));
      document.body.appendChild(s);
    });
    for(let i=0;i<60 && !document.querySelector(".joi-w");i++) await new Promise(r=>setTimeout(r,100));
    if(!document.querySelector(".joi-w") || !window.Joi) throw new Error("Joi can't be reached right now. Try again in a bit.");
    if(cfg.token) window.Joi.setAppToken(cfg.token);
    return true;
  })();
  ready.catch(()=>{ ready=null; });
  return ready;
}
// what the admin is looking at: the page and the company, nothing from anyone's mailbox
function context(){
  const who = document.getElementById("adm-who")?.textContent || "";
  const crumb = document.getElementById("adm-crumb")?.textContent || "";
  const head = document.querySelector("#adm-main h1")?.textContent || "";
  return `Dejoiy Mail Admin console (admin-mail.dejoiy.com). Signed in: ${who}. Open page: ${crumb || head} (${location.pathname}). Now: ${new Date().toLocaleString()}.`;
}
function share(){ try{ if(window.Joi?.setContext) Joi.setContext(context()); }catch(_){} }
addEventListener("popstate", ()=>{ if(ready) share(); });
document.addEventListener("click", e=>{ if(ready && e.target.closest?.("a[href^='/admin/']")) setTimeout(share, 300); });
document.getElementById("adm-joi")?.addEventListener("click", async ()=>{
  try{ await load(); share(); window.Joi.open(); }
  catch(e){ const t=document.createElement("div"); t.className="adm-toast"; t.textContent=e.message; document.getElementById("adm-toasts")?.appendChild(t); setTimeout(()=>t.remove(),3800); }
});
})();
