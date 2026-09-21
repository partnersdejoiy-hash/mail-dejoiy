/* ============ Dejoiy Mail — themes.js : 24 themes + brightness + custom background ============ */
(function(){
"use strict";

const THEMES = [
  // 13 colour / gradient header themes
  {id:"aol",        name:"AOL",            kind:"color"},
  {id:"yellow",     name:"Yellow",         kind:"color"},
  {id:"highcontrast",name:"High Contrast",kind:"color"},
  {id:"simple",     name:"Simple",         kind:"color"},
  {id:"aim",        name:"AIM",            kind:"color"},
  {id:"aoldotcom",  name:"AOL.com",        kind:"color"},
  {id:"purple",     name:"Purple",         kind:"color"},
  {id:"sunrise",    name:"Sunrise",        kind:"color"},
  {id:"aquagreen",  name:"Aqua Green",     kind:"color"},
  {id:"aquablue",   name:"Aqua Blue",      kind:"color"},
  {id:"deeppurple", name:"Deep Purple",    kind:"color"},
  {id:"bluenight",  name:"Blue Night",     kind:"color"},
  {id:"darkgrey",   name:"Dark Grey",      kind:"color"},
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
  aol:"#2f7cf6", yellow:"#f7b733", highcontrast:"#111111", simple:"#c9d2e2", aim:"#e33d2e",
  aoldotcom:"#00a9e0", purple:"#9b5cf6", sunrise:"#ff9a56", aquagreen:"#34d399", aquablue:"#38bdf8",
  deeppurple:"#6d28d9", bluenight:"#1e3a8a", darkgrey:"#6b7280",
  nightlandscape:"linear-gradient(135deg,#3b4a6b,#05080f)", roadtrip:"linear-gradient(135deg,#7c3f16,#120903)",
  sunsetaussie:"linear-gradient(135deg,#93386b,#f7b733)", lighthouse:"linear-gradient(135deg,#155e86,#0a1622)",
  spring:"linear-gradient(135deg,#3f7d4e,#0b1a10)", winter:"linear-gradient(135deg,#d7e3ef,#9db4c8)",
  summer:"linear-gradient(135deg,#a3d65c,#2c7a4b)", galaxy:"linear-gradient(135deg,#4c1d95,#050310)",
  fall:"linear-gradient(135deg,#c2410c,#451a03)", western:"linear-gradient(135deg,#eab308,#290e03)",
  sunset:"linear-gradient(135deg,#9d3c6e,#f97316)"
};

const Themes = {
  ALL: THEMES,
  get current(){ return Store.state.prefs.theme; },

  apply(){
    const p = Store.state.prefs;
    document.documentElement.dataset.theme = p.theme;
    document.documentElement.dataset.brightness = p.brightness;
    const bg = document.getElementById("bg");
    if(p.customBg){ bg.classList.add("custom"); bg.style.setProperty("--custom-bg", "url('"+p.customBg+"')"); }
    else { bg.classList.remove("custom"); bg.style.removeProperty("--custom-bg"); }
  },

  set(id){
    if(!THEMES.find(t=>t.id===id)) return;
    Store.state.prefs.theme = id;
    Store.state.prefs.customBg = "";
    Store.save(); this.apply();
    App.toast("Theme: " + this.name(id));
    if(App.route==="settings") Views.settings(document.getElementById("view"), "themes");
  },
  name(id){ const t = THEMES.find(t=>t.id===id); return t ? t.name : id; },

  setBrightness(b){
    Store.state.prefs.brightness = b; Store.save(); this.apply();
    App.toast("Brightness: " + b[0].toUpperCase()+b.slice(1));
  },

  setCustom(dataUrl){
    Store.state.prefs.customBg = dataUrl; Store.save(); this.apply();
    App.toast("Custom background applied");
  },
  clearCustom(){
    Store.state.prefs.customBg = ""; Store.save(); this.apply();
    App.toast("Custom background removed");
  },

  /* theme picker dialog — applies instantly on click, no save button */
  openPicker(){
    const p = Store.state.prefs;
    const cell = t => `
      <div class="theme-cell ${p.theme===t.id && !p.customBg ? "sel":""}" data-theme-pick="${t.id}" role="button" tabindex="0" aria-label="${esc(t.name)} theme">
        <div class="theme-sw" style="background:${THEME_CSS[t.id]}"></div>
        <div class="theme-nm">${esc(t.name)} ${p.theme===t.id && !p.customBg ? "✓":""}</div>
      </div>`;
    const colors = THEMES.filter(t=>t.kind==="color").map(cell).join("");
    const scenic = THEMES.filter(t=>t.kind==="scenic").map(cell).join("");
    const body = `
      <div class="field"><label>Brightness (independent of theme)</label>
        <div class="seg" id="pk-bright">
          ${["light","medium","dark"].map(b=>`<button data-b="${b}" class="${p.brightness===b?"on":""}">${b[0].toUpperCase()+b.slice(1)}</button>`).join("")}
        </div></div>
      <div class="theme-sec">Colour themes</div><div class="theme-grid">${colors}</div>
      <div class="theme-sec">Scenic themes</div><div class="theme-grid">${scenic}</div>
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
