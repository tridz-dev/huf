import { copyFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';

const frontendDir = resolve(import.meta.dirname, '..');
const repoDir = resolve(frontendDir, '..');
const source = resolve(frontendDir, '../huf/public/frontend/index.html');
const shellTarget = resolve(frontendDir, '../huf/www/huf.html');
const serviceWorkerSource = resolve(frontendDir, '../huf/public/frontend/sw.js');
const serviceWorkerTarget = resolve(frontendDir, '../huf/www/huf/sw.js');
const manifestSource = resolve(frontendDir, '../huf/public/frontend/manifest.json');
const manifestTarget = resolve(frontendDir, '../huf/www/huf/manifest.json');
const serviceWorkerRouteDir = resolve(frontendDir, '../huf/www/huf');

await mkdir(dirname(shellTarget), { recursive: true });
await copyFile(source, shellTarget);

await mkdir(serviceWorkerRouteDir, { recursive: true });
await copyFile(serviceWorkerSource, serviceWorkerTarget);
await copyFile(manifestSource, manifestTarget);

const copiedPaths = [shellTarget, serviceWorkerTarget, manifestTarget];
console.log(`Copied frontend entry files to ${copiedPaths.map((target) => target.replace(`${repoDir}/`, '')).join(', ')}`);
