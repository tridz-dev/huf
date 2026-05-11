/// <reference types="vite-plugin-pwa/client" />

import { registerSW } from 'virtual:pwa-register';

registerSW({
  immediate: true,
});
