/* ============ Dejoiy Mail — themes.js : 54 themes (12 live animated) + brightness + custom background ============ */
(function(){
"use strict";

const PHOTO_THEMES = [
  {id:'forest',name:'Forest',photo:'photo-1441974231531-c6227db76b6e',accent:'#357959'},
  {id:'mountains',name:'Alpine peaks',photo:'photo-1464822759023-fed622ff2c3b',accent:'#526e8a'},
  {id:'coast',name:'Ocean breeze',photo:'photo-1475924156734-496f6cac6ec1',accent:'#197884'},
  {id:'woodland',name:'Woodland light',photo:'photo-1448375240586-882707db888b',accent:'#5b754b'},
  {id:'alpine',name:'Mountain lake',photo:'photo-1470770841072-f978cf4d019e',accent:'#497674'},
  {id:'desert',name:'Desert dunes',photo:'photo-1509316785289-025f5b846b35',accent:'#ac704c'}
].map(t=>({...t,kind:'photo',image:`https://images.unsplash.com/${t.photo}?auto=format&fit=crop&w=1920&q=85`}));
const LIVE_THEMES = (window.LiveThemes ? window.LiveThemes.list() : []).map(t=>({...t,kind:"live"}));
const THEMES = [
  ...LIVE_THEMES,
  ...PHOTO_THEMES,
  // Dejoiy colours: the brand look in eight pops
  {id:"pearl",    name:"Dejoiy Pink",   kind:"dejoiy"},
  {id:"djgreen",  name:"Dejoiy Green",  kind:"dejoiy"},
  {id:"djyellow", name:"Dejoiy Yellow", kind:"dejoiy"},
  {id:"djblue",   name:"Dejoiy Blue",   kind:"dejoiy"},
  {id:"djorange", name:"Dejoiy Orange", kind:"dejoiy"},
  {id:"djlilac",  name:"Dejoiy Lilac",  kind:"dejoiy"},
  {id:"djmint",   name:"Dejoiy Mint",   kind:"dejoiy"},
  {id:"djred",    name:"Dejoiy Red",    kind:"dejoiy"},
  // 13 colour / gradient header themes
  {id:"aol",        name:"Cobalt",         kind:"color"},
  {id:"yellow",     name:"Yellow",         kind:"color"},
  {id:"highcontrast",name:"High Contrast",kind:"color"},
  {id:"simple",     name:"Simple",         kind:"color"},
  {id:"aim",        name:"Ember",          kind:"color"},
  {id:"aoldotcom",  name:"Skyline",        kind:"color"},
  {id:"purple",     name:"Purple",         kind:"color"},
  {id:"sunrise",    name:"Sunrise",        kind:"color"},
  {id:"aquagreen",  name:"Aqua Green",     kind:"color"},
  {id:"aquablue",   name:"Aqua Blue",      kind:"color"},
  {id:"deeppurple", name:"Deep Purple",    kind:"color"},
  {id:"bluenight",  name:"Blue Night",     kind:"color"},
  {id:"darkgrey",   name:"Dark Grey",      kind:"color"},
  // 4 holiday themes (retired-AOL-motif originals; AOL published no official values)
  {id:"christmas",   name:"Christmas",      kind:"color"},
  {id:"halloween",   name:"Halloween",      kind:"color"},
  {id:"thanksgiving",name:"Thanksgiving",   kind:"color"},
  {id:"easter",      name:"Easter",         kind:"color"},
  // 11 scenic themes
  {id:"nightlandscape", name:"Night Landscape", kind:"scenic"},
  {id:"roadtrip",    name:"Roadtrip",       kind:"scenic"},
  {id:"sunsetaussie",name:"Sunset Aussie",  kind:"scenic"},
  {id:"lighthouse", name:"Lighthouse",     kind:"scenic"},
  {id:"spring",     name:"Spring",         kind:"scenic"},
  {id:"winter",     name:"Winter",         kind:"scenic"},
  {id:"summer",     name:"Summer",         kind:"scenic"},
  {id:"galaxy",     name:"Galaxy",         kind:"scenic"},
  {id:"fall",       name:"Fall",           kind:"scenic"},
  {id:"western",    name:"Western",        kind:"scenic"},
  {id:"sunset",     name:"Sunset",         kind:"scenic"}
];
const THEME_CSS = {
  pearl:"#ff4fa3", djgreen:"#3ddc84", djyellow:"#ffd23f", djblue:"#4da3ff", djorange:"#ff8a3d", djlilac:"#b892ff", djmint:"#2dd4bf", djred:"#ff5a5f",
  aol:"#2f7cf6", yellow:"#f7b733", highcontrast:"#111111", simple:"#c9d2e2", aim:"#e33d2e",
  aoldotcom:"#00a9e0", purple:"#9b5cf6", sunrise:"#ff9a56", aquagreen:"#34d399", aquablue:"#38bdf8",
  deeppurple:"#6d28d9", bluenight:"#1e3a8a", darkgrey:"#6b7280",
  christmas:"#0f5132", halloween:"#ff7518", thanksgiving:"#b45309", easter:"#db2777",
  nightlandscape:"linear-gradient(135deg,#3b4a6b,#05080f)", roadtrip:"linear-gradient(135deg,#7c3f16,#120903)",
  sunsetaussie:"linear-gradient(135deg,#93386b,#f7b733)", lighthouse:"linear-gradient(135deg,#155e86,#0a1622)",
  spring:"linear-gradient(135deg,#3f7d4e,#0b1a10)", winter:"linear-gradient(135deg,#d7e3ef,#9db4c8)",
  summer:"linear-gradient(135deg,#a3d65c,#2c7a4b)", galaxy:"linear-gradient(135deg,#4c1d95,#050310)",
  fall:"linear-gradient(135deg,#c2410c,#451a03)", western:"linear-gradient(135deg,#eab308,#290e03)",
  sunset:"linear-gradient(135deg,#9d3c6e,#f97316)"
};

// How see-through the mail panels start for each kind of background (percent).
const GLASS_DEFAULT = {live:55, photo:50, scenic:45, custom:50};
const GLASS_MAX = 85;

const Themes = {
  ALL: THEMES,
  GLASS_MAX,
  glassKey(){ const p=Store.state.prefs; return p.customBg ? "custom" : p.theme; },
  hasBackdrop(){ const p=Store.state.prefs; return !!p.customBg || THEMES.some(t=>t.id===p.theme && GLASS_DEFAULT[t.kind]!==undefined); },
  glass(){
    if(!this.hasBackdrop()) return 0;
    const p=Store.state.prefs, key=this.glassKey(), saved=p.glass && p.glass[key];
    if(Number.isInteger(saved)) return Math.max(0,Math.min(GLASS_MAX,saved));
    return p.customBg ? GLASS_DEFAULT.custom : GLASS_DEFAULT[THEMES.find(t=>t.id===p.theme).kind];
  },
  setGlass(value){
    const p=Store.state.prefs; p.glass={...(p.glass||{}),[this.glassKey()]:Math.max(0,Math.min(GLASS_MAX,Math.round(+value)||0))};
    Store.save(); this.apply(); this.persist();
  },
  /* Signed-in mailboxes keep their look on the server, so it follows the user to every device. */
  persist(){ if(window.Live && window.Live.enabled && window.Live.saveAppearance) window.Live.saveAppearance(); },
  glassControl(){
    if(!this.hasBackdrop()) return "";
    return `<div class="field glass-field"><label for="glass-range">Panel transparency <span id="glass-value">${this.glass()}%</span></label>
      <input type="range" id="glass-range" min="0" max="${GLASS_MAX}" step="5" value="${this.glass()}" aria-describedby="glass-hint">
      <p class="hint" id="glass-hint">Slide right to see more of the background behind your mail. Saved for this theme.</p></div>`;
  },
  bindGlass(root){
    const range=root.querySelector("#glass-range"); if(!range) return;
    range.addEventListener("input",()=>{ this.setGlass(range.value); const label=root.querySelector("#glass-value"); if(label) label.textContent=this.glass()+"%"; });
  },
  preview(id){const t=THEMES.find(t=>t.id===id);if(t?.kind==="live"){const still=window.LiveThemes.thumb(id);return still?`url('${still}') center/cover`:t.accent;}return t?.image?`url('${t.image.replace('w=1920','w=420')}') center/cover`:THEME_CSS[id]||'#666';},
  get current(){ return Store.state.prefs.theme; },

  apply(){
    const p = Store.state.prefs;
    if(/^dj[a-z]+$/.test(p.theme)&&p.theme!=="djnone"){ p.accent=p.theme.slice(2); p.theme="pearl"; }  // older saved looks
    const accent = this.accent();
    if(accent) document.documentElement.dataset.dj = accent; else delete document.documentElement.dataset.dj;
    // The header logo follows the colour too (unless the mailbox uploaded its own logo).
    if(window.DejoiyAccent) for(const el of document.querySelectorAll(".brand-name,.brand-mark:not([data-logo-applied]),.workspace-emblem")) DejoiyAccent.recolour(el, accent||"pink");
    document.documentElement.dataset.theme = p.theme;
    document.documentElement.dataset.brightness = p.brightness;
    document.documentElement.dataset.scenic = String(!!p.customBg || THEMES.some(t=>t.id===p.theme && ["scenic","photo","live"].includes(t.kind)));
    const photo=PHOTO_THEMES.find(t=>t.id===p.theme), live=LIVE_THEMES.find(t=>t.id===p.theme);
    document.documentElement.dataset.photoTheme=String(!!photo||!!live||!!p.customBg);
    for(const key of ['--accent','--accent-ink'])document.documentElement.style?.removeProperty(key);
    const tinted=photo||live;
    if(tinted&&!accent){document.documentElement.style?.setProperty('--accent',tinted.accent);document.documentElement.style?.setProperty('--accent-ink','#fff');}
    const bg = document.getElementById("bg");
    bg.style.backgroundImage=photo&&!p.customBg?`url("${photo.image}")`:'';
    if(p.customBg){ bg.classList.add("custom"); bg.style.setProperty("--custom-bg", "url('"+p.customBg+"')"); }
    else { bg.classList.remove("custom"); bg.style.removeProperty("--custom-bg"); }
    if(live && !p.customBg) window.LiveThemes.start(live.id, bg); else window.LiveThemes?.stop();
    document.documentElement.style?.setProperty('--glass', this.glass()+'%');
    document.documentElement.style?.setProperty('--glass-num', String(this.glass()));
  },

  /* The Dejoiy colour in use: chosen on its own, or pink for the plain default look. */
  /* The colour picked on the home page (or here) wins everywhere in this browser until it is changed. */
  accent(){ const p=Store.state.prefs, chosen=window.DejoiyAccent?.chosen?.()||""; return chosen || p.accent || (p.theme==="pearl" ? "pink" : ""); },
  isPicked(id){
    const p=Store.state.prefs, t=THEMES.find(t=>t.id===id); if(!t) return false;
    if(t.kind==="dejoiy") return this.accent()===(id==="pearl"?"pink":id.slice(2));
    return p.theme===id && !p.customBg;
  },
  set(id){
    const t=THEMES.find(t=>t.id===id); if(!t) return;
    const p=Store.state.prefs;
    if(t.kind==="dejoiy"){
      // A Dejoiy colour keeps the background scene; on a plain look it brings the Dejoiy base.
      p.accent = id==="pearl" ? "pink" : id.slice(2);
      if(window.DejoiyAccent) DejoiyAccent.save(p.accent);  // same preference as the home page picker
      const scene = !!p.customBg || THEMES.some(x=>x.id===p.theme && ["scenic","photo","live"].includes(x.kind));
      if(!scene) p.theme="pearl";
      Store.save(); this.apply(); this.persist(); App.toast("Colour: " + t.name.replace("Dejoiy ",""));
      if(App.route==="settings") Views.settings(document.getElementById("view"), "themes");
      return;
    }
    if(t.kind==="color"){ p.accent=""; if(window.DejoiyAccent) DejoiyAccent.clear(); }  // a plain colour theme brings its own colour
    Store.state.prefs.theme = id;
    Store.state.prefs.customBg = "";
    Store.save(); this.apply(); this.persist();
    App.toast("Theme: " + this.name(id));
    if(App.route==="settings") Views.settings(document.getElementById("view"), "themes");
  },
  name(id){ const t = THEMES.find(t=>t.id===id); return t ? t.name : id; },

  setBrightness(b){
    Store.state.prefs.brightness = b; Store.save(); this.apply(); this.persist();
    App.toast("Brightness: " + b[0].toUpperCase()+b.slice(1));
  },

  setCustom(dataUrl){
    Store.state.prefs.customBg = dataUrl; Store.save(); this.apply(); this.persist();
    App.toast("Custom background applied");
  },
  clearCustom(){
    Store.state.prefs.customBg = ""; Store.save(); this.apply(); this.persist();
    App.toast("Custom background removed");
  },

  /* theme picker dialog — applies instantly on click, no save button */
  openPicker(){
    const p = Store.state.prefs;
    const cell = t => `
      <div class="theme-cell ${this.isPicked(t.id) ? "sel":""}" data-theme-pick="${t.id}" role="button" tabindex="0" aria-label="${esc(t.name)} theme">
        <div class="theme-sw" style="background:${this.preview(t.id)}"></div>
        <div class="theme-nm">${esc(t.name)} ${this.isPicked(t.id) ? "✓":""}</div>
      </div>`;
    const brand = THEMES.filter(t=>t.kind==="dejoiy").map(cell).join("");
    const lives = THEMES.filter(t=>t.kind==="live").map(cell).join("");
    const photos = THEMES.filter(t=>t.kind==="photo").map(cell).join("");
    const colors = THEMES.filter(t=>t.kind==="color").map(cell).join("");
    const scenic = THEMES.filter(t=>t.kind==="scenic").map(cell).join("");
    const body = `
      <div class="field"><label>Brightness (independent of theme)</label>
        <div class="seg" id="pk-bright">
          ${["light","medium","dark"].map(b=>`<button data-b="${b}" class="${p.brightness===b?"on":""}">${b[0].toUpperCase()+b.slice(1)}</button>`).join("")}
        </div></div>
      ${this.glassControl()}
      <div class="theme-sec">Dejoiy colours · works with any background below</div><div class="theme-grid">${brand}</div>
      <div class="theme-sec">Live animated</div><div class="theme-grid photo-grid">${lives}</div>
      <div class="theme-sec">Photo backgrounds</div><div class="theme-grid photo-grid">${photos}</div>
      <div class="theme-sec">Colour themes</div><div class="theme-grid">${colors}</div>
      <div class="theme-sec">Illustrated gradients</div><div class="theme-grid">${scenic}</div>
      <div class="theme-sec">Your photo</div>
      <div class="btn-row">
        <label class="btn sm" style="cursor:pointer">Upload background<input type="file" id="pk-upload" accept="image/*" class="sr"></label>
        ${p.customBg ? `<button class="btn sm ghost" id="pk-clear">Remove photo</button>` : ""}
      </div>
      <p class="hint" style="margin-top:10px">Tip: click any theme — it applies instantly across the whole app.</p>`;
    App.dialog({title:"Themes", body, wide:true, actions:[{label:"Done", primary:true}]});
    const root = document.getElementById("dialog-root");
    root.querySelectorAll("[data-theme-pick]").forEach(el=>{
      const pick = ()=>{ Themes.set(el.dataset.themePick); Themes.openPicker(); };
      el.addEventListener("click", pick);
      el.addEventListener("keydown", e=>{ if(e.key==="Enter"||e.key===" "){e.preventDefault();pick();} });
    });
    this.bindGlass(root);
    root.querySelectorAll("#pk-bright button").forEach(b=> b.addEventListener("click", ()=>{
      Themes.setBrightness(b.dataset.b);
      root.querySelectorAll("#pk-bright button").forEach(x=>x.classList.toggle("on", x===b));
    }));
    const up = root.querySelector("#pk-upload");
    if(up) up.addEventListener("change", ()=>{
      const f = up.files[0]; if(!f) return;
      const r = new FileReader();
      r.onload = ()=>{ Themes.setCustom(r.result); Themes.openPicker(); };
      r.readAsDataURL(f);
    });
    const clr = root.querySelector("#pk-clear");
    if(clr) clr.addEventListener("click", ()=>{ Themes.clearCustom(); Themes.openPicker(); });
  }
};

window.Themes = Themes;
})();
