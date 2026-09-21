/* ============ Dejoiy Mail — mail.js : mailbox operations ============ */
(function(){
"use strict";

const FOLDERS = [
  {id:"inbox",   name:"Inbox",   ico:"📥"},
  {id:"starred", name:"Starred", ico:"⭐", view:true},
  {id:"sent",    name:"Sent",    ico:"📤"},
  {id:"drafts",  name:"Drafts",  ico:"📝"},
  {id:"archive", name:"Archive", ico:"🗄️"},
  {id:"spam",    name:"Spam",    ico:"🚫"},
  {id:"trash",   name:"Trash",   ico:"🗑️"}
];
const SMART = [
  {id:"unread", name:"Unread", ico:"✉️", fn: e=>!e.read && !["trash","spam"].includes(e.folder)},
  {id:"starredv", name:"Starred", ico:"⭐", fn: e=>e.starred && e.folder!=="trash"},
  {id:"attach", name:"Has attachments", ico:"📎", fn: e=>e.hasAttachment && e.folder!=="trash"},
  {id:"important", name:"Important", ico:"❗", fn: e=>e.important && e.folder!=="trash"}
];

const Mail = {
  FOLDERS, SMART,
  folderName(id){
    const f = FOLDERS.find(f=>f.id===id) || SMART.find(f=>f.id===id);
    return f ? f.name : id;
  },

  list(folder){
    const all = Store.state.emails;
    const smart = SMART.find(s=>s.id===folder);
    let r = smart ? all.filter(smart.fn)
          : folder==="starred" ? all.filter(e=>e.starred && e.folder!=="trash")
          : all.filter(e=>e.folder===folder);
    const q = (App.ui.search||"").trim().toLowerCase();
    if(q) r = r.filter(e => (e.subject+" "+e.from.name+" "+e.from.email+" "+strip(e.body)).toLowerCase().includes(q));
    return r.sort((a,b)=>b.date-a.date);
  },

  get(id){ return Store.state.emails.find(e=>e.id===id); },

  counts(){
    const all = Store.state.emails, c = {};
    FOLDERS.forEach(f=>{ c[f.id] = all.filter(e=> f.id==="starred" ? (e.starred&&e.folder!=="trash") : e.folder===f.id).length; });
    c.unread = all.filter(e=>e.folder==="inbox" && !e.read).length;
    return c;
  },

  setRead(id, read){ const e=this.get(id); if(e){ e.read = read!==false; Store.save(); } },
  toggleStar(id){ const e=this.get(id); if(e){ e.starred=!e.starred; Store.save(); } return e && e.starred; },
  toggleImportant(id){ const e=this.get(id); if(e){ e.important=!e.important; Store.save(); } },

  moveTo(ids, folder){
    (Array.isArray(ids)?ids:[ids]).forEach(id=>{ const e=this.get(id); if(e) e.folder=folder; });
    Store.save();
  },
  trash(ids){ this.moveTo(ids, "trash"); },
  archive(ids){ this.moveTo(ids, "archive"); },
  spam(ids){ this.moveTo(ids, "spam"); },
  notSpam(ids){ this.moveTo(ids, "inbox"); },
  deleteForever(ids){
    const set = new Set(Array.isArray(ids)?ids:[ids]);
    Store.state.emails = Store.state.emails.filter(e=>!set.has(e.id));
    Store.save();
  },
  emptyTrash(){
    Store.state.emails = Store.state.emails.filter(e=>e.folder!=="trash");
    Store.save();
  },

  addLabel(ids, label){
    (Array.isArray(ids)?ids:[ids]).forEach(id=>{ const e=this.get(id);
      if(e){ e.labels=e.labels||[]; if(!e.labels.includes(label)) e.labels.push(label); } });
    Store.save();
  },

  send({to, cc, subject, body, attachments}){
    const me = Store.state.user;
    const em = { id: uid("m"), from:{name:me.name, email:me.email},
      to: splitAddr(to), cc: splitAddr(cc), subject: subject||"(no subject)",
      body: body||"", folder:"sent", read:true, starred:false, date:Date.now(),
      labels:[], hasAttachment:(attachments||[]).length>0, attachments:attachments||[] };
    Store.state.emails.push(em); Store.save();
    App.sound("sent");
    return em;
  },

  saveDraft({to, cc, subject, body, attachments, id}){
    let em = id && this.get(id);
    const data = { to:splitAddr(to), cc:splitAddr(cc), subject:subject||"(no subject)", body:body||"",
      hasAttachment:(attachments||[]).length>0, attachments:attachments||[] };
    if(em && em.folder==="drafts"){ Object.assign(em, data); }
    else { em = Object.assign({ id:uid("m"), from:{name:Store.state.user.name, email:Store.state.user.email},
      folder:"drafts", read:true, starred:false, date:Date.now(), labels:[] }, data);
      Store.state.emails.push(em); }
    Store.save(); return em;
  },

  replyDraft(id, all){
    const e = this.get(id); if(!e) return null;
    const me = Store.state.user.email;
    const to = [e.from.email];
    const cc = all ? (e.cc||[]).concat((e.to||[]).filter(t=>t!==me && t!==e.from.email)) : [];
    return { to: to.join(", "), cc:[...new Set(cc)].join(", "),
      subject: (/^re:/i.test(e.subject)?e.subject:"Re: "+e.subject),
      body: `<br><br><div style="color:var(--ink-2);border-left:3px solid var(--line);padding-left:10px">On ${new Date(e.date).toLocaleString()}, ${esc(e.from.name)} wrote:<br>${e.body}</div>` };
  },
  forwardDraft(id){
    const e = this.get(id); if(!e) return null;
    return { to:"", cc:"", subject:(/^fwd?:/i.test(e.subject)?e.subject:"Fwd: "+e.subject),
      body:`<br><br><div style="color:var(--ink-2);border-left:3px solid var(--line);padding-left:10px">Forwarded message — from ${esc(e.from.name)} &lt;${esc(e.from.email)}&gt;:<br>${e.body}</div>` };
  },

  advancedSearch(c){
    return Store.state.emails.filter(e=>{
      if(e.folder==="trash") return false;
      const hay = e.subject+" "+strip(e.body)+" "+e.from.name+" "+e.from.email+" "+(e.to||[]).join(" ");
      if(c.from && !hay.toLowerCase().includes(c.from.toLowerCase()) && !e.from.email.toLowerCase().includes(c.from.toLowerCase())) return false;
      if(c.to && !(e.to||[]).join(" ").toLowerCase().includes(c.to.toLowerCase())) return false;
      if(c.subject && !e.subject.toLowerCase().includes(c.subject.toLowerCase())) return false;
      if(c.has && !c.has.split(/\s+/).every(w=>hay.toLowerCase().includes(w.toLowerCase()))) return false;
      if(c.hasnt && c.hasnt.split(/\s+/).some(w=>hay.toLowerCase().includes(w.toLowerCase()))) return false;
      if(c.attach && !e.hasAttachment) return false;
      if(c.after && e.date < new Date(c.after).getTime()) return false;
      if(c.before && e.date > new Date(c.before).getTime()+864e5) return false;
      return true;
    }).sort((a,b)=>b.date-a.date);
  },

  /* simulate fetching new mail — applies filters + blocked list, plays sound */
  checkMail(){
    const D = window.DemoData, s = Store.state;
    const item = D.incomingPool[s.poolIdx % D.incomingPool.length]; s.poolIdx++;
    const em = { id:uid("m"), from:item.from, to:[s.user.email], subject:item.subject,
      body:item.body, folder:"inbox", read:false, starred:false, date:Date.now(),
      labels:item.labels||[], hasAttachment:!!item.hasAttachment, attachments:item.attachments||[] };
    if(s.blocked.some(b=>em.from.email.toLowerCase().includes(b.toLowerCase()))){ em.folder="spam"; }
    else {
      s.filters.filter(f=>f.on).forEach(f=>{ if(Filters.matches(em,f)) Filters.applyTo(em,f); });
    }
    s.emails.push(em); Store.save();
    if(em.folder==="inbox") App.sound("mail");
    return em;
  },

  storage(){
    const used = Store.state.emails.length * 0.4; // demo MB
    return { used: used.toFixed(1), total: 5120, pct: Math.min(100, used/5120*100) };
  }
};

function splitAddr(s){ return String(s||"").split(/[,;\n]+/).map(x=>x.trim()).filter(Boolean); }
function strip(h){ const d=document.createElement("div"); d.innerHTML=h||""; return d.textContent||""; }

window.Mail = Mail;
})();
