/* ============ Dejoiy Mail: idcard.js : a person's ID card in DEJOIY's Gen-Z colours ============
   Used in Settings → My ID card and in the admin console. The photo sits in the D of DEJOIY's logo
   (the same D as on dejoiy.com), with the logo's two dots and a lime D behind it. No photo, or one
   that fails to load: the initials of the first and last name. */
(function(){
"use strict";
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
/* the D of DEJOIY's logo (dejoiy.com/assets/brand): flat rounded left side, round right side */
const D = "M18 -20H80A70 70 0 0 1 80 120H18A18 18 0 0 1 0 102V-2A18 18 0 0 1 18 -20Z";
let n = 0;

/** "Asha Verma" → "AV", "asha" → "A", "asha.verma@x.in" → "AV". */
function initials(name, email){
  const words = String(name || "").trim().split(/\s+/).filter(Boolean);
  if(words.length >= 2) return (words[0][0] + words[words.length-1][0]).toUpperCase();
  if(words.length === 1 && !words[0].includes("@")) return words[0][0].toUpperCase();
  const local = String(email || name || "?").split("@")[0].split(/[._-]+/).filter(Boolean);
  return ((local[0]?.[0] || "?") + (local.length > 1 ? local[local.length-1][0] : "")).toUpperCase();
}

/** The photo (or initials) inside the D, as an SVG so it scales cleanly. */
function dFrame(photo, letters){
  const id = "idc-d" + (++n);
  return `<svg class="idc-d" viewBox="-46 -32 214 172" role="img" aria-hidden="true">
    <defs><clipPath id="${id}"><path d="${D}"/></clipPath></defs>
    <path d="${D}" transform="translate(12 10)" fill="#d4ff3a" stroke="#121212" stroke-width="5"/>
    <g clip-path="url(#${id})">
      <rect x="0" y="-20" width="150" height="140" fill="#ff9bcb"/>
      <text x="75" y="52" text-anchor="middle" dominant-baseline="central" class="idc-d-letters">${esc(letters)}</text>
      ${photo ? `<image href="${esc(photo)}" x="0" y="-20" width="150" height="140" preserveAspectRatio="xMidYMid slice" onerror="this.remove()"/>` : ""}
    </g>
    <path d="${D}" fill="none" stroke="#121212" stroke-width="5"/>
    <circle cx="-24" cy="20" r="13" fill="#ff4fa3" stroke="#121212" stroke-width="4"/>
    <circle cx="-24" cy="80" r="13" fill="#121212"/>
  </svg>`;
}

function html(c){
  const chips = [["ID", c.employeeId, "sky"], ["Dept", c.department, "mint"]].filter(([,v]) => v);
  return `<article class="idc" aria-label="ID card of ${esc(c.name)}">
    <header class="idc-top">
      ${c.logo ? `<img class="idc-logo" src="${esc(c.logo)}" alt="">` : `<span class="idc-mark" aria-hidden="true">${esc(initials(c.company))}</span>`}
      <span class="idc-co"><b>${esc(c.company)}</b><small>${esc(c.domain)}</small></span>
      <span class="idc-tag">ID</span>
    </header>
    <div class="idc-body">
      ${dFrame(c.photo, initials(c.name, c.email))}
      <h3 class="idc-name">${esc(c.name)}</h3>
      ${c.position ? `<p class="idc-pos">${esc(c.position)}</p>` : ""}
      ${c.role ? `<span class="idc-role">${esc(c.role)}</span>` : ""}
      ${chips.length ? `<div class="idc-chips">${chips.map(([k,v,t]) => `<span class="idc-chip ${t}"><small>${k}</small>${esc(v)}</span>`).join("")}</div>` : ""}
      <p class="idc-mail">${esc(c.email)}</p>
    </div>
    <footer class="idc-foot"><span class="idc-brand"><i></i><i></i>DEJOIY</span><span class="idc-bars" aria-hidden="true"></span><span class="idc-num">${c.employeeId ? esc(c.employeeId) : "ID CARD"}</span></footer>
  </article>`;
}

window.IdCard = { html, initials, dFrame };
})();
