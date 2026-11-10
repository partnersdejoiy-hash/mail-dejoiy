/* ============ Dejoiy Mail — landing.js : motion and the interactive bits of both landing pages ============
   Everything works without it: links are links, the claim form is a plain GET form. */
(function(){
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $$ = (s, r=document) => [...r.querySelectorAll(s)];

  /* entrances: the parts of each section arrive one after another */
  const io = "IntersectionObserver" in window && new IntersectionObserver(entries => entries.forEach(e => {
    if(!e.isIntersecting) return; e.target.classList.add("in"); io.unobserve(e.target);
  }), {rootMargin:"0px 0px -8% 0px"});
  $$(".rv").forEach(el => {
    const sibs = $$(".rv", el.parentElement).filter(x => x.parentElement === el.parentElement);
    el.style.setProperty("--rd", Math.max(0, sibs.indexOf(el)) * 80 + "ms");
    io ? io.observe(el) : el.classList.add("in");
  });

  /* colour picker: a click previews the colour on the whole page, Save keeps it in this browser */
  const swatches = document.querySelector("[data-swatches]");
  if(swatches && window.DejoiyAccent){
    const A = window.DejoiyAccent, msg = document.querySelector("[data-colour-msg]");
    let current = A.saved();
    const label = n => n[0].toUpperCase() + n.slice(1);
    swatches.innerHTML = Object.keys(A.COLOURS).map(n =>
      `<button type="button" role="radio" aria-label="${label(n)}" aria-checked="${n === current}" data-colour="${n}" style="--c:${A.COLOURS[n][0]}"></button>`).join("");
    $$("[data-colour]", swatches).forEach(b => b.addEventListener("click", () => {
      current = b.dataset.colour; A.apply(current);
      $$("[data-colour]", swatches).forEach(x => x.setAttribute("aria-checked", x === b));
      msg.textContent = current === A.saved() ? "" : "Previewing " + label(current) + ". Save to keep it.";
    }));
    document.querySelector("[data-save-colour]").addEventListener("click", () => {
      A.save(current); msg.textContent = "Saved. This browser stays " + label(current) + ".";
    });
  }

  /* sentences with switches */
  $$(".lp-switch").forEach(band => {
    const t = band.querySelector(".lp-toggle");
    t.addEventListener("click", () => {
      const on = t.getAttribute("aria-checked") !== "true";
      t.setAttribute("aria-checked", on); band.classList.toggle("is-on", on);
    });
  });

  /* signature move: the hero screenshots crossfade, slowly, while the tab is visible */
  $$("[data-fade]").forEach(box => {
    const imgs = $$("img", box); if(reduce || imgs.length < 2) return;
    let i = 0;
    setInterval(() => {
      if(document.hidden) return;
      imgs[i].classList.remove("is-on"); i = (i + 1) % imgs.length; imgs[i].classList.add("is-on");
    }, 5600);
  });

  /* showcase: pick a look, the D changes colour and the screen swaps */
  const stage = document.querySelector("[data-stage]");
  if(stage){
    const looks = [
      ["var(--pink)", "The default. Your colour, ink and plenty of white."],
      ["#2a1f5c", "One of the photo themes: a night sky behind your inbox."],
      ["#121212", "Every theme has a dark side. Easy on the eyes at 2 a.m."],
      ["#f59e6b", "Big screens get the full scene, from Sydney at sunset to snow."],
      ["var(--soft)", "Open a message and Reply sits right where your thumb is."]
    ];
    const tabs = $$("[data-look]"), imgs = $$("img", stage), fact = document.querySelector(".lp-show-fact");
    const pick = n => {
      tabs.forEach((t, k) => { t.setAttribute("aria-selected", k === n); t.tabIndex = k === n ? 0 : -1; });
      imgs.forEach((im, k) => im.classList.toggle("is-on", k === n));
      stage.style.background = looks[n][0]; fact.textContent = looks[n][1];
    };
    tabs.forEach((t, k) => {
      t.addEventListener("click", () => pick(k));
      t.addEventListener("keydown", e => {
        const d = {ArrowDown:1, ArrowRight:1, ArrowUp:-1, ArrowLeft:-1}[e.key]; if(!d) return;
        e.preventDefault(); const n = (k + d + tabs.length) % tabs.length; pick(n); tabs[n].focus();
      });
    });
    pick(0);
  }

  /* pricing: monthly or yearly on every plan, and a team-size slider that names the plan and the saving */
  const plans = $$(".lp-plan");
  if(plans.length){
    const inr = n => "₹" + Math.round(n).toLocaleString("en-IN");
    const seats = document.getElementById("lp-seats"), out = document.getElementById("lp-seats-out"), calc = document.getElementById("lp-calc-out");
    let yearly = false;
    const render = () => {
      plans.forEach(el => {
        const m = +el.dataset.month, y = +el.dataset.year;
        el.querySelector("[data-amount]").textContent = (yearly ? y : m).toLocaleString("en-IN");
        el.querySelector("[data-per]").textContent = yearly ? "/year" : "/month";
        el.querySelector("[data-alt]").textContent = yearly ? `or ${inr(m)}/month` : `or ${inr(y)}/year · 2 months free`;
        el.querySelector("[data-choose]").href = `/signup?plan=${el.dataset.plan}&billing=${yearly ? "year" : "month"}`;
      });
      const n = +seats.value, plan = plans.find(el => n <= +el.dataset.seats) || plans[plans.length - 1];
      plans.forEach(el => el.classList.toggle("is-pick", el === plan));
      out.textContent = n;
      const ours = yearly ? +plan.dataset.year / 12 : +plan.dataset.month;
      calc.innerHTML = `<b>${plan.querySelector("h3").textContent}</b> fits. You pay <b>${inr(ours)} a month</b> for everyone (${n > 1 ? "about " + inr(Math.max(1, ours / n)) + " a person" : "just you"}). ` +
        `The same team on Zoho Mail Lite: ${inr(59 * n)}. On Google Workspace Starter: ${inr(270 * n)}.`;
    };
    seats.addEventListener("input", render);
    $$("[data-bill]").forEach(b => b.addEventListener("click", () => {
      yearly = b.dataset.bill === "year";
      $$("[data-bill]").forEach(x => x.setAttribute("aria-checked", x === b));
      render();
    }));
    render();
  }

  /* claim form: tidy what was typed before it goes to sign-up */
  const claim = document.querySelector(".lp-claim-form");
  if(claim) claim.addEventListener("submit", () => {
    const d = claim.elements.domain, l = claim.elements.local;
    d.value = d.value.trim().toLowerCase().replace(/^https?:\/\//, "").replace(/^www\./, "").replace(/\/.*$/, "");
    l.value = l.value.trim().toLowerCase().replace(/[^a-z0-9._-]/g, "");
  });

  /* admin preview: add a teammate, check DNS. Nothing leaves the page. */
  const people = document.getElementById("lp-people");
  if(people){
    const form = document.getElementById("lp-add"), domain = document.getElementById("lp-domain"), count = document.getElementById("lp-count");
    const esc = s => s.replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
    const host = () => (domain.value.trim().toLowerCase().replace(/^https?:\/\//, "").replace(/^www\./, "").replace(/\/.*$/, "") || "yourcompany.com");
    const refresh = () => { $$(".who span", people).forEach(s => s.textContent = s.dataset.local + "@" + host()); count.textContent = people.children.length; };
    domain.addEventListener("input", refresh);
    form.addEventListener("submit", e => {
      e.preventDefault();
      const name = form.elements.name.value.trim().replace(/\s+/g, " ").slice(0, 40); if(!name) return form.elements.name.focus();
      const local = name.toLowerCase().split(" ")[0].replace(/[^a-z0-9]/g, "") || "teammate";
      const li = document.createElement("li");
      li.innerHTML = `<span class="av">${esc(name[0].toUpperCase())}</span><span class="who"><b>${esc(name)}</b><span data-local="${local}"></span></span><span class="lp-pill">Active</span>`;
      people.prepend(li); form.reset(); refresh();
      if(people.children.length > 5) people.lastElementChild.remove();
    });
    refresh();
    const dns = document.getElementById("lp-dns-check");
    dns.addEventListener("click", () => {
      dns.disabled = true; const rows = $$("#lp-dns li"), score = document.getElementById("lp-score");
      rows.forEach(r => { const p = r.querySelector(".lp-pill"); p.className = "lp-pill wait"; p.textContent = "Checking"; });
      score.textContent = "Checking " + host() + "…";
      rows.forEach((r, k) => setTimeout(() => {
        const p = r.querySelector(".lp-pill"); p.className = "lp-pill"; p.textContent = "Live";
        if(k === rows.length - 1){ score.textContent = rows.length + " of " + rows.length + " records live for " + host(); dns.disabled = false; }
      }, reduce ? 0 : 450 * (k + 1)));
    });
  }
})();
