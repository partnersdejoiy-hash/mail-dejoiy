/* ============ Dejoiy Mail — view-contacts.js : address book with CSV import/export ============ */
(function(){
"use strict";

Views.contacts = function(el){
  const s = Store.state;
  let q = "";

  function render(){
    const list = s.contacts.filter(c=>
      (c.name+" "+c.email+" "+(c.org||"")).toLowerCase().includes(q.toLowerCase()))
      .sort((a,b)=>a.name.localeCompare(b.name));
    el.innerHTML = `
      <div class="view-head"><h1>👥 Contacts</h1><span class="sub">${list.length} contacts</span><span style="flex:1"></span>
        <div class="btn-row">
          <input type="search" id="ct-q" placeholder="Search contacts…" value="${esc(q)}" style="width:200px">
          <button class="btn sm" id="ct-add">+ Add</button>
          <button class="btn sm" id="ct-export">Export CSV</button>
          <label class="btn sm" style="cursor:pointer">Import CSV<input type="file" id="ct-import" accept=".csv" class="sr"></label>
        </div></div>
      <div class="card" style="padding:0;overflow:hidden"><table class="tbl">
        <thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Organisation</th><th></th></tr></thead>
        <tbody>${list.map(c=>`<tr>
          <td><b>${esc(c.name)}</b></td><td>${esc(c.email)}</td><td>${esc(c.phone||"—")}</td><td>${esc(c.org||"—")}</td>
          <td style="white-space:nowrap;text-align:right">
            <button class="btn sm ghost" data-mail="${c.id}" title="Email">✉️</button>
            <button class="btn sm ghost" data-edit="${c.id}" title="Edit">✎</button>
            <button class="btn sm ghost" data-del="${c.id}" title="Delete">×</button></td>
        </tr>`).join("") || `<tr><td colspan="5"><div class="empty-note">No contacts match.</div></td></tr>`}</tbody>
      </table></div>`;
    el.querySelector("#ct-q").addEventListener("input", ev=>{ q = ev.target.value;
      const pos = ev.target.selectionStart; render(); const nq = el.querySelector("#ct-q"); nq.focus(); nq.setSelectionRange(pos,pos); });
    el.querySelector("#ct-add").addEventListener("click", ()=> editDialog(null));
    el.querySelector("#ct-export").addEventListener("click", exportCsv);
    el.querySelector("#ct-import").addEventListener("change", importCsv);
    el.querySelectorAll("[data-edit]").forEach(b=> b.addEventListener("click", ()=> editDialog(s.contacts.find(c=>c.id===b.dataset.edit))));
    el.querySelectorAll("[data-del]").forEach(b=> b.addEventListener("click", ()=>{
      const c = s.contacts.find(x=>x.id===b.dataset.del);
      App.confirm(`Delete ${c.name}?`, ()=>{ s.contacts = s.contacts.filter(x=>x.id!==c.id); Store.save(); render(); App.toast("Contact deleted."); });
    }));
    el.querySelectorAll("[data-mail]").forEach(b=> b.addEventListener("click", ()=>{
      const c = s.contacts.find(x=>x.id===b.dataset.mail);
      App.go("compose:new"); setTimeout(()=>{ const t=document.getElementById("c-to"); if(t) t.value=c.email; },120);
    }));
  }

  function editDialog(c){
    const isNew = !c; c = c || {name:"",email:"",phone:"",org:""};
    App.dialog({ title: isNew?"Add contact":"Edit contact", body:`
      <div class="field"><label>Name</label><input type="text" id="cc-name" value="${esc(c.name)}"></div>
      <div class="field"><label>Email</label><input type="email" id="cc-email" value="${esc(c.email)}"></div>
      <div class="grid c2"><div class="field"><label>Phone</label><input type="text" id="cc-phone" value="${esc(c.phone||"")}"></div>
      <div class="field"><label>Organisation</label><input type="text" id="cc-org" value="${esc(c.org||"")}"></div></div>`,
      actions:[{label:"Cancel"},{label:"Save", primary:true, fn:()=>{
        const name = document.getElementById("cc-name").value.trim(), email = document.getElementById("cc-email").value.trim();
        if(!name || !email){ App.toast("Name and email are required."); return false; }
        if(isNew) s.contacts.push({id:uid("c"), name, email, phone:document.getElementById("cc-phone").value.trim(), org:document.getElementById("cc-org").value.trim(), presence:"off"});
        else Object.assign(c, {name, email, phone:document.getElementById("cc-phone").value.trim(), org:document.getElementById("cc-org").value.trim()});
        Store.save(); render(); App.toast("Contact saved ✓");
      }}]});
  }

  function exportCsv(){
    const rows = [["Name","Email","Phone","Organisation"]]
      .concat(s.contacts.map(c=>[c.name,c.email,c.phone||"",c.org||""]))
      .map(r=>r.map(x=>`"${String(x).replace(/"/g,'""')}"`).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([rows], {type:"text/csv"}));
    a.download = "dejoiy-contacts.csv"; a.click(); URL.revokeObjectURL(a.href);
    App.toast("Contacts exported ✓");
  }

  function importCsv(ev){
    const f = ev.target.files[0]; if(!f) return;
    const r = new FileReader();
    r.onload = ()=>{
      let added = 0;
      String(r.result).split(/\r?\n/).slice(1).forEach(line=>{
        const parts = line.match(/(".*?"|[^",]+)(?=\s*,|\s*$)/g); if(!parts || parts.length<2) return;
        const clean = v => v.replace(/^"|"$/g,"").replace(/""/g,'"').trim();
        const name = clean(parts[0]), email = clean(parts[1]);
        if(name && email && /.+@.+\..+/.test(email)){ s.contacts.push({id:uid("c"), name, email, phone:clean(parts[2]||""), org:clean(parts[3]||""), presence:"off"}); added++; }
      });
      Store.save(); render(); App.toast(added ? `Imported ${added} contacts ✓` : "No valid contacts found in CSV.");
    };
    r.readAsText(f); ev.target.value="";
  }

  render();
};
})();
