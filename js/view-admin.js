/* ============ Dejoiy Mail — view-admin.js : organisation admin panel ============ */
(function(){
"use strict";

Views.admin = function(el){
  const a = Store.state.admin;
  const st = Mail.storage();

  function render(){
    el.innerHTML = `
      <div class="view-head"><h1>🛡️ Admin</h1><span class="sub">${esc(a.org)}</span></div>
      <div class="grid c4" style="margin-bottom:14px">
        <div class="card"><div class="stat">${a.users.length}</div><div class="stat-sub">Users</div></div>
        <div class="card"><div class="stat">${a.domains.length}</div><div class="stat-sub">Domains</div></div>
        <div class="card"><div class="stat">${st.used}<span style="font-size:14px"> MB</span></div><div class="stat-sub">of ${(st.total/1024).toFixed(0)} GB used</div></div>
        <div class="card"><div class="stat">${Store.state.filters.filter(f=>f.on).length}</div><div class="stat-sub">Active filters</div></div>
      </div>
      <div class="grid c2" style="align-items:start">
        <div class="card"><h3>👥 Users</h3>
          <table class="tbl"><thead><tr><th>Name</th><th>Email</th><th>Role</th><th></th></tr></thead><tbody>
          ${a.users.map((u,i)=>`<tr><td><b>${esc(u.name)}</b></td><td>${esc(u.email)}</td>
            <td><select data-role="${i}" style="width:auto;padding:4px 8px">
              ${["User","Admin","Super Admin"].map(r=>`<option ${u.role===r?"selected":""}>${r}</option>`).join("")}</select></td>
            <td style="text-align:right"><button class="btn sm ghost" data-deluser="${i}">×</button></td></tr>`).join("")}
          </tbody></table>
          <div class="btn-row" style="margin-top:10px"><button class="btn sm primary" id="adm-adduser">+ Add user</button></div></div>
        <div class="card"><h3>🌐 Domains</h3>
          <table class="tbl"><thead><tr><th>Domain</th><th>MX</th><th>SPF</th><th>DKIM</th><th>DMARC</th></tr></thead><tbody>
          ${a.domains.map((d,i)=>`<tr><td><b>${esc(d.domain)}</b></td>
            ${["mx","spf","dkim","dmarc"].map(k=>`<td><button class="pill-toggle" role="switch" aria-checked="${d[k]}" data-dk="${k}" data-di="${i}" aria-label="${k} for ${esc(d.domain)}"></button></td>`).join("")}</tr>`).join("")}
          </tbody></table>
          <p class="hint" style="margin-top:10px;font-size:12px;color:var(--ink-3)">Toggle a record off if it isn't configured yet at your DNS host. For real deliverability, SPF + DKIM + DMARC should all be green.</p>
          <div class="btn-row" style="margin-top:10px"><button class="btn sm" id="adm-adddomain">+ Add domain</button></div></div>
      </div>`;
    el.querySelector("#adm-adduser").addEventListener("click", ()=>{
      App.dialog({title:"Add user", body:`
        <div class="field"><label>Name</label><input type="text" id="au-name"></div>
        <div class="field"><label>Email</label><input type="email" id="au-email" placeholder="name@${esc(a.domains[0]?a.domains[0].domain:"dejoiy.com")}"></div>
        <div class="field"><label>Role</label><select id="au-role"><option>User</option><option>Admin</option><option>Super Admin</option></select></div>`,
        actions:[{label:"Cancel"},{label:"Add user", primary:true, fn:()=>{
          const name=document.getElementById("au-name").value.trim(), email=document.getElementById("au-email").value.trim();
          if(!name||!/.+@.+\..+/.test(email)){ App.toast("Enter a valid name and email."); return false; }
          a.users.push({name, email, role:document.getElementById("au-role").value});
          Store.save(); render(); App.toast("User added ✓");
        }}]});
    });
    el.querySelectorAll("[data-deluser]").forEach(b=> b.addEventListener("click", ()=>{
      const u = a.users[+b.dataset.deluser];
      App.confirm(`Remove ${u.name} (${u.email})?`, ()=>{ a.users.splice(+b.dataset.deluser,1); Store.save(); render(); App.toast("User removed."); });
    }));
    el.querySelectorAll("[data-role]").forEach(s2=> s2.addEventListener("change", ()=>{
      a.users[+s2.dataset.role].role = s2.value; Store.save(); App.toast("Role updated.");
    }));
    el.querySelectorAll("[data-dk]").forEach(t=> t.addEventListener("click", ()=>{
      const d = a.domains[+t.dataset.di]; d[t.dataset.dk] = !d[t.dataset.dk]; Store.save(); render();
    }));
    el.querySelector("#adm-adddomain").addEventListener("click", ()=>{
      App.promptDialog("Add domain", "Domain name (e.g. example.com):", "", v=>{
        v=v.trim().toLowerCase(); if(!v) return;
        if(a.domains.some(d=>d.domain===v)){ App.toast("Domain already added."); return; }
        a.domains.push({domain:v, mx:false, spf:false, dkim:false, dmarc:false});
        Store.save(); render(); App.toast("Domain added — point its MX to Dejoiy Mail, then enable the records.");
      });
    });
  }
  render();
};
})();
