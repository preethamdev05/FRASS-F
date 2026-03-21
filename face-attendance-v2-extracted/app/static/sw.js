const CACHE_NAME = 'faceattend-v2';
const STATIC_ASSETS = [
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/js/realtime.js',
];

self.addEventListener('install', (e) => {
    e.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
    );
    self.skipWaiting();
});

self.addEventListener('activate', (e) => {
    e.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', (e) => {
    const url = new URL(e.request.url);

    // Network-first for API calls
    if (url.pathname.startsWith('/api/')) {
        e.respondWith(
            fetch(e.request).catch(() => new Response(JSON.stringify({ error: 'Offline' }), {
                headers: { 'Content-Type': 'application/json' }, status: 503
            }))
        );
        return;
    }

    // Cache-first for static assets
    if (url.pathname.startsWith('/static/')) {
        e.respondWith(
            caches.match(e.request).then(cached => cached || fetch(e.request))
        );
        return;
    }

    // Network-first for HTML pages
    e.respondWith(
        fetch(e.request).catch(() => caches.match(e.request))
    );
});
