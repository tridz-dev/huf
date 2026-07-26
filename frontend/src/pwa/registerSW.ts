if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/huf/sw.js', { scope: '/huf/' }).catch((error) => {
      console.error('Failed to register Huf service worker', error);
    });
  });
}
