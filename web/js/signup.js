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
function step(n){ document.querySelectorAll(".su-steps li").forEach(li => { const k=+li.dataset.step; li.className = k<n ? "done" : k===n ? "on" : ""; }); }
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
    <p class="su-fine">You'll prove you own the domain with one DNS record. No card needed to start.</p></form>`;
  const form = body.querySelector("form");
  form.elements.domain.addEventListener("input", e => { document.getElementById("su-at").textContent = "@" + (e.target.value.trim().toLowerCase().replace(/^https?:\/\//,"").replace(/^www\./,"").replace(/\/.*$/,"") || "yourcompany.com"); });
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
  body.innerHTML = `<div>
    <h2>Verify ${esc(r.domain)}</h2>
    <p>Sign in where your domain's DNS is managed (GoDaddy, Cloudflare, Hostinger, etc.) and add this record:</p>
    <dl class="su-record">
      <dt>Type</dt><dd><code>TXT</code></dd>
      <dt>Host / Name</dt><dd><code>@</code> <small>(the domain itself)</small></dd>
      <dt>Value</dt><dd><code id="su-value">${esc(r.record.value)}</code> <button class="su-copy" id="su-copy" type="button">Copy</button></dd>
    </dl>
    <p class="su-status" id="su-status" role="status">Waiting for the record…</p>
    <button class="su-btn" id="su-check">I've added it — check now</button>
    <button class="su-btn ghost" id="su-restart" type="button">Use a different domain</button>
    <p class="su-fine">DNS changes usually appear within a few minutes, sometimes up to an hour. You can close this page and come back.</p></div>`;
  document.getElementById("su-copy").addEventListener("click", async e => { try{ await navigator.clipboard.writeText(r.record.value); e.target.textContent="Copied"; }catch(_){ e.target.textContent="Select and copy"; } });
  document.getElementById("su-restart").addEventListener("click", () => { saved.set(null); company(); });
  const status = document.getElementById("su-status"), check = document.getElementById("su-check");
  let timer = 0;
  const poll = async manual => {
    check.disabled = true; status.textContent = "Checking DNS…";
    try{
      const c = await api("check", {token:saved.get()?.token});
      if(c.verified){ clearInterval(timer); create(c); return; }
      status.textContent = manual ? "Not visible yet. We'll keep checking every 30 seconds." : "Still waiting for the record…";
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
    try{ await api("complete", {token:saved.get()?.token, password:form.elements.password.value}); saved.set(null); done(c); }
    catch(err){ alert.textContent = err.message; form.elements.password.value = form.elements.confirm.value = ""; busy(form, false); }
  });
}

function done(c){
  step(4);
  body.innerHTML = `<div><h2>Welcome to Dejoiy Mail 🎉</h2>
    <p><b>${esc(c.email)}</b> is ready and you're the administrator of <b>${esc(c.domain)}</b>.</p>
    <p>Next: add your team in the admin panel, then point your domain's <b>MX</b> record to <code>mail.dejoiy.com</code> so mail starts arriving.</p>
    <a class="su-btn" href="/admin">Open the admin panel</a> <a class="su-btn ghost" href="/">Open my inbox</a></div>`;
}

(async function start(){
  const pending = saved.get();
  if(!pending?.token) return company();
  try{ const c = await api("check", {token:pending.token}); c.verified ? create(c) : verify(c); }
  catch(_){ saved.set(null); company(); }
})();
})();
