import { copyFile, mkdir, readdir, unlink } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';

const frontendDir = resolve(import.meta.dirname, '..');
const repoDir = resolve(frontendDir, '..');
const source = resolve(frontendDir, '../huf/public/frontend/index.html');
const shellTarget = resolve(frontendDir, '../huf/www/huf.html');
const serviceWorkerSource = resolve(frontendDir, '../huf/public/frontend/sw.js');
const serviceWorkerTarget = resolve(frontendDir, '../huf/www/huf/sw.js');
const manifestSource = resolve(frontendDir, '../huf/public/frontend/manifest.webmanifest');
const manifestTarget = resolve(frontendDir, '../huf/www/huf/manifest.webmanifest');
const frontendOutDir = resolve(frontendDir, '../huf/public/frontend');
const serviceWorkerRouteDir = resolve(frontendDir, '../huf/www/huf');

await mkdir(dirname(shellTarget), { recursive: true });
await copyFile(source, shellTarget);

await mkdir(serviceWorkerRouteDir, { recursive: true });
await copyFile(serviceWorkerSource, serviceWorkerTarget);
await copyFile(manifestSource, manifestTarget);

const generatedFiles = await readdir(frontendOutDir);
const workboxFiles = generatedFiles.filter((file) => /^workbox-.+\.js$/.test(file));
const existingRouteFiles = await readdir(serviceWorkerRouteDir);

await Promise.all(
  existingRouteFiles
    .filter((file) => /^workbox-.+\.js$/.test(file))
    .map((file) => unlink(resolve(serviceWorkerRouteDir, file))),
);

await Promise.all(
  workboxFiles.map((file) =>
    copyFile(resolve(frontendOutDir, file), resolve(serviceWorkerRouteDir, file)),
  ),
);

const copiedPaths = [
  shellTarget,
  serviceWorkerTarget,
  manifestTarget,
  ...workboxFiles.map((file) => resolve(serviceWorkerRouteDir, file)),
];
console.log(`Copied frontend entry files to ${copiedPaths.map((target) => target.replace(`${repoDir}/`, '')).join(', ')}`);
