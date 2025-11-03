import path from 'path';
import fs from 'fs';
import type { ProxyOptions } from 'vite';

interface CommonSiteConfig {
  webserver_port?: number;
  [key: string]: any;
}

function getCommonSiteConfig(): CommonSiteConfig | null {
  let currentDir = path.resolve('.')
  // traverse up till we find frappe-bench with sites directory
  while (currentDir !== '/') {
    if (
      fs.existsSync(path.join(currentDir, 'sites')) &&
      fs.existsSync(path.join(currentDir, 'apps'))
    ) {
      let configPath = path.join(currentDir, 'sites', 'common_site_config.json')
      if (fs.existsSync(configPath)) {
        return JSON.parse(fs.readFileSync(configPath, 'utf-8'))
      }
      return null
    }
    currentDir = path.resolve(currentDir, '..')
  }
  return null
}

const config = getCommonSiteConfig()
const webserver_port = config ? config.webserver_port : 8000
console.log(`webserver_port: ${webserver_port}`);
if (!config) {
  console.log('No common_site_config.json found, using default port 8000')
}

const proxyOptions: Record<string, ProxyOptions> = {
  '^/(app|api|assets|files|private|login)(/.*)?': {
    target: 'http://huf.localhost:8003', // Frappe webserver port
    changeOrigin: true,
    secure: false,
    ws: true,
    headers: {
      host: 'huf.localhost',          // 👈 must match your site folder name
      origin: 'http://huf.localhost:8003',
    },
    onError(err, req, res) {
      console.error(`[Proxy Error] ${req.url}:`, err.message);
    },
  },
};

export default proxyOptions;
