/* ============ Dejoiy Mail — android-links.js ============
   The Android apps (android/mail, android/admin) each keep to their own site. Inside an app, a link to
   the other Dejoiy site is handed to Android, which opens it in the other app when it is installed and
   in the browser otherwise, instead of a browser bar inside this app. In a normal browser nothing changes.
   We are in an app when it started us (?source=android, or an android-app:// referrer); remembered for the tab. */
(function(){
"use strict";
const SITES = ["mail.dejoiy.com", "admin-mail.dejoiy.com"];
let inApp = false;
try{
  if(new URLSearchParams(location.search).get("source")==="android" || String(document.referrer).startsWith("android-app://")) sessionStorage.setItem("dm-android","1");
  inApp = sessionStorage.getItem("dm-android")==="1";
}catch(_){ inApp = String(document.referrer).startsWith("android-app://"); }

/* The other Dejoiy site's address, or null for anything else (this site, other sites, non-https). */
function otherSite(url){
  try{ const u = new URL(url, location.href); return u.protocol==="https:" && u.host!==location.host && SITES.includes(u.host) ? u : null; }
  catch(_){ return null; }
}
/* Android picks the app for the address (no package named), and the browser opens the address when no app takes it. */
function intentUrl(u){
  return "intent://"+u.host+u.pathname+u.search+u.hash+"#Intent;scheme=https;S.browser_fallback_url="+encodeURIComponent(u.href)+";end";
}
window.DejoiyLinks = {
  inApp: ()=>inApp,
  intentUrl: url=>{ const u = otherSite(url); return u ? intentUrl(u) : null; },
  /* For code that moves to another page: true when the app handed it to Android. */
  open(url){ const u = inApp && otherSite(url); if(!u) return false; location.href = intentUrl(u); return true; }
};
if(inApp) document.addEventListener("click", e=>{
  const a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
  const u = a && otherSite(a.href); if(!u) return;
  e.preventDefault(); e.stopPropagation(); location.href = intentUrl(u);
}, true);
})();
