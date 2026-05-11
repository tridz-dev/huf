import { copyFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';

const frontendDir = resolve(import.meta.dirname, '..');
const source = resolve(frontendDir, '../huf/public/frontend/index.html');
const targets = [
  resolve(frontendDir, '../huf/www/huf.html'),
  resolve(frontendDir, '../huf/www/chat.html'),
];

await Promise.all(
  targets.map(async (target) => {
    await mkdir(dirname(target), { recursive: true });
    await copyFile(source, target);
  }),
);

console.log(`Copied frontend shell to ${targets.map((target) => target.replace(`${resolve(frontendDir, '..')}/`, '')).join(', ')}`);
