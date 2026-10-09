/* Dejoiy Mail service worker: makes the app installable and opens the shell offline.
   Network first, so every deploy is picked up at once; mail data (/api) and the admin
   console are never cached. */
const CACHE = "dmail-shell-v1";
self.addEventListener("install", event => self.skipWaiting());
self.addEventListener("activate", event => event.waitUntil(
  caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/admin") || url.pathname.includes("admin-app") || url.pathname.endsWith("admin.css")) return;
  event.respondWith(fetch(event.request).then(response => {
    if (response.ok && response.type === "basic") { const copy = response.clone(); caches.open(CACHE).then(c => c.put(event.request, copy)); }
    return response;
  }).catch(() => caches.match(event.request).then(hit => hit || (event.request.mode === "navigate" ? caches.match("/") : Response.error()))));
});
