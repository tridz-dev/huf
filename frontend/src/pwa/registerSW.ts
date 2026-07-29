if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/huf/sw.js', { scope: '/huf/' }).catch((error) => {
      console.error('Failed to register Huf service worker', error);
    });
  });

  // Paired with workbox's skipWaiting/clientsClaim (see vite.config.ts): when
  // a new service worker takes control of this page, the JS/CSS the page
  // already loaded is from the OLD bundle and won't update on its own.
  // Reload once so the app picks up the new bundle automatically instead of
  // requiring the user to manually refresh (often twice) to see a new
  // deploy. `refreshing` guards against a reload loop if the controller
  // changes more than once in a session.
  let refreshing = false;
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (refreshing) return;
    refreshing = true;
    window.location.reload();
  });
}
