/* ============ Dejoiy Mail — signup.js : company self sign-up ============
   1) company details → 2) prove the domain with a DNS TXT record → 3) choose the admin password.
   The pending sign-up token is kept in this browser so people can come back after editing DNS. */
(function(){
"use strict";

const body = document.getElementById("su-body");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const KEY = "dejoiy-signup";
const saved = { get(){ try{ return JSON.parse(localStorage.getItem(KEY)); }catch(_){ return null; } },
  set(v){ try{ v ? localStorage.setItem(KEY, JSON.stringify(v)) : localStorage.removeItem(KEY); }catch(_){} } };

async function api(op, data){
  const res = await fetch("/api/signup/"+op, {method:"POST", credentials:"same-origin", headers:{"Content-Type":"application/json"}, body:JSON.stringify(data)});
  let out = {}; try{ out = await res.json(); }catch(_){}
  if(!res.ok){ const e = new Error(out.error || "Something went wrong. Try again."); e.status = res.status; throw e; }
  return out;
}
const STATUS = {ok:["Live","good"], missing:["Not added yet","wait"], conflict:["Needs a fix","bad"], pending:["Created after verification","wait"]};
function recordList(records){
  return `<ol class="su-dns">${records.map((r,i)=>{
    const st = STATUS[r.pending ? "pending" : r.status || (r.ok ? "ok" : "missing")];
    return `<li class="su-dns-row is-${st[1]}">
      <div class="su-dns-head"><b>${esc(r.kind)}</b><span>${esc(r.purpose||"")}</span><em class="su-pill ${st[1]}">${st[0]}</em></div>
      ${r.pending ? `<p class="su-fine">Your signing key is made as soon as the domain is verified. It appears on the next screen.</p>` : `
      <dl class="su-record">
        <dt>Type</dt><dd><code>${esc(r.type)}</code>${r.priority ? ` <small>Priority <code>${r.priority}</code></small>` : ""}</dd>
        <dt>Host</dt><dd><code>${esc(r.host)}</code> <button class="su-copy" type="button" data-copy="${i}:host">Copy</button></dd>
        <dt>Value</dt><dd><code>${esc(r.value)}</code> <button class="su-copy" type="button" data-copy="${i}:value">Copy</button></dd>
      </dl>
      ${r.note ? `<p class="su-note">${esc(r.note)}</p>` : ""}
      ${r.found && r.found.length && r.status !== "ok" ? `<p class="su-fine">Found now: <code>${r.found.map(esc).join("</code> <code>")}</code></p>` : ""}`}
    </li>`; }).join("")}</ol>`;
}
function bindCopy(root, records){
  root.querySelectorAll("[data-copy]").forEach(b => b.addEventListener("click", async () => {
    const [i, key] = b.dataset.copy.split(":");
    try{ await navigator.clipboard.writeText(String(records[+i][key])); b.textContent = "Copied"; setTimeout(() => b.textContent = "Copy", 1600); }
    catch(_){ b.textContent = "Select and copy"; }
  }));
}
function step(n){ document.body.dataset.step = n;
  if(n>1 && matchMedia("(max-width: 900px)").matches) document.querySelector(".su-card").scrollIntoView({behavior:"smooth", block:"start"});
  document.querySelectorAll(".su-steps li").forEach(li => { const k=+li.dataset.step; li.className = k<n ? "done" : k===n ? "on" : ""; }); }
function busy(form, on){ form.querySelectorAll("button,input").forEach(x => x.disabled = on); }

function company(prefill){
  step(1);
  body.innerHTML = `<form id="su-form">
    <h2>Tell us about your company</h2>
    <label>Company name<input name="company" maxlength="120" required value="${esc(prefill?.company)}" autocomplete="organization"></label>
    <label>Company domain<input name="domain" required placeholder="yourcompany.com" value="${esc(prefill?.domain)}" autocapitalize="off" spellcheck="false" inputmode="url"></label>
    <label>Your name<input name="name" maxlength="200" required value="${esc(prefill?.name)}" autocomplete="name"></label>
    <label>Your admin address<span class="su-address"><input name="localPart" required placeholder="you" autocapitalize="off" spellcheck="false"><span id="su-at">@${esc(prefill?.domain || "yourcompany.com")}</span></span></label>
    <p class="su-error" role="alert"></p>
    <button class="su-btn">Continue</button>
    <p class="su-fine">Next you'll get every DNS record your domain needs, ready to copy.</p></form>`;
  const form = body.querySelector("form");
  const clean = v => v.trim().toLowerCase().replace(/^https?:\/\//,"").replace(/^www\./,"").replace(/\/.*$/,"");
  const preview = () => {  // the big address card on the left mirrors what is typed here
    const d = clean(form.elements.domain.value) || "yourcompany.com";
    document.getElementById("su-at").textContent = "@" + d;
    const set = (id, v) => { const el = document.getElementById(id); if(el) el.textContent = v; };
    set("su-pv-domain", d); set("su-pv-local", form.elements.localPart.value.trim().toLowerCase() || "you");
    set("su-pv-company", form.elements.company.value.trim() || "Your company");
  };
  ["domain","localPart","company"].forEach(n => form.elements[n].addEventListener("input", preview)); preview();
  form.addEventListener("submit", async e => {
    e.preventDefault(); busy(form, true);
    const domain = form.elements.domain.value.trim().toLowerCase().replace(/^https?:\/\//,"").replace(/^www\./,"").replace(/\/.*$/,"");
    try{
      const r = await api("start", {company:form.elements.company.value, domain, name:form.elements.name.value, localPart:form.elements.localPart.value});
      saved.set({token:r.token}); verify(r);
    }catch(err){ form.querySelector("[role=alert]").textContent = err.message; busy(form, false); }
  });
}

function verify(r){
  step(2);
  const records = r.records && r.records.length ? r.records : [{kind:"Verification", purpose:"Proves you own the domain", ...r.record}];
  body.innerHTML = `<div>
    <h2>Connect ${esc(r.domain)}</h2>
    <p>Sign in where your domain's DNS is managed (GoDaddy, Cloudflare, Hostinger, etc.) and add <b>all ${records.length} records</b> below. The first one proves you own the domain; the others let your team send and receive mail without landing in spam.</p>
    ${recordList(records)}
    <p class="su-status" id="su-status" role="status">Waiting for the verification record…</p>
    <button class="su-btn" id="su-check">I've added them — check now</button>
    <button class="su-btn ghost" id="su-restart" type="button">Use a different domain</button>
    <p class="su-fine">Only the verification record is needed to continue. DNS changes usually appear within a few minutes, sometimes up to an hour. You can close this page and come back.</p></div>`;
  bindCopy(body, records);
  document.getElementById("su-restart").addEventListener("click", () => { saved.set(null); company(); });
  const status = document.getElementById("su-status"), check = document.getElementById("su-check");
  let timer = 0;
  const poll = async manual => {
    check.disabled = true; status.textContent = "Checking DNS…";
    try{
      const c = await api("check", {token:saved.get()?.token});
      if(c.verified){ clearInterval(timer); create(c); return; }
      if(manual){ clearInterval(timer); verify(c); return; }
      status.textContent = "Still waiting for the verification record…";
    }catch(err){ status.textContent = err.message; if(err.status===404){ clearInterval(timer); saved.set(null); } }
    check.disabled = false;
  };
  check.addEventListener("click", () => poll(true));
  timer = setInterval(() => { if(document.visibilityState==="visible" && document.getElementById("su-check")) poll(false); else if(!document.getElementById("su-check")) clearInterval(timer); }, 30000);
}

function create(c){
  step(3);
  body.innerHTML = `<form id="su-form">
    <h2>Domain verified ✓</h2>
    <p>Create the password for <b>${esc(c.email)}</b>. You'll be the administrator for <b>${esc(c.domain)}</b>.</p>
    <label>Password<input name="password" type="password" minlength="8" required autocomplete="new-password"></label>
    <label>Confirm password<input name="confirm" type="password" minlength="8" required autocomplete="new-password"></label>
    <p class="su-error" role="alert"></p>
    <button class="su-btn">Create my company mail</button></form>`;
  const form = body.querySelector("form");
  form.addEventListener("submit", async e => {
    e.preventDefault(); const alert = form.querySelector("[role=alert]");
    if(form.elements.password.value !== form.elements.confirm.value){ alert.textContent = "The passwords don't match."; return; }
    busy(form, true); alert.textContent = "";
    try{ const session = await api("complete", {token:saved.get()?.token, password:form.elements.password.value}); saved.set(null); done(c, session.csrf); }
    catch(err){ alert.textContent = err.message; form.elements.password.value = form.elements.confirm.value = ""; busy(form, false); }
  });
}

function done(c, csrf){
  step(4);
  body.innerHTML = `<div><h2>You're in.</h2>
    <p><b>${esc(c.email)}</b> is ready and you're the administrator of <b>${esc(c.domain)}</b>.</p>
    <p>Mail starts flowing once these records are live at your DNS host:</p>
    <div id="su-final"><p class="su-status" role="status">Checking your DNS…</p></div>
    <button class="su-btn ghost" id="su-recheck" type="button">Check again</button>
    <a class="su-btn" href="/admin">Open the admin panel</a> <a class="su-btn ghost" href="/">Open my inbox</a></div>`;
  const box = document.getElementById("su-final"), again = document.getElementById("su-recheck");
  const load = async () => {
    again.disabled = true;
    try{
      const res = await fetch("/api/dns", {method:"POST", credentials:"same-origin", headers:{"Content-Type":"application/json","X-CSRF-Token":csrf||""}, body:"{}"});
      const out = await res.json(); if(!res.ok) throw new Error(out.error || "DNS could not be checked right now.");
      const live = out.records.filter(r => r.ok).length;
      box.innerHTML = `<p class="su-status" role="status">${live} of ${out.records.length} records are live.</p>` + recordList(out.records);
      bindCopy(box, out.records);
    }catch(err){ box.innerHTML = `<p class="su-error" role="alert">${esc(err.message)} You can also find these records in the admin panel under Domains → DNS setup.</p>`; }
    again.disabled = false;
  };
  again.addEventListener("click", load); load();
}

(async function start(){
  const pending = saved.get();
  if(!pending?.token) return company();
  try{ const c = await api("check", {token:pending.token}); c.verified ? create(c) : verify(c); }
  catch(_){ saved.set(null); company(); }
})();
})();
