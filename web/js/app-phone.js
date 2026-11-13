/* ============ Dejoiy Mail — app-phone.js : the clean phone app look ============
   Phones only, and only while Settings → Phone app look is "Clean" (the default).
   Adds a title header (folder + unread, compose, search), a bottom action bar while reading,
   a "More" sheet and a text-size button. Every action presses the reader's own buttons,
   so nothing about how mail is moved, deleted or marked is duplicated here. */
const Phone = {
  SIZES: [15, 17, 19],
  on(){ return document.documentElement.dataset.appLook === "clean" && matchMedia("(max-width:680px)").matches; },

  init(){
    const bar = document.getElementById("topbar"), actions = bar.querySelector(".top-actions");
    const title = document.createElement("button");
    title.id = "ph-title"; title.type = "button"; title.setAttribute("aria-label", "Open folders");
    title.innerHTML = '<span class="ph-name"></span><span class="ph-sub"></span>';
    title.addEventListener("click", () => document.getElementById("menu-btn").click());
    bar.insertBefore(title, bar.querySelector(".search-wrap"));
    for (const [id, icon, label, fn] of [["ph-compose", "compose", "Compose", () => App.go("compose:new")], ["ph-search", "search", "Search mail", () => this.search(true)]]) {
      const b = document.createElement("button");
      b.id = id; b.type = "button"; b.className = "icon-btn ph-only"; b.title = label; b.setAttribute("aria-label", label); b.innerHTML = Icons.get(icon);
      b.addEventListener("click", fn); actions.insertBefore(b, document.getElementById("account-btn"));
    }
    const cancel = document.createElement("button");
    cancel.id = "ph-search-x"; cancel.type = "button"; cancel.className = "ph-only"; cancel.textContent = "Cancel";
    cancel.addEventListener("click", () => this.search(false));
    bar.querySelector(".search-wrap").after(cancel);

    /* reading a message: actions sit at the bottom, in thumb reach */
    const read = document.createElement("div");
    read.id = "ph-readbar"; read.setAttribute("role", "toolbar"); read.setAttribute("aria-label", "Message actions");
    read.innerHTML = [["r-trash", "trash", "Delete"], ["r-archive", "archive", "Archive"], ["r-reply", "reply", "Reply"], ["r-fwd", "forward", "Forward"], ["", "more", "More"]]
      .map(([press, icon, label]) => `<button type="button" data-press="${press}">${Icons.get(icon)}<span>${label}</span></button>`).join("");
    read.addEventListener("click", ev => { const b = ev.target.closest("button"); if (!b) return; if (b.dataset.press) this.press(b.dataset.press); else this.sheet(); });
    document.body.append(read);
    const size = document.createElement("button");
    size.id = "ph-size"; size.type = "button"; size.title = "Text size"; size.setAttribute("aria-label", "Change text size"); size.innerHTML = "<small>a</small>A";
    size.addEventListener("click", () => this.textSize(true));
    document.body.append(size);
    this.textSize(false);

    for (const name of ["render", "refreshNav"]) { const original = App[name]; App[name] = function(){ const out = original.apply(this, arguments); Phone.sync(); return out; }; }
    matchMedia("(max-width:680px)").addEventListener("change", () => this.sync());
    this.sync();
  },

  /* header title: where you are, and how much is unread */
  sync(){
    const title = document.getElementById("ph-title"); if (!title || !App.route) return;
    const route = App.route, names = {today: "Home", calendar: "Calendar", contacts: "Contacts", settings: "Settings", notes: "Notes", chat: "Chat", compose: "New message", search: "Search"};
    let name = names[route] || "Dejoiy Mail", sub = "";
    if (route === "mail") {
      name = Mail.folderName(App.ui.folder);
      const unread = Store.state.emails.filter(e => e.folder === App.ui.folder && !e.read).length;
      sub = unread ? unread + " unread" : "All read";
    }
    title.querySelector(".ph-name").textContent = name; title.querySelector(".ph-sub").textContent = sub;
    if (route !== "mail" && route !== "search") this.search(false, true);
  },

  search(open, quiet){
    const input = document.getElementById("global-search");
    document.body.classList.toggle("ph-searching", open);
    if (open) input.focus();
    else if (!quiet) { if (input.value) { input.value = ""; input.dispatchEvent(new Event("input", {bubbles: true})); } if (App.route === "search") App.go("mail:inbox"); }
  },

  press(id){ const b = document.getElementById(id); if (b) b.click(); },

  textSize(step){
    let i = 0; try { i = +localStorage.getItem("dejoiy-read-size") || 0; } catch (_) {}
    if (step) { i = (i + 1) % this.SIZES.length; try { localStorage.setItem("dejoiy-read-size", i); } catch (_) {} }
    document.documentElement.style.setProperty("--ph-read", this.SIZES[i] + "px");
  },

  /* "More": the rest of the reader's actions as a bottom sheet */
  sheet(){
    const starred = document.getElementById("r-star")?.classList.contains("on");
    const items = [["r-replyall", "replyall", "Reply all"], ["r-star", "star", starred ? "Remove star" : "Star"], ["r-unread", "unread", "Mark as unread"],
      ["r-spam", "spam", "Mark as spam"], ["r-print", "print", "Print"], ["", "", "Text size"]];
    const wrap = document.createElement("div");
    wrap.id = "ph-sheet";
    wrap.innerHTML = `<div class="ph-scrim"></div><div class="ph-panel" role="dialog" aria-modal="true" aria-label="More actions"><button type="button" class="ph-close" aria-label="Close">×</button>${
      items.map(([press, icon, label]) => `<button type="button" class="ph-item" data-press="${press}">${icon ? Icons.get(icon) : '<span class="ph-aa"><small>a</small>A</span>'}<span>${label}</span></button>`).join("")}</div>`;
    const close = () => { wrap.remove(); removeEventListener("popstate", close); Back.closed(); };
    wrap.addEventListener("click", ev => {
      const item = ev.target.closest(".ph-item");
      if (item) { if (item.dataset.press) { close(); this.press(item.dataset.press); } else this.textSize(true); }
      else if (ev.target.closest(".ph-scrim,.ph-close")) close();
    });
    wrap.addEventListener("keydown", ev => { if (ev.key === "Escape") close(); });
    document.body.append(wrap); Back.open(); addEventListener("popstate", close);
    wrap.querySelector(".ph-item").focus();
  }
};
window.Phone = Phone;
Phone.init();
