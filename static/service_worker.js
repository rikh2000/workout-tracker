const CACHE_NAME = 'workout-tracker-v1';
const STATIC_ASSETS = ['/'];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
    );
});

self.addEventListener('fetch', event => {
    event.respondWith(
        fetch(event.request).catch(() =>
            caches.match(event.request)
        )
    );
});