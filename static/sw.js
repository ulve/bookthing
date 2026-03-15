const CACHE = 'bookthing-v5';
const STATIC = ['/icon-nav.svg', '/icon-192.webp', '/icon-512.webp', '/apple-touch-icon.png'];

self.addEventListener('install', e => {
  // Pre-cache only images (rarely change); JS/CSS/HTML use network-first
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(STATIC)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // Always go to network for API and auth
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/auth/')) return;

  // Images: cache-first (they change rarely)
  if (/\.(webp|png|jpg|jpeg|gif|svg|ico)$/i.test(url.pathname)) {
    e.respondWith(
      caches.match(e.request).then(cached => cached || fetch(e.request).then(res => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return res;
      }))
    );
    return;
  }

  // JS, CSS, HTML: network-first so new deploys are picked up immediately
  e.respondWith(
    fetch(e.request)
      .then(res => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
