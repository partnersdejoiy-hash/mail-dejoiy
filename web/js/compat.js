/* ============ Dejoiy Mail — compat.js : keeps older phone browsers working ============
   Loaded first. Many phones ship browsers a few years behind (for example Chrome 91 on
   Android 12). Each shim only fills in what is missing and leaves modern browsers untouched. */
(function(){
"use strict";
function define(target, name, value){
  if(!(name in target)) Object.defineProperty(target, name, {value, writable:true, configurable:true});
}
function at(index){
  const n = Math.trunc(index) || 0, len = this.length, i = n < 0 ? len + n : n;
  return i < 0 || i >= len ? undefined : this[i];
}
define(Array.prototype, "at", at);
define(String.prototype, "at", at);
define(Object, "hasOwn", (object, key)=> Object.prototype.hasOwnProperty.call(object, key));
define(Array.prototype, "findLast", function(fn, self){ for(let i=this.length-1;i>=0;i--) if(fn.call(self,this[i],i,this)) return this[i]; });
define(Array.prototype, "findLastIndex", function(fn, self){ for(let i=this.length-1;i>=0;i--) if(fn.call(self,this[i],i,this)) return i; return -1; });
if(typeof window.structuredClone !== "function") window.structuredClone = value=> value===undefined ? undefined : JSON.parse(JSON.stringify(value));

/* 100dvh is the visible screen height on current browsers. Older ones ignore it, so the
   stylesheets fall back to --vh, which is measured here and kept up to date as the address
   bar and on-screen keyboard come and go. */
const root = document.documentElement;
const measure = ()=>{
  const h = (window.visualViewport && window.visualViewport.height) || window.innerHeight;
  root.style.setProperty("--vh", (h/100)+"px");
};
measure();
window.addEventListener("resize", measure);
window.addEventListener("orientationchange", ()=> setTimeout(measure, 250));
if(window.visualViewport) window.visualViewport.addEventListener("resize", measure);

/* Feature flags for the stylesheets. */
const supports = (prop, value)=>{ try{ return CSS.supports(prop, value); }catch(_){ return false; } };
if(!supports("color", "color-mix(in srgb, red 50%, blue)")) root.classList.add("no-color-mix");
try{ document.querySelector(":has(a)"); }catch(_){ root.classList.add("no-has"); }
})();
