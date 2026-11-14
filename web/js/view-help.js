/* ============ Dejoiy Mail — view-help.js : Help & guides ============
   Shows the user guide (web/help/user-guide.html, made from docs/USER-GUIDE.md by tools/build-guides.py)
   inside the app. The page is our own static file with no scripts; its Report a bug buttons open the
   same dialog as the account menu. */
(function(){
"use strict";

Views.help = async function(el){
  el.innerHTML = `<div class="help-view"><div class="empty-note">Loading the guide…</div></div>`;
  let page;
  try{
    const res = await fetch("/help/user-guide.html", {cache:"no-cache", credentials:"same-origin"});
    if(!res.ok) throw new Error("The guide could not be loaded. Try again in a moment.");
    page = new DOMParser().parseFromString(await res.text(), "text/html").getElementById("guide");
    if(!page) throw new Error("The guide could not be loaded. Try again in a moment.");
  }catch(error){ el.innerHTML = `<div class="help-view"><div class="empty-note" role="alert">${esc(error.message)}</div></div>`; return; }
  if(App.route!=="help") return;
  const box = document.createElement("div"); box.className = "help-view";
  box.innerHTML = `<p class="help-links"><a href="/help/user-guide.html" target="_blank" rel="noopener">Open in a new tab</a> · <a href="/help/admin-guide.html" target="_blank" rel="noopener">Admin guide</a></p>`;
  page.querySelectorAll("script,iframe,object,embed").forEach(n=>n.remove());   // there are none; never let one in
  box.append(...page.childNodes);
  el.replaceChildren(box);
  box.addEventListener("click", e=>{
    const a = e.target.closest("a"); if(!a) return;
    if(a.hasAttribute("data-report-bug")){ e.preventDefault(); Views.deskReport(); return; }
    const to = a.getAttribute("href")||"";
    if(to.startsWith("#")){   // a place in the guide: scroll there (the app's own address uses #/)
      e.preventDefault();
      const id = to.slice(1), target = id && box.querySelector("#"+CSS.escape(id));
      if(target) target.scrollIntoView({behavior:"smooth", block:"start"});
    }
  });
};
})();
