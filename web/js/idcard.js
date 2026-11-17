/* ============ Dejoiy Mail: idcard.js : a person's ID card in DEJOIY's colours ============
   Used in Settings → My ID card and in the admin console. Photo when the person has one,
   otherwise the initials of their first and last name. */
(function(){
"use strict";
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

/** "Asha Verma" → "AV", "asha" → "A", "asha.verma@x.in" → "AV". */
function initials(name, email){
  const words = String(name || "").trim().split(/\s+/).filter(Boolean);
  if(words.length >= 2) return (words[0][0] + words[words.length-1][0]).toUpperCase();
  if(words.length === 1 && !words[0].includes("@")) return words[0][0].toUpperCase();
  const local = String(email || name || "?").split("@")[0].split(/[._-]+/).filter(Boolean);
  return ((local[0]?.[0] || "?") + (local.length > 1 ? local[local.length-1][0] : "")).toUpperCase();
}

function html(c){
  const rows = [["Employee ID", c.employeeId], ["Department", c.department], ["Email", c.email]].filter(([,v]) => v);
  return `<article class="idc" aria-label="ID card of ${esc(c.name)}">
    <header class="idc-top">
      ${c.logo ? `<img class="idc-logo" src="${esc(c.logo)}" alt="">` : `<span class="idc-mark" aria-hidden="true">${esc(initials(c.company))}</span>`}
      <span class="idc-co"><b>${esc(c.company)}</b><small>${esc(c.domain)}</small></span>
    </header>
    <div class="idc-body">
      <div class="idc-photo"><span>${esc(initials(c.name, c.email))}</span>${c.photo ? `<img src="${esc(c.photo)}" alt="" onerror="this.remove()">` : ""}</div>
      <h3 class="idc-name">${esc(c.name)}</h3>
      ${c.position ? `<p class="idc-pos">${esc(c.position)}</p>` : ""}
      ${c.role ? `<span class="idc-role">${esc(c.role)}</span>` : ""}
      <dl class="idc-rows">${rows.map(([k,v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>
    </div>
    <footer class="idc-foot"><span>DEJOIY</span><span>${c.employeeId ? esc(c.employeeId) : "ID card"}</span></footer>
  </article>`;
}

window.IdCard = { html, initials };
})();
