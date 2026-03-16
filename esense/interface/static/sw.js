const CACHE = "esense-v1";
const STATIC = ["/", "/static/app.js", "/static/style.css", "/static/favicon.svg"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const { request } = e;
  const url = new URL(request.url);

  // Don't intercept WebSocket or API/ANP calls — these need the node to be active
  if (url.pathname.includes("/ws") || url.pathname.includes("/api/") || url.pathname.includes("/anp/")) {
    return;
  }

  if (request.mode === "navigate") {
    // Navigation requests: network-first, fallback to offline.html
    e.respondWith(
      fetch(request).catch(() => {
        return caches.match("/static/offline.html").then(cached => {
          return cached || caches.match("/");
        });
      })
    );
    return;
  }

  // Static assets: cache-first strategy
  e.respondWith(
    caches.match(request).then(cached => {
      return cached || fetch(request).then(response => {
        // Only cache successful responses
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE).then(c => c.put(request, clone));
        }
        return response;
      });
    }).catch(() => {
      // If offline and not in cache, try root
      return caches.match("/");
    })
  );
});
