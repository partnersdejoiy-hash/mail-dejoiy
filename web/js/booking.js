/* Dejoiy Mail public booking page (/book/<slug>). Times come from the server in UTC ms and are shown in the visitor's own zone. */
(() => {
  const root = document.getElementById('bk');
  const slug = location.pathname.split('/').filter(Boolean).pop() || '';
  const api = '/api/public/booking/' + encodeURIComponent(slug);
  const here = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const sameZone = tz => { try { const o = z => new Intl.DateTimeFormat('en', { timeZone: z, timeZoneName: 'longOffset' }).format(Date.now()).split(' ').pop(); return o(tz) === o(here); } catch { return true; } };
  const fmt = (ms, o) => new Intl.DateTimeFormat(undefined, o).format(new Date(ms));
  const time = ms => fmt(ms, { hour: 'numeric', minute: '2-digit' });
  const dayKey = ms => fmt(ms, { year: 'numeric', month: '2-digit', day: '2-digit' });
  const friendly = { 404: 'This booking link is not available. Ask for a new one.', 409: 'Someone just took that time. Pick another one.',
    429: 'Too many tries. Wait a minute and try again.', 503: 'Booking is not set up on this server yet.' };
  let info, byDay, day, pick;

  function msg(title, text) { root.innerHTML = `<div class="bk-msg"><h1>${esc(title)}</h1><p>${esc(text)}</p></div>`; }

  async function load() {
    try {
      const r = await fetch(api, { headers: { Accept: 'application/json' } });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) return msg('Hmm.', friendly[r.status] || d.error || 'Could not load free times. Try again.');
      info = d;
      // regroup by the visitor's own calendar day
      byDay = new Map();
      Object.values(d.slots || {}).flat().sort((a, b) => a - b).forEach(ms => {
        const k = dayKey(ms); if (!byDay.has(k)) byDay.set(k, []); byDay.get(k).push(ms);
      });
      day = byDay.keys().next().value; render();
    } catch { msg('No connection.', 'Check your internet and refresh the page.'); }
  }

  function render() {
    const name = info.name || 'Someone';
    document.title = `${info.title} · ${name}`;
    const days = [...byDay.entries()];
    root.innerHTML = `
      <aside class="bk-who">
        <div class="bk-avatar" aria-hidden="true">${esc(name.trim()[0] || 'D').toUpperCase()}</div>
        <small>${esc(name)}</small>
        <h1>${esc(info.title)}</h1>
        <ul class="bk-facts"><li>⏱ ${info.duration} minutes</li>${info.location ? `<li>📍 ${esc(info.location)}</li>` : ''}<li>✉️ Invite comes by email</li></ul>
        ${info.description ? `<p class="bk-desc">${esc(info.description)}</p>` : ''}
      </aside>
      <section class="bk-pick">
        ${days.length ? `<h2>Pick a day</h2>
        <div class="bk-days" role="group" aria-label="Days">${days.map(([k, l]) => `<button class="bk-day" data-day="${k}" aria-pressed="${k === day}">
          <small>${fmt(l[0], { weekday: 'short' })}</small><b>${fmt(l[0], { day: 'numeric' })}</b><small>${fmt(l[0], { month: 'short' })}</small></button>`).join('')}</div>
        <h2>${fmt(byDay.get(day)[0], { weekday: 'long', day: 'numeric', month: 'long' })}</h2>
        <div class="bk-times" role="group" aria-label="Times">${byDay.get(day).map(ms => `<button class="bk-time" data-ms="${ms}" aria-pressed="${ms === pick}">${time(ms)}</button>`).join('')}</div>
        <p class="bk-tz">Times are in your zone (${esc(here)}).${info.tz && !sameZone(info.tz) ? ` ${esc(name)} is in ${esc(info.tz)}.` : ''}</p>
        <form class="bk-form" ${pick ? '' : 'hidden'} novalidate>
          <h3>${pick ? `${fmt(pick, { weekday: 'short', day: 'numeric', month: 'short' })}, ${time(pick)} – ${time(pick + info.duration * 60000)}` : ''}</h3>
          <label>Your name<input name="name" autocomplete="name" required maxlength="100" /></label>
          <label>Your email<input name="email" type="email" autocomplete="email" inputmode="email" required maxlength="254" /></label>
          <label>Anything to share? (optional)<textarea name="note" rows="3" maxlength="1000"></textarea></label>
          <p class="bk-err" role="alert"></p>
          <button class="bk-go" type="submit">Book it</button>
        </form>` : `<div class="bk-empty">No free times in the next few days. Check back later or email ${esc(name)} directly.</div>`}
      </section>`;
  }

  root.addEventListener('click', e => {
    const d = e.target.closest('.bk-day'), t = e.target.closest('.bk-time');
    if (d) { day = d.dataset.day; pick = null; render(); }
    if (t) { pick = Number(t.dataset.ms); render(); root.querySelector('.bk-form input')?.focus({ preventScroll: true }); root.querySelector('.bk-form').scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
  });

  root.addEventListener('submit', async e => {
    e.preventDefault();
    const f = e.target, err = f.querySelector('.bk-err'), go = f.querySelector('.bk-go');
    const data = { name: f.name.value.trim(), email: f.email.value.trim(), note: f.note.value.trim(), start: pick };
    if (!data.name) return (err.textContent = 'Enter your name.', f.name.focus());
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email)) return (err.textContent = 'Enter a valid email address.', f.email.focus());
    err.textContent = ''; go.disabled = true; go.textContent = 'Booking…';
    try {
      const r = await fetch(api, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(data) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        err.textContent = friendly[r.status] || d.error || 'Could not book. Try again.';
        go.disabled = false; go.textContent = 'Book it';
        if (r.status === 409) setTimeout(load, 1200);
        return;
      }
      root.innerHTML = `<div class="bk-done"><div class="bk-tick" aria-hidden="true">✓</div><h1>You're booked</h1>
        <p><strong>${esc(d.title || info.title)}</strong> with ${esc(info.name || '')}</p>
        <p><strong>${fmt(d.start || pick, { weekday: 'long', day: 'numeric', month: 'long' })}, ${time(d.start || pick)} – ${time(d.end || pick + info.duration * 60000)}</strong></p>
        ${d.location || info.location ? `<p>📍 ${esc(d.location || info.location)}</p>` : ''}
        <p>An invite is on its way to ${esc(data.email)}. Accept it to add this to your calendar.</p></div>`;
    } catch { err.textContent = 'No connection. Try again.'; go.disabled = false; go.textContent = 'Book it'; }
  });

  load();
})();
