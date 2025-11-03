import path from 'path';
import fs from 'fs';
import type { ProxyOptions } from 'vite';

interface CommonSiteConfig {
  webserver_port?: number;
  default_site?: string;
  [key: string]: any;
}

function getCommonSiteConfig(): CommonSiteConfig | null {
  let currentDir = path.resolve('.');
  while (currentDir !== '/') {
    if (
      fs.existsSync(path.join(currentDir, 'sites')) &&
      fs.existsSync(path.join(currentDir, 'apps'))
    ) {
      const configPath = path.join(currentDir, 'sites', 'common_site_config.json');
      if (fs.existsSync(configPath)) {
        return JSON.parse(fs.readFileSync(configPath, 'utf-8'));
      }
      return null;
    }
    currentDir = path.resolve(currentDir, '..');
  }
  return null;
}

function detectFirstSite(): string | null {
  let currentDir = path.resolve('.');
  while (currentDir !== '/') {
    const sitesDir = path.join(currentDir, 'sites');
    if (fs.existsSync(sitesDir)) {
      const siteFolders = fs
        .readdirSync(sitesDir)
        .filter((f) => fs.existsSync(path.join(sitesDir, f, 'site_config.json')));
      if (siteFolders.length > 0) {
        return siteFolders[0];
      }
    }
    currentDir = path.resolve(currentDir, '..');
  }
  return null;
}

const config = getCommonSiteConfig();
const webserver_port = config?.webserver_port || 8000;
const site_name =
  process.env.FRAPPE_SITE || config?.default_site || detectFirstSite() || 'localhost';

console.log(`webserver_port: ${webserver_port}, site_name: ${site_name}`);

const proxyOptions: Record<string, ProxyOptions> = {
  '^/(app|api|assets|files|private|login)(/.*)?': {
    target: `http://${site_name}:${webserver_port}`,
    changeOrigin: true,
    secure: false,
    ws: true,
    // router(req) {
    //   const reqSite = req.headers.host?.split(':')[0] || site_name;
    //   return `http://${reqSite}:${webserver_port}`;
    // },
  },
};

export default proxyOptions;
