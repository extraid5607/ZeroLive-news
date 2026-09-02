const CACHE_NAME = 'zerolive-shell-v3';
const SHELL_ASSETS = [
  '/',
  '/about',
  '/manifest.json',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/preview.png'
];

// Install: Cache minimal app shell only (not live news data)
self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(SHELL_ASSETS);
    }).then(function() {
      return self.skipWaiting();
    })
  );
});

// Activate: Clean up older cache versions
self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(cacheNames) {
      return Promise.all(
        cacheNames.map(function(cacheName) {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    }).then(function() {
      return self.clients.claim();
    })
  );
});

// Fetch: Pass dynamic API requests straight to network; network-first for shell with offline cache fallback
self.addEventListener('fetch', function(event) {
  if (event.request.method !== 'GET') {
    return;
  }

  const url = new URL(event.request.url);

  // Bypass cache completely for constantly updating news and calendar APIs
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/docs') || url.pathname.startsWith('/openapi.json')) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then(function(networkResponse) {
        if (networkResponse && networkResponse.status === 200) {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then(function(cache) {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      })
      .catch(function() {
        return caches.match(event.request).then(function(cachedResponse) {
          if (cachedResponse) {
            return cachedResponse;
          }
          if (event.request.mode === 'navigate') {
            return caches.match('/');
          }
        });
      })
  );
});

self.addEventListener('push', function(event) {
  let data = {};
  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data = {
        title: 'ZeroLive – Breaking Market Alert',
        body: event.data.text(),
        url: '/?tab=important'
      };
    }
  }

  const title = data.title || 'ZeroLive – Breaking Market Alert';
  const targetUrl = data.url || '/?tab=important';

  const options = {
    body: data.body || 'Live market breaking news.',
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-192.png',
    tag: data.tag || 'zerolive-alert',
    renotify: false,
    requireInteraction: false,
    data: {
      url: targetUrl
    }
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();

  // Resolve target URL relative to our PWA origin
  const rawUrl = (event.notification.data && event.notification.data.url) || '/?tab=important';
  const targetUrl = new URL(rawUrl, self.location.origin).href;

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
      // 1. If an app window or installed PWA is already open, focus it and navigate to the news
      for (let i = 0; i < clientList.length; i++) {
        let client = clientList[i];
        if (client.url && client.url.startsWith(self.location.origin) && 'focus' in client) {
          if ('navigate' in client) {
            client.navigate(targetUrl);
          }
          return client.focus();
        }
      }
      // 2. If the app is closed, open the window in standalone PWA mode
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});
