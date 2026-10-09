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
    const sort=Store.state.prefs.mailSort||'dateDesc';
    return r.sort((a,b)=>sort==='dateAsc'?a.date-b.date:sort==='sender'?a.from.name.localeCompare(b.from.name):sort==='subject'?a.subject.localeCompare(b.subject):b.date-a.date);
  },

  get(id){ return Store.state.emails.find(e=>e.id===id); },
  /* Conversations work like Gmail: a thread listed in a folder also shows the rest of the
     conversation (your sent replies, the answers in the inbox), while folder actions such as
     Archive only move the messages that are actually in that folder (`ids`). */
  conversation(id, folder){
    const hidden=["trash","spam"].includes(folder)?[]:["trash","spam"];
    return Store.state.emails.filter(m=>this.threadKey(m)===String(id)&&(m.folder===folder||!hidden.includes(m.folder)&&m.folder!=="drafts"));
  },
  /* The server groups messages by their Message-ID references. Amazon SES, which relays our
     mail to Gmail, replaces the Message-ID of everything it sends, so a Gmail reply can come
     back as a new upstream conversation. Like Gmail, a reply with the same subject and at least
     one person in common (besides you) joins the earlier conversation. */
  threadKey(message){ if(window.Settings && Settings.messageView()) return String(message.id); return threadKeys().get(message.id) || String(message.conversationId||message.id); },
  threadId(messageId){ const m=this.get(messageId); return m ? this.threadKey(m) : String(messageId); },
  senderNames(messages){
    const me=(Store.state.user.email||"").toLowerCase();
    return [...new Set(messages.map(m=>(m.from?.email||"").toLowerCase()===me&&me?"me":m.from?.name||m.from?.email).filter(Boolean))];
  },
  threadList(folder){
    const groups=new Map();
    for(const message of this.list(folder)){
      const id=this.threadKey(message);
      if(!groups.has(id))groups.set(id,[]);
      groups.get(id).push(message);
    }
    return [...groups].map(([id,inFolder])=>{
      const messages=folder==="drafts"||SMART.some(s=>s.id===folder)?inFolder:this.conversation(id,folder);
      const ordered=[...messages].sort((a,b)=>a.date-b.date),latest=ordered.at(-1),senders=this.senderNames(ordered);
      return {id,conversationId:id,messages:ordered,latest,ids:inFolder.map(m=>m.id),subject:latest.subject,from:{name:senders.join(', '),email:latest.from?.email||''},date:latest.date,read:ordered.every(m=>m.read),unreadCount:ordered.filter(m=>!m.read).length,starred:ordered.every(m=>m.starred),hasAttachment:ordered.some(m=>m.hasAttachment),important:ordered.some(m=>m.important),labels:[...new Set(ordered.flatMap(m=>m.labels||[]))],count:ordered.length};
    }).sort((a,b)=>Store.state.prefs.mailSort==='dateAsc'?a.date-b.date:Store.state.prefs.mailSort==='sender'?a.from.name.localeCompare(b.from.name):Store.state.prefs.mailSort==='subject'?a.subject.localeCompare(b.subject):b.date-a.date);
  },
  getThread(id, folder=App.ui?.folder){
    const messages=this.conversation(id,folder);
    if(!messages.length)return null;
    messages.sort((a,b)=>a.date-b.date);
    const latest=messages[messages.length-1],senders=this.senderNames(messages);
    return {...latest,id:String(id),conversationId:String(id),latest,messages,ids:messages.map(m=>m.id),folderIds:messages.filter(m=>m.folder===folder).map(m=>m.id),from:{...latest.from,name:senders.join(', ')},count:messages.length,unreadCount:messages.filter(m=>!m.read).length,read:messages.every(m=>m.read),starred:messages.every(m=>m.starred),hasAttachment:messages.some(m=>m.hasAttachment)};
  },

  counts(){
    const all = Store.state.emails, c = {};
    FOLDERS.forEach(f=>{ c[f.id] = all.filter(e=> f.id==="starred" ? (e.starred&&e.folder!=="trash") : e.folder===f.id).length; });
    c.unread = all.filter(e=>e.folder==="inbox" && !e.read).length;
    return c;
  },

  setRead(id, read){ const messages=(Array.isArray(id)?id:[id]).map(key=>this.get(key)).filter(Boolean);for(const e of messages)e.read=read!==false;if(messages.length)Store.save(); },
  toggleStar(id){ const e=this.get(id); if(e){ e.starred=!e.starred; Store.save(); } return e && e.starred; },
  toggleImportant(id){ const e=this.get(id); if(e){ e.important=!e.important; Store.save(); } },

  moveTo(ids, folder){
    (Array.isArray(ids)?ids:[ids]).forEach(id=>{ const e=this.get(id); if(e) e.folder=folder; });
    Store.save();
  },
  trash(ids){ return this.moveTo(ids, "trash"); },
  archive(ids){ return this.moveTo(ids, "archive"); },
  spam(ids){ return this.moveTo(ids, "spam"); },
  notSpam(ids){ return this.moveTo(ids, "inbox"); },
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
    const me = (Store.state.user.email||"").toLowerCase(), not=list=>a=>!list.some(x=>x.toLowerCase()===a.toLowerCase());
    // Replying to your own message goes back to the people you wrote to, as in Gmail.
    const mine = (e.from.email||"").toLowerCase()===me;
    const to = mine ? (e.to||[]) : [e.from.email];
    const cc = all ? (mine ? (e.cc||[]) : (e.cc||[]).concat(e.to||[])).filter(a=>a.toLowerCase()!==me).filter(not(to)) : [];
    return { to: to.join(", "), cc:[...new Set(cc)].join(", "), inReplyTo:e.messageId||"", origId:String(e.id), replyType:"r",
      subject: (/^re:/i.test(e.subject)?e.subject:"Re: "+e.subject),
      body: `<br><br><div>On ${new Date(e.date).toLocaleString()}, ${esc(e.from.name)} &lt;${esc(e.from.email)}&gt; wrote:</div><blockquote>${e.body}</blockquote>` };
  },
  forwardDraft(id){
    const e = this.get(id); if(!e) return null;
    return { to:"", cc:"", origId:String(e.id), replyType:"w", subject:(/^fwd?:/i.test(e.subject)?e.subject:"Fwd: "+e.subject),
      body:`<br><br><div>---------- Forwarded message ---------<br>From: ${esc(e.from.name)} &lt;${esc(e.from.email)}&gt;<br>Date: ${new Date(e.date).toLocaleString()}<br>Subject: ${esc(e.subject)}<br>To: ${(e.to||[]).map(esc).join(", ")}</div><br>${e.body}` };
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

const REPLY_PREFIX=/^\s*(?:(?:re|fw|fwd|aw|wg|sv|antw)(?:\[\d+\])?\s*:\s*)+/i;
const THREAD_WINDOW=90*864e5;
let threadCache={emails:null,length:-1,me:"",keys:null};
function threadKeys(){
  const emails=Store.state.emails, me=(Store.state.user?.email||"").toLowerCase();
  if(threadCache.emails===emails && threadCache.length===emails.length && threadCache.me===me) return threadCache.keys;
  const parent=new Map(), find=id=>{ while(parent.has(id)&&parent.get(id)!==id) id=parent.get(id); return id; };
  const bySubject=new Map();
  for(const m of [...emails].sort((a,b)=>a.date-b.date)){
    const own=String(m.conversationId||m.id); if(!parent.has(own)) parent.set(own,own);
    const subject=String(m.subject||"").replace(REPLY_PREFIX,"").replace(/\s+/g," ").trim().toLowerCase();
    if(!subject) continue;
    const people=new Set([m.from?.email,...(m.to||[]),...(m.cc||[])].map(a=>String(a||"").toLowerCase()).filter(a=>a&&a!==me));
    const earlier=bySubject.get(subject)||[];
    if(REPLY_PREFIX.test(m.subject||"")||m.inReplyTo){
      const match=[...earlier].reverse().find(t=>m.date-t.last<THREAD_WINDOW && [...people].some(p=>t.people.has(p)));
      if(match){ const a=find(match.root), b=find(own); if(a!==b) parent.set(b,a); }
    }
    const root=find(own), entry=earlier.find(t=>find(t.root)===root);
    if(entry){ people.forEach(p=>entry.people.add(p)); entry.last=Math.max(entry.last,m.date); }
    else { earlier.push({root, people, last:m.date}); bySubject.set(subject, earlier); }
  }
  const keys=new Map(emails.map(m=>[m.id, find(String(m.conversationId||m.id))]));
  threadCache={emails, length:emails.length, me, keys};
  return keys;
}

function splitAddr(s){ return String(s||"").split(/[,;\n]+/).map(x=>x.trim()).filter(Boolean); }
function strip(h){ return new DOMParser().parseFromString(h||"","text/html").body.textContent||""; }

window.Mail = Mail;
})();
