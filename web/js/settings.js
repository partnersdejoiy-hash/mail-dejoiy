/* ============ Dejoiy Mail — settings.js : the user's settings and what they switch on ============
   Two kinds of settings, one place to read them:
   - mailbox: real mail server preferences (page size, out of office, forwarding, text style…),
     shared with every device and every mail app on this account;
   - ui: display choices the mail server has no field for (undo send, hover actions…), stored
     per account by the Dmail server so they also follow the user between devices.
   The demo build keeps both on this device. */
(function(){
"use strict";

const MAILBOX_DEFAULTS = {locale:"", timeZone:"Asia/Kolkata", pageSize:"50", conversationView:"conversation",
  externalImages:false, snippets:true, autoAddContacts:true, keyboardShortcuts:true, pollInterval:"2m", readReceipts:"prompt", saveToSent:true,
  fontFamily:"arial, helvetica, sans-serif", fontSize:"12pt", fontColor:"#000000", replyToEnabled:false, replyTo:"",
  forwardTo:"", forwardKeepCopy:true, popDelete:"keep", vacationOn:false, vacationMessage:"", vacationFrom:"", vacationUntil:"",
  vacationExternalOn:false, vacationExternalMessage:"", vacationEvery:"4d", vacationAudience:"everyone"};
const UI_DEFAULTS = {undoSendOn:true, undoSend:5, defaultReply:"reply", hoverActions:true, sendArchive:false, spellcheck:true, autocorrect:true,
  buttonLabels:"icons", notifications:"off", inboxType:"default", readingPane:"off", autoAdvanceOn:false, autoAdvance:"next", density:"comfortable",
  indicators:false, importanceMarkers:true, templates:false, templateList:[], unreadBadge:true, hiddenFolders:[]};
const LOCAL_KEY = "dejoiy-settings-v1";

const Settings = {
  mailbox: {...MAILBOX_DEFAULTS}, ui: {...UI_DEFAULTS}, account: null, server: {host: location.hostname},
  loaded: false,

  async load(){
    if(window.Live && Live.enabled){
      try{
        const result = await Live.request("settings");
        this.mailbox = {...MAILBOX_DEFAULTS, ...result.mailbox};
        this.ui = {...UI_DEFAULTS, ...result.ui};
        /* Before reading pane was an account setting, it was kept on each device. */
        if(!result.ui || !result.ui.readingPane) this.ui.readingPane = Store.state.prefs.messageLayout==="right" ? "right" : "off";
        this.account = result.account; this.server = result.server || this.server;
        this.loaded = true;
      }catch(_){ /* the app still works with defaults; Settings shows the error when opened */ }
    } else {
      try{ const saved = JSON.parse(localStorage.getItem(LOCAL_KEY)) || {};
        this.mailbox = {...MAILBOX_DEFAULTS, ...saved.mailbox}; this.ui = {...UI_DEFAULTS, ...saved.ui}; }catch(_){}
      this.loaded = true;
    }
    this.apply();
  },

  /* Saves {mailbox:{…}, ui:{…}}; only the keys given change. Throws with a readable message. */
  async save(change){
    if(window.Live && Live.enabled){
      const result = await Live.request("settings", change);
      if(result.mailbox) this.mailbox = {...MAILBOX_DEFAULTS, ...result.mailbox};
      if(result.ui) this.ui = {...UI_DEFAULTS, ...result.ui};
    } else {
      Object.assign(this.mailbox, change.mailbox||{}); Object.assign(this.ui, change.ui||{});
      try{ localStorage.setItem(LOCAL_KEY, JSON.stringify({mailbox:this.mailbox, ui:this.ui})); }catch(_){}
    }
    this.apply();
  },

  /* ---------- applying settings to the app ---------- */
  apply(){
    const body = document.body, root = document.documentElement, ui = this.ui, mb = this.mailbox;
    body.classList.toggle("density-compact", ui.density==="compact");
    body.classList.toggle("no-snippets", mb.snippets===false);
    body.classList.toggle("labels-text", ui.buttonLabels==="text");
    body.classList.toggle("hover-actions", !!ui.hoverActions);
    body.classList.toggle("no-importance", ui.importanceMarkers===false);
    root.dataset.mailLayout = ui.readingPane==="right" ? "right" : ui.readingPane==="bottom" ? "bottom" : "list";
    if(window.Store) Store.state.prefs.messageLayout = root.dataset.mailLayout;
    this.startPolling();
    this.updateBadge();
  },
  pageSize(){ return Math.max(10, parseInt(this.mailbox.pageSize,10) || 50); },
  messageView(){ return this.mailbox.conversationView==="message"; },
  textStyle(){ const m=this.mailbox; return `font-family:${m.fontFamily};font-size:${m.fontSize};color:${m.fontColor}`; },

  /* Unread count in the tab title and, for the installed app, on its icon. */
  updateBadge(count){
    if(count===undefined){ try{ count = Mail.counts().unread; }catch(_){ return; } }
    const on = this.ui.unreadBadge!==false;
    document.title = on && count ? `(${count}) Dejoiy Mail` : "Dejoiy Mail";
    try{
      if(on && count && navigator.setAppBadge) navigator.setAppBadge(count).catch(()=>{});
      else if(navigator.clearAppBadge) navigator.clearAppBadge().catch(()=>{});
    }catch(_){}
  },

  /* ---------- new mail: checking, notifications ---------- */
  startPolling(){
    clearInterval(this.timer); this.timer = null;
    if(!(window.Live && Live.enabled)) return;
    const m = /^(\d+)m$/.exec(this.mailbox.pollInterval||"2m"), every = (m ? +m[1] : 2) * 60000;
    this.timer = setInterval(()=> this.checkNow(), every);
    if(!this.wakeBound){ this.wakeBound = true;
      /* Coming back to the app after a while checks straight away, as phone mail apps do. */
      document.addEventListener("visibilitychange", ()=>{ if(!document.hidden && Date.now()-(this.lastCheck||0) > 60000) this.checkNow(); }); }
  },
  async checkNow(){
    if(this.checking || !(window.Live && Live.enabled)) return;
    if(window.App && App.route==="compose") return;
    this.checking = true; this.lastCheck = Date.now();
    const known = new Set(Store.state.emails.map(m=>m.id));
    try{
      await Live.sync();
      const fresh = Store.state.emails.filter(m=>!known.has(m.id) && m.folder==="inbox" && !m.read);
      if(known.size && fresh.length) this.announce(fresh);
      if(App.route==="mail" && App.ui._mail && !document.body.classList.contains("selecting")) App.ui._mail.renderList();
      App.refreshNav();
    }catch(_){ /* the next check retries */ }
    finally{ this.checking = false; }
  },
  announce(messages){
    const mode = this.ui.notifications, pick = mode==="important" ? messages.filter(m=>m.important) : mode==="all" ? messages : [];
    if(!pick.length) return;
    if(document.hidden && "Notification" in window && Notification.permission==="granted"){
      const m = pick[0], more = pick.length>1 ? ` (+${pick.length-1} more)` : "";
      try{ const n = new Notification((m.from.name||m.from.email)+more, {body:m.subject||"(no subject)", icon:"/assets/icons/icon-192.png", tag:"dmail-new"});
        n.onclick = ()=>{ window.focus(); App.go("mail:inbox"); n.close(); }; }catch(_){}
    } else if(window.App){ App.toast(`New mail from ${pick[0].from.name||pick[0].from.email}`); }
    if(Store.state.prefs.sounds) App.sound("mail");
  },
  async askNotificationPermission(){
    if(!("Notification" in window)) throw new Error("This browser does not support notifications.");
    const result = await Notification.requestPermission();
    if(result!=="granted") throw new Error("Notifications are blocked. Allow them for this site in your browser settings.");
    return result;
  }
};

window.Settings = Settings;
})();
