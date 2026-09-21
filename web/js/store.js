/* ============ Dejoiy Mail — store.js : app state + localStorage persistence ============ */
(function(){
"use strict";

const KEY = "dejoiy-mail-v1";

function uid(p){ return (p||"id") + "-" + Math.random().toString(36).slice(2,9); }

function freshState(){
  const D = window.DemoData;
  return {
    version: 1,
    user: { name: D.ME.name, email: D.ME.email, signature: "Best,\nRoopa\nDejoiy Mail" },
    emails: JSON.parse(JSON.stringify(D.emails)),
    contacts: JSON.parse(JSON.stringify(D.contacts)),
    events: JSON.parse(JSON.stringify(D.events)),
    todos: JSON.parse(JSON.stringify(D.todos)),
    notes: [ {id: uid("n"), title:"Welcome note", body:"This is your notepad — everything saves automatically.", ts: Date.now()} ],
    chats: {},                       // contactId -> [{from:'me'|'them', text, ts}]
    filters: JSON.parse(JSON.stringify(D.defaultFilters)),
    blocked: ["winner@prize-lotto.xyz"],
    allowed: [],
    vacation: { on:false, subject:"Out of office", message:"Thanks for writing — I'm away and will reply when I'm back." },
    prefs: { theme:"aol", brightness:"dark", customBg:"", sounds:true },
    admin: {
      org: "DEJOIY INDIA PRIVATE LIMITED",
      users: [
        {name:"Deepak Sharma", email:"deepak.sharma@dejoiy.com", role:"Super Admin"},
        {name:"Roopa", email:"roopa@dejoiy.com", role:"Admin"},
        {name:"Kavya Rao", email:"kavya@dejoiy.com", role:"User"}
      ],
      domains: [
        {domain:"dejoiy.com", mx:true, spf:false, dkim:true, dmarc:false},
        {domain:"dejoiy.co.in", mx:false, spf:false, dkim:false, dmarc:false}
      ]
    },
    poolIdx: 0
  };
}

function load(){
  try{
    const raw = localStorage.getItem(KEY);
    if(raw){ const s = JSON.parse(raw); if(s && s.version===1) return s; }
  }catch(e){}
  return freshState();
}

const Store = {
  state: load(),
  save(){ try{ localStorage.setItem(KEY, JSON.stringify(this.state)); }catch(e){} },
  reset(){ this.state = freshState(); this.save(); },
  get emails(){ return this.state.emails; }
};

window.Store = Store;
window.Views = window.Views || {};
window.uid = uid;
window.esc = function(s){
  return String(s==null?"":s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
};
window.fmtDate = function(ts){
  const d = new Date(ts), now = new Date();
  const sameDay = d.toDateString()===now.toDateString();
  const yest = new Date(now-864e5).toDateString()===d.toDateString();
  const t = d.toLocaleTimeString([], {hour:"numeric", minute:"2-digit"});
  if(sameDay) return t;
  if(yest) return "Yesterday";
  if(now-d < 7*864e5) return d.toLocaleDateString([], {weekday:"short"}) + ", " + t;
  return d.toLocaleDateString([], {day:"numeric", month:"short"}) + (d.getFullYear()!==now.getFullYear() ? " "+d.getFullYear() : "");
};
window.initials = function(name){
  return String(name||"?").trim().split(/\s+/).slice(0,2).map(w=>w[0]).join("").toUpperCase();
};
})();
