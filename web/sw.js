/* Dejoiy Mail service worker: makes the mail and admin apps installable and keeps them usable offline.
   Network first, so every deploy is picked up at once; mail data (/api) and the admin console are
   never cached. When the network is gone, pages fall back to the last copy, or to the offline page. */
const CACHE = "dmail-shell-v6";
const OFFLINE = "/offline.html";
self.addEventListener("install", event => event.waitUntil(
  caches.open(CACHE).then(c => c.add(new Request(OFFLINE, {cache: "reload"}))).then(() => self.skipWaiting())));
self.addEventListener("activate", event => event.waitUntil(
  caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url), navigate = event.request.mode === "navigate";
  if (event.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  const secret = url.pathname.startsWith("/admin") || url.pathname.includes("admin-app") || url.pathname.endsWith("admin.css");
  if (secret) {
    // The console is never stored; offline it shows the offline page instead of a browser error.
    if (navigate) event.respondWith(fetch(event.request).catch(() => caches.match(OFFLINE)));
    return;
  }
  // Pages skip the browser cache so a new deploy is never hidden behind an old copy.
  const fresh = navigate ? fetch(event.request, {cache: "no-cache"}) : fetch(event.request);
  event.respondWith(fresh.then(response => {
    if (response.ok && response.type === "basic") { const copy = response.clone(); caches.open(CACHE).then(c => c.put(event.request, copy)); }
    return response;
  }).catch(() => caches.match(event.request).then(hit => hit || (navigate ? caches.match("/").then(shell => shell || caches.match(OFFLINE)) : Response.error()))));
});
