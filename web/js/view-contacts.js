/* ============ Dejoiy Mail — view-contacts.js : address book with CSV import/export ============ */
(function(){
"use strict";

Views.contacts = function(el){
  if(window.Live?.enabled && !el._liveContactsReady){
    el.innerHTML='<div class="card" role="status">Loading contacts…</div>';
    Live.request('contacts').then(result=>{if(App.route!=='contacts')return;Store.state.contacts=result.contacts;el._liveContactsReady=true;Views.contacts(el);el._liveContactsReady=false;}).catch(error=>{if(App.route==='contacts')el.innerHTML=`<div class="empty-note">${esc(error.message)}</div>`;});return;
  }
  const s = Store.state;
  let q = "";

  /* Divisions: people at your own company's domain are Work family, everyone else Others. */
  const mine = String(s.user?.email||"").split("@")[1]||"";
  const division = c => c.division || (mine && String(c.email).toLowerCase().endsWith("@"+mine.toLowerCase()) ? "Work family" : "Others");
  let group = "all";
  function render(){
    const list = s.contacts.filter(c=>
      (c.name+" "+c.email+" "+(c.org||"")).toLowerCase().includes(q.toLowerCase()) && (group==="all" || division(c)===group))
      .sort((a,b)=>a.name.localeCompare(b.name));
    const row = c=>`<tr>
          <td><b>${esc(c.name)}</b></td><td>${esc(c.email)}</td><td>${esc(c.phone||"—")}</td><td>${esc(c.org||"—")}</td>
          <td style="white-space:nowrap;text-align:right">
            <button class="btn sm ghost" data-mail="${c.id}" title="Email">✉️</button>
            <button class="btn sm ghost" data-edit="${c.id}" title="Edit">✎</button>
            <button class="btn sm ghost" data-del="${c.id}" title="Delete">×</button></td>
        </tr>`;
    const sections = ["Work family","Others"].map(name=>{ const people=list.filter(c=>division(c)===name);
      return people.length ? `<tr class="ct-div" data-div="${name==="Work family"?"work":"others"}"><th colspan="5">${name==="Work family"?"🏢 Work family":"🌍 Others"} <span>${people.length}</span></th></tr>${people.map(row).join("")}` : ""; }).join("");
    const counts = {"Work family":s.contacts.filter(c=>division(c)==="Work family").length, Others:s.contacts.filter(c=>division(c)==="Others").length};
    el.innerHTML = `
      <div class="view-head"><h1>👥 Contacts</h1><span class="sub">${list.length} contacts · people you write to are saved here automatically</span><span style="flex:1"></span>
        <div class="btn-row">
          <input type="search" id="ct-q" placeholder="Search contacts…" value="${esc(q)}" style="width:200px">
          <button class="btn sm" id="ct-add">+ Add</button>
          <button class="btn sm" id="ct-export">Export CSV</button>
          <label class="btn sm" style="cursor:pointer">Import CSV<input type="file" id="ct-import" accept=".csv" class="sr"></label>
        </div></div>
      <div class="ct-groups" role="radiogroup" aria-label="Division">${[["all","All",s.contacts.length],["Work family","🏢 Work family"+(mine?" · @"+mine:""),counts["Work family"]],["Others","🌍 Others",counts.Others]].map(([id,label,n])=>
        `<button type="button" role="radio" class="chip-filter" data-group="${esc(id)}" aria-checked="${group===id}">${esc(label)} <b>${n}</b></button>`).join("")}</div>
      <div class="card" style="padding:0;overflow:hidden"><table class="tbl ct-tbl">
        <thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Organisation</th><th></th></tr></thead>
        <tbody>${sections || `<tr><td colspan="5"><div class="empty-note">No contacts match.</div></td></tr>`}</tbody>
      </table></div>`;
    el.querySelectorAll("[data-group]").forEach(b=>b.addEventListener("click",()=>{ group=b.dataset.group; render(); }));
    el.querySelector("#ct-q").addEventListener("input", ev=>{ q = ev.target.value;
      const pos = ev.target.selectionStart; render(); const nq = el.querySelector("#ct-q"); nq.focus(); nq.setSelectionRange(pos,pos); });
    el.querySelector("#ct-add").addEventListener("click", ()=> editDialog(null));
    el.querySelector("#ct-export").addEventListener("click", exportCsv);
    el.querySelector("#ct-import").addEventListener("change", importCsv);
    el.querySelectorAll("[data-edit]").forEach(b=> b.addEventListener("click", ()=> editDialog(s.contacts.find(c=>c.id===b.dataset.edit))));
    el.querySelectorAll("[data-del]").forEach(b=> b.addEventListener("click", ()=>{
      const c = s.contacts.find(x=>x.id===b.dataset.del);
      App.confirm(`Delete ${c.name}?`, async ()=>{try{if(window.Live?.enabled)await Live.request('contacts',{op:'delete',id:c.id});s.contacts = s.contacts.filter(x=>x.id!==c.id); Store.save(); render(); App.toast("Contact deleted.");}catch(error){App.toast(error.message);} });
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
        if(window.Live?.enabled){
          const button=document.querySelector('.dlg-foot .primary');if(button.disabled)return false;button.disabled=true;
          const contact={id:isNew?undefined:c.id,name,email,phone:document.getElementById("cc-phone").value.trim(),org:document.getElementById("cc-org").value.trim(),presence:'off'};
          Live.request('contacts',{op:'save',...contact}).then(result=>{contact.id=result.id;if(isNew)s.contacts.push(contact);else Object.assign(c,contact);App.closeDialog();render();App.toast('Contact saved.');}).catch(error=>{button.disabled=false;App.toast(error.message);});return false;
        }
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
    r.onload = async ()=>{
      let added = 0;
      let failure='';
      for(const line of String(r.result).split(/\r?\n/).slice(1)){
        const parts = line.match(/(".*?"|[^",]+)(?=\s*,|\s*$)/g); if(!parts || parts.length<2) continue;
        const clean = v => v.replace(/^"|"$/g,"").replace(/""/g,'"').trim();
        const name = clean(parts[0]), email = clean(parts[1]);
        if(name && email && /.+@.+\..+/.test(email)){
          const contact={id:uid('c'),name,email,phone:clean(parts[2]||''),org:clean(parts[3]||''),presence:'off'};
          if(window.Live?.enabled){try{const result=await Live.request('contacts',{...contact,id:undefined,op:'save'});contact.id=result.id;}catch(error){failure=error.message;break;}}
          s.contacts.push(contact);added++;
        }
      }
      Store.save(); render(); App.toast(added ? `Imported ${added} contacts ✓` : "No valid contacts found in CSV.");
      if(failure)App.toast(`Import stopped after ${added} contacts: ${failure}`);
    };
    r.readAsText(f); ev.target.value="";
  }

  render();
};
})();
