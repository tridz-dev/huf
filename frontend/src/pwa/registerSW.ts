// The Huf web app ships no service worker (an offline cache kept serving old builds after a deploy).
// Registering /huf/sw.js 404'd on every load, so nothing registers it any more. Older builds did register
// one, and that worker could keep a stale shell alive in a returning browser: remove it and its caches once.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .getRegistrations()
      .then((registrations) => Promise.all(registrations.filter((r) => r.scope.includes('/huf/')).map((r) => r.unregister())))
      .catch(() => undefined);
    if ('caches' in window) {
      caches
        .keys()
        .then((keys) => Promise.all(keys.filter((k) => /workbox|huf/i.test(k)).map((k) => caches.delete(k))))
        .catch(() => undefined);
    }
  });
}
