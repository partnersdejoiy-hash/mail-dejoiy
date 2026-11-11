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

/* What the person sees right now, so Joi can read their mail when asked ("check my latest email").
   It stays in this browser and goes only to Joi, with the message they send her. */
const text = html => { const d=document.createElement("div"); d.innerHTML=String(html||""); return (d.textContent||"").replace(/\s+/g," ").trim(); };
const when = ts => { try{ return new Date(ts).toLocaleString(); }catch(_){ return ""; } };
function mailContext(){
  const st=Store.state, me=st.user||{};
  const line=(m,len)=>`- ${when(m.date)} | from ${m.from?.name||""} <${m.from?.email||""}> | to ${(m.to||[]).join(", ")} | "${m.subject||"(no subject)"}"${m.read?"":" [unread]"}${m.hasAttachment?" [attachment]":""}\n  ${text(m.body).slice(0,len)}`;
  const inbox=(st.emails||[]).filter(m=>m.folder==="inbox").sort((a,b)=>b.date-a.date);
  const sent=(st.emails||[]).filter(m=>m.folder==="sent").sort((a,b)=>b.date-a.date);
  const open=window.App?.ui?.activeTab ? Mail.get(App.ui.activeTab) : null;
  const parts=[`Signed in to Dejoiy Mail as ${me.name||""} <${me.email||""}>. Now: ${when(Date.now())}.`];
  if(open) parts.push("THE MAIL THEY HAVE OPEN:\n"+line(open,4000));
  parts.push(`INBOX, newest first (${inbox.length} messages, ${inbox.filter(m=>!m.read).length} unread):\n`+inbox.slice(0,15).map((m,i)=>line(m,i<3?1500:200)).join("\n"));
  if(sent.length) parts.push("RECENTLY SENT:\n"+sent.slice(0,5).map(m=>line(m,200)).join("\n"));
  return parts.join("\n\n").slice(0,12000);
}
function share(){ try{ if(window.Joi?.setContext) Joi.setContext(mailContext()); }catch(_){ } }
addEventListener("hashchange", ()=>{ if(ready) share(); });
setInterval(()=>{ if(ready && document.visibilityState==="visible") share(); }, 30000);

window.JoiDock = {
  avatar: "/assets/brand/joi-avatar.webp?v=7",
  async open(){
    try{ await load(); share(); window.Joi.open(); }
    catch(e){ App.toast(e.message); }
  },
};

document.addEventListener("keydown", e=>{
  if((e.metaKey||e.ctrlKey) && e.key.toLowerCase()==="j" && !e.shiftKey){ e.preventDefault(); JoiDock.open(); }
});
})();
