/* ============ Dejoiy Mail — joi-dock.js : Joi, DEJOIY's AI buddy, as the mail assistant ============
   The Joi button opens her chat panel: Joi's own one-line embed (joi.js) for the "mail" app.
   The server says where Joi lives and, for DEJOIY's own people, hands a token so she may use
   DEJOIY's internal memory. Her answers come from the Joi server once that is set up. */
(function(){
"use strict";

let ready = null;
async function load(){
  if(ready) return ready;
  ready = (async()=>{
    const cfg = window.Live?.enabled ? await Live.request("joi").catch(()=>({})) : {};
    const url = (cfg.url || "https://joi-ai.dejoiy.com").replace(/\/+$/,"");
    await new Promise((resolve,reject)=>{
      const s=document.createElement("script"); s.src=url+"/joi.js"; s.async=true;
      Object.assign(s.dataset,{app:"mail", api:cfg.api||url, launcher:"none"});
      const u=Store.state.user||{}; if(u.name) s.dataset.userName=u.name; if(u.email) s.dataset.userEmail=u.email;
      s.onload=resolve; s.onerror=()=>reject(new Error("Joi can't be reached right now. Try again in a bit."));
      document.body.appendChild(s);
    });
    // joi.js builds her panel after reading the app's settings
    for(let i=0;i<60 && !document.querySelector(".joi-w");i++) await new Promise(r=>setTimeout(r,100));
    if(!document.querySelector(".joi-w") || !window.Joi) throw new Error("Joi can't be reached right now. Try again in a bit.");
    if(cfg.token) window.Joi.setAppToken(cfg.token);
    return true;
  })();
  ready.catch(()=>{ ready=null; });
  return ready;
}

window.JoiDock = {
  avatar: "/assets/brand/joi-avatar.webp?v=4",
  async open(){
    try{ await load(); window.Joi.open(); }
    catch(e){ App.toast(e.message); }
  },
};

document.addEventListener("keydown", e=>{
  if((e.metaKey||e.ctrlKey) && e.key.toLowerCase()==="j" && !e.shiftKey){ e.preventDefault(); JoiDock.open(); }
});
})();
