/* ============ Dejoiy Mail — accent.js : the visitor's Dejoiy colour ============
   Pink by default. A colour picked and saved on the home page is kept in this browser and
   recolours every pink thing on the landing, sign-up and sign-in pages, logos included.
   Loaded in <head> so the page never flashes pink first. */
(function(){
  // pop (fills, ink text on top) · deep (readable on white) · soft (light tint) · soft for dark pages
  var COLOURS = {
    pink:   ["#ff4fa3","#c4166c","#ffe1ef","#3a1d2c"],
    yellow: ["#ffd23f","#8a6200","#fff3c4","#352c0f"],
    green:  ["#3ddc84","#12804a","#dcf8e8","#14321f"],
    blue:   ["#4da3ff","#1257c7","#e0edff","#14273f"],
    orange: ["#ff8a3d","#b04a06","#ffe7d6","#3a2415"],
    lilac:  ["#b892ff","#6b3fc9","#eee5ff","#272040"],
    mint:   ["#2dd4bf","#0f766e","#d5f7f2","#113230"],
    red:    ["#ff5a5f","#c21d2b","#ffe1e2","#3a1a1c"]
  };
  var KEY = "dm-accent", root = document.documentElement, svgCache = {};
  // In the mail app the header logo belongs to the app (custom logos), so only the sign-in screen is recoloured, on request.
  var manual = !!(document.currentScript && document.currentScript.getAttribute("data-logos") === "manual");
  // Kept in a cookie for all *.dejoiy.com sites (home, sign-up, admin-mail) and in localStorage as a fallback.
  var shared = /(^|\.)dejoiy\.com$/.test(location.hostname) ? "; domain=.dejoiy.com" : "";
  function saved(){
    var m = document.cookie.match(/(?:^|; )dm-accent=([a-z]+)/), c = m && m[1];
    if(!COLOURS[c]) try{ c = localStorage.getItem(KEY); }catch(e){}
    return COLOURS[c] ? c : "pink";
  }

  // The lockups are SVG files shown with <img>; to recolour them they are swapped for inline copies.
  function recolourLogos(name, scope){
    var pop = COLOURS[name][0];
    Array.prototype.forEach.call((scope || document).querySelectorAll('img[src*="assets/brand/"],svg[data-dj-logo]'), function(el){
      var src = el.getAttribute("data-dj-src") || el.currentSrc || el.src;
      if(!/\.svg/.test(src)) return;
      var url = src.replace(location.origin, "");
      (svgCache[url] || (svgCache[url] = fetch(url).then(function(r){ return r.text(); }))).then(function(text){
        var box = document.createElement("div");
        box.innerHTML = text.replace(/#FF4FA3/gi, pop);
        var svg = box.querySelector("svg"); if(!svg) return;
        svg.setAttribute("data-dj-logo", ""); svg.setAttribute("data-dj-src", url);
        svg.setAttribute("class", el.getAttribute("class") || "");
        var h = el.getAttribute("height") || el.getAttribute("data-h"); if(h){ svg.setAttribute("height", h); svg.setAttribute("data-h", h); }
        svg.style.width = "auto";
        if(el.alt === "" || el.getAttribute("aria-hidden") === "true") svg.setAttribute("aria-hidden", "true");
        var target = el.parentNode && el.parentNode.tagName === "PICTURE" ? el.parentNode : el;
        target.replaceWith(svg);
      }).catch(function(){});
    });
  }

  function apply(name){
    if(!COLOURS[name]) name = "pink";
    var c = COLOURS[name];
    root.style.setProperty("--dj-pop", c[0]); root.style.setProperty("--dj-deep", c[1]);
    root.style.setProperty("--dj-soft", c[2]); root.style.setProperty("--dj-soft-dark", c[3]);
    root.setAttribute("data-accent", name);
    var meta = document.querySelector('meta[name="theme-color"]');
    if(meta && !meta.hasAttribute("data-fixed")) meta.content = c[0];
    if(manual) return;
    var run = function(){ if(name !== "pink" || document.querySelector("svg[data-dj-logo]")) recolourLogos(name); };
    if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", run, {once:true}); else run();
  }

  window.DejoiyAccent = {
    COLOURS: COLOURS,
    saved: saved,
    apply: apply,
    recolour: function(scope){ var n = saved(); if(n !== "pink") recolourLogos(n, scope); },
    save: function(name){
      try{ localStorage.setItem(KEY, name); }catch(e){}
      document.cookie = KEY + "=" + name + "; path=/; max-age=31536000; samesite=lax" + shared + (location.protocol === "https:" ? "; secure" : "");
      apply(name);
    }
  };
  apply(saved());
})();
