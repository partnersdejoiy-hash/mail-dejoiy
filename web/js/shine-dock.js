/* Shine chat inside Dejoiy Mail, like Gmail's chat: a sticker bubble (desktop) or the Chat tab (phone)
   opens Shine's chats in a docked panel. The server hands us a short-lived sign-in token, so the
   person is already signed in to Shine with their mailbox account. */
const ShineDock = (() => {
  let origin = "", panel = null, frame = null, bubble = null, unread = 0, ready = null, pushed = false;
  const phone = () => matchMedia("(max-width:899px)").matches;
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function badge() {
    const text = unread > 99 ? "99+" : String(unread);
    document.querySelectorAll("[data-shine-badge]").forEach(el => { el.textContent = text; el.hidden = !unread; });
  }

  async function token() {
    const r = await fetch("/api/shine", { credentials: "same-origin", headers: { Accept: "application/json" } });
    const d = await r.json().catch(() => ({}));
    if (!r.ok || !d.enabled) throw new Error(d.error || "Shine chat isn't connected to this mailbox yet.");
    origin = d.origin; return d.token;
  }

  function build() {
    panel = document.createElement("section");
    panel.className = "shine-dock"; panel.hidden = true;
    panel.setAttribute("role", "dialog"); panel.setAttribute("aria-label", "Shine chat");
    panel.innerHTML = `<header class="shine-dock-head">
        <button class="shine-dock-btn shine-back" data-act="close" aria-label="Back to mail">‹</button>
        <span class="shine-dock-logo" aria-hidden="true"></span><b>Shine</b><small>chat</small>
        <span class="shine-dock-tools">
          <button class="shine-dock-btn" data-act="full" title="Open Shine in a new tab" aria-label="Open Shine in a new tab">↗</button>
          <button class="shine-dock-btn shine-x" data-act="close" title="Close" aria-label="Close chat">×</button>
        </span></header>
      <div class="shine-dock-body"><p class="shine-dock-msg" role="status"><span class="shine-dock-spin"></span>Opening Shine…</p></div>`;
    panel.addEventListener("click", e => {
      const act = e.target.closest("[data-act]")?.dataset.act;
      if (act === "close") close();
      if (act === "full" && origin) window.open(origin + "/app/chats", "_blank", "noopener");
    });
    document.body.append(panel);
  }

  function load() {
    if (ready) return ready;
    if (!panel) build();
    ready = token().then(t => {
      frame = document.createElement("iframe");
      frame.title = "Shine chat";
      frame.allow = "camera; microphone; display-capture; autoplay; clipboard-write; fullscreen";
      frame.src = `${origin}/auth/dejoiy?embed=1#t=${encodeURIComponent(t)}&next=${encodeURIComponent("/app/chats?embed=1")}`;
      frame.addEventListener("load", () => panel.classList.add("is-ready"), { once: true });
      panel.querySelector(".shine-dock-body").append(frame);
    }).catch(err => {
      ready = null;
      panel.querySelector(".shine-dock-msg").innerHTML = `<b>Chat is not available</b>${esc(err.message)}`;
      throw err;
    });
    return ready;
  }

  function open() {
    if (!panel) build();
    panel.hidden = false; requestAnimationFrame(() => panel.classList.add("is-open"));
    document.body.classList.add("shine-open");
    if (phone() && !pushed) { history.pushState({ shineDock: 1 }, ""); pushed = true; }
    load().catch(() => {});
  }
  function close(fromHistory) {
    if (!panel || panel.hidden) return;
    panel.classList.remove("is-open"); document.body.classList.remove("shine-open");
    setTimeout(() => { if (!panel.classList.contains("is-open")) panel.hidden = true; }, 220);
    if (pushed) { pushed = false; if (!fromHistory) history.back(); }
  }
  const toggle = () => (panel && !panel.hidden && panel.classList.contains("is-open") ? close() : open());

  function init() {
    if (!window.Live || !Live.enabled || bubble) return;
    bubble = document.createElement("button");
    bubble.className = "shine-bubble"; bubble.type = "button";
    bubble.setAttribute("aria-label", "Open Shine chat");
    bubble.innerHTML = `${window.Icons ? Icons.get("chat") : "💬"}<span>Chat</span><i data-shine-badge hidden></i>`;
    bubble.addEventListener("click", toggle);
    document.body.append(bubble);
    addEventListener("message", e => {
      if (!origin || e.origin !== origin || !e.data || e.data.type !== "shine:unread") return;
      unread = Math.max(0, Number(e.data.count) || 0); badge();
    });
    addEventListener("popstate", () => { if (pushed) { pushed = false; close(true); } });
    addEventListener("keydown", e => { if (e.key === "Escape" && panel && !panel.hidden) close(); });
    // load Shine quietly once the inbox has settled, so the unread count shows like Gmail's chat
    if (!navigator.connection?.saveData) setTimeout(() => (window.requestIdleCallback || setTimeout)(() => { if (!panel) build(); load().catch(() => {}); }), 4000);
  }

  return { init, open, close, toggle, badge };
})();
window.ShineDock = ShineDock;
