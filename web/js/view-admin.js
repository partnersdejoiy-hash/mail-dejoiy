/* ============ Dejoiy Mail — view-admin.js : organisation admin panel ============ */
(function(){
"use strict";

Views.admin = function(el){
  if(window.Live?.enabled){ renderLiveAdmin(el); return; }
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

async function renderLiveAdmin(el){
  const current=()=>App.route==='admin' && el.isConnected!==false;
  el.innerHTML='<div class="view-head"><h1>🛡️ Dejoiy Mail Admin</h1></div><div class="card" role="status">Loading administration…</div>';
  let data;
  try{data=await Live.request('admin');}
  catch(error){
    if(!current())return;
    el.innerHTML=`<div class="view-head"><h1>🛡️ Dejoiy Mail Admin</h1></div>
      <form class="card" id="admin-login" style="max-width:480px"><h3>Administrator verification</h3>
      <p>${esc(error.message)}</p><p>Signed in as ${esc(Store.state.user.email)}. Use an administrator mailbox to manage users and domains.</p>
      <div class="field"><label for="admin-password">Administrator password</label><input id="admin-password" type="password" autocomplete="current-password" required></div>
      <p role="alert"></p><button class="btn primary">Verify administrator</button></form>`;
    el.querySelector('form').addEventListener('submit',async event=>{
      event.preventDefault();const form=event.currentTarget;const button=form.querySelector('button');button.disabled=true;
      try{await Live.request('admin/login',{password:form.querySelector('input').value});form.reset();await renderLiveAdmin(el);}
      catch(err){form.querySelector('[role=alert]').textContent=err.message;form.reset();button.disabled=false;}
    });return;
  }
  if(!current())return;
  const users=data.users,domains=data.domains;
  el.innerHTML=`<div class="view-head"><h1>🛡️ Dejoiy Mail Admin</h1><span class="sp"></span><button class="btn" id="admin-refresh">Refresh</button><button class="btn ghost" id="admin-lock">Lock admin</button></div>
    <div class="grid c2" style="margin-bottom:14px"><div class="card"><div class="stat">${users.length}</div><div class="stat-sub">Mailboxes</div></div><div class="card"><div class="stat">${domains.length}</div><div class="stat-sub">Domains</div></div></div>
    <div class="card"><h3>👥 Users</h3><div style="overflow:auto"><table class="tbl"><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th></th></tr></thead><tbody>
    ${users.map((u,i)=>`<tr><td>${esc(u.name)}</td><td>${esc(u.email)}</td><td>${esc(u.role)}</td><td><select data-status="${i}" aria-label="Status for ${esc(u.email)}">${['active','locked','maintenance'].map(s=>`<option value="${s}" ${s===u.status?'selected':''}>${s}</option>`).join('')}${['active','locked','maintenance'].includes(u.status)?'':`<option selected value="${esc(u.status)}">${esc(u.status)}</option>`}</select></td><td><button class="btn sm" data-password="${i}">Reset password</button></td></tr>`).join('')}
    </tbody></table></div></div>
    <div class="grid c2" style="margin-top:14px;align-items:start">
      <form class="card" id="admin-add-user"><h3>Add mailbox</h3>
      <div class="field"><label for="admin-name">Display name</label><input id="admin-name" name="displayName" required maxlength="200"></div>
      <div class="field"><label for="admin-email">Email</label><input id="admin-email" name="email" type="email" required autocomplete="off"></div>
      <div class="field"><label for="admin-new-password">Initial password</label><input id="admin-new-password" name="password" type="password" required autocomplete="new-password"></div>
      <p role="alert"></p><button class="btn primary">Create mailbox</button></form>
      <div><div class="card"><h3>🌐 Domains</h3><table class="tbl"><thead><tr><th>Domain</th><th>Status</th></tr></thead><tbody>${domains.map(d=>`<tr><td>${esc(d.domain)}</td><td>${esc(d.status)}</td></tr>`).join('')}</tbody></table>
      <p class="hint">Creating a domain here does not update its public DNS. Configure MX, SPF, DKIM and DMARC with your DNS provider.</p></div>
      <form class="card" id="admin-add-domain" style="margin-top:14px"><h3>Add domain</h3><div class="field"><label for="admin-domain">Domain name</label><input id="admin-domain" name="domain" required placeholder="example.com" autocomplete="off"></div><p role="alert"></p><button class="btn primary">Create domain</button></form></div></div>`;
  el.querySelector('#admin-refresh').addEventListener('click',()=>renderLiveAdmin(el));
  el.querySelector('#admin-lock').addEventListener('click',async()=>{try{await Live.request('admin/logout',{});await renderLiveAdmin(el);}catch(e){App.toast(e.message);}});
  el.querySelectorAll('[data-status]').forEach(select=>select.addEventListener('change',async()=>{
    const user=users[+select.dataset.status];const status=select.value;select.disabled=true;
    try{await Live.request('admin/action',{op:'status',id:user.id,status});user.status=status;App.toast('Mailbox status updated.');}
    catch(error){select.value=user.status;App.toast(error.message);}finally{select.disabled=false;}
  }));
  el.querySelectorAll('[data-password]').forEach(button=>button.addEventListener('click',()=>{
    const user=users[+button.dataset.password];
    App.dialog({title:'Reset mailbox password',body:`<p>${esc(user.email)}</p><div class="field"><label for="admin-reset-password">New password</label><input id="admin-reset-password" type="password" autocomplete="new-password" required></div><p id="admin-reset-error" role="alert"></p>`,actions:[{label:'Cancel'},{label:'Set password',primary:true,fn:()=>{
      const input=document.getElementById('admin-reset-password');const password=input.value;
      if(input.disabled)return false;input.disabled=true;
      Live.request('admin/action',{op:'password',id:user.id,password}).then(()=>{input.value='';App.closeDialog();App.toast('Mailbox password updated.');}).catch(error=>{input.disabled=false;input.value='';document.getElementById('admin-reset-error').textContent=error.message;});return false;
    }}]});
  }));
  for(const [id,op] of [['admin-add-user','create_user'],['admin-add-domain','create_domain']]){
    el.querySelector('#'+id).addEventListener('submit',async event=>{
      event.preventDefault();const form=event.currentTarget;const button=form.querySelector('button');button.disabled=true;
      const payload=op==='create_user'?{op,name:form.elements.displayName.value,email:form.elements.email.value,password:form.elements.password.value}:{op,domain:form.elements.domain.value};
      try{await Live.request('admin/action',payload);form.reset();App.toast(op==='create_user'?'Mailbox created.':'Domain created; configure its public DNS.');await renderLiveAdmin(el);}
      catch(error){form.querySelector('[role=alert]').textContent=error.message;if(form.elements.password)form.elements.password.value='';button.disabled=false;}
    });
  }
}
})();
