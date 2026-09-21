/* ============ Dejoiy Mail — filters.js : Gmail-style filter engine ============
   A filter has criteria (from/to/subject/words/size/date/attachment) and actions.
   Filters run on demand ("Run filters now") over the inbox, and on newly arrived mail. */
(function(){
"use strict";

function norm(s){ return String(s||"").toLowerCase(); }
function contains(hay, needle){ return norm(hay).includes(norm(needle)); }

const Filters = {
  blank(){
    return { id: uid("f"), name:"Untitled filter", on:true,
      criteria:{from:"",to:"",subject:"",hasWords:"",noWords:"",larger:"",smaller:"",after:"",before:"",hasAttachment:false},
      actions:{archive:false,markRead:false,star:false,label:"",forwardTo:"",delete:false,neverSpam:false,important:false,category:""} };
  },

  /* true if the email satisfies ALL non-empty criteria */
  matches(em, f){
    const c = f.criteria;
    if(c.from && !contains(em.from.email+" "+em.from.name, c.from)) return false;
    if(c.to && !(em.to||[]).some(t=>contains(t, c.to))) return false;
    if(c.subject && !contains(em.subject, c.subject)) return false;
    const hay = em.subject+" "+stripTags(em.body)+" "+em.from.email+" "+em.from.name;
    if(c.hasWords && !c.hasWords.split(/\s+/).every(w=>contains(hay,w))) return false;
    if(c.noWords && c.noWords.split(/\s+/).some(w=>contains(hay,w))) return false;
    if(c.hasAttachment && !em.hasAttachment) return false;
    const size = (em.attachments||[]).reduce((a,x)=>a+parseSize(x.size), 0);
    if(c.larger && !(size > parseSize(c.larger))) return false;
    if(c.smaller && !(size < parseSize(c.smaller))) return false;
    if(c.after && !(em.date >= new Date(c.after).getTime())) return false;
    if(c.before && !(em.date <= new Date(c.before).getTime()+864e5)) return false;
    return true;
  },

  /* apply a filter's actions to one email; returns list of applied action names */
  applyTo(em, f){
    const a = f.actions, done = [];
    if(a.delete){ em.folder = em.folder==="trash" ? em.folder : "trash"; done.push("deleted"); return done; }
    if(a.archive){ em.folder = "archive"; done.push("archived"); }
    if(a.markRead){ em.read = true; done.push("marked read"); }
    if(a.star){ em.starred = true; done.push("starred"); }
    if(a.important){ em.important = true; done.push("marked important"); }
    if(a.label){ em.labels = em.labels||[]; if(!em.labels.includes(a.label)){ em.labels.push(a.label); } done.push("labelled "+a.label); }
    if(a.category){ em.labels = em.labels||[]; if(!em.labels.includes(a.category)){ em.labels.push(a.category); } done.push("categorised"); }
    if(a.neverSpam && em.folder==="spam"){ em.folder = "inbox"; done.push("never spam"); }
    if(a.forwardTo){
      const copy = JSON.parse(JSON.stringify(em));
      copy.id = uid("m"); copy.from = {name:Store.state.user.name, email:Store.state.user.email};
      copy.to = [a.forwardTo]; copy.folder = "sent"; copy.date = Date.now(); copy.read = true;
      Store.state.emails.push(copy); done.push("forwarded to "+a.forwardTo);
    }
    return done;
  },

  /* run all enabled filters over the given emails (default: inbox). Returns {matched, actions} */
  runAll(emails){
    const list = (emails||Store.state.emails).filter(e=>e.folder==="inbox");
    let matched = 0, log = [];
    Store.state.filters.filter(f=>f.on).forEach(f=>{
      list.forEach(em=>{
        if(this.matches(em, f)){ matched++; log.push({filter:f.name, subject:em.subject, did:this.applyTo(em,f)}); }
      });
    });
    if(matched) Store.save();
    return {matched, log};
  }
};

function stripTags(h){ const d=document.createElement("div"); d.innerHTML=h||""; return d.textContent||""; }
function parseSize(s){
  if(typeof s==="number") return s;
  const m = String(s||"").match(/([\d.]+)\s*(KB|MB|GB|B)?/i); if(!m) return 0;
  const n = parseFloat(m[1]), u = (m[2]||"B").toUpperCase();
  return n * (u==="GB"?1e9 : u==="MB"?1e6 : u==="KB"?1e3 : 1);
}

window.Filters = Filters;
})();
