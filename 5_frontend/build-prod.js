/**
 * Production CRA build: always v2 UI + same-origin /api (nginx strip).
 *
 * Usage: npm run build:prod
 * Reads REACT_APP_MAPBOX_TOKEN from the environment or 5_frontend/.env
 * (CRA also loads .env itself; we load it here so warnings are accurate).
 */
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

function loadEnvFile(filePath, target) {
  if (!fs.existsSync(filePath)) return;
  const text = fs.readFileSync(filePath, 'utf8');
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq <= 0) continue;
    const key = line.slice(0, eq).trim();
    let val = line.slice(eq + 1).trim();
    if (
      (val.startsWith('"') && val.endsWith('"')) ||
      (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1);
    }
    // Do not override vars already set in the shell.
    if (target[key] === undefined || target[key] === '') {
      target[key] = val;
    }
  }
}

const env = { ...process.env };
loadEnvFile(path.join(__dirname, '.env'), env);
loadEnvFile(path.join(__dirname, '.env.production'), env);

env.REACT_APP_UI_VERSION = 'v2';
env.REACT_APP_API_BASE = '/api';
// Never bake mobile LAN mode into a production bundle.
env.REACT_APP_MOBILE_DEBUG = '';

const token = (env.REACT_APP_MAPBOX_TOKEN || '').trim();
if (!token) {
  console.warn(
    '[build:prod] WARNING: REACT_APP_MAPBOX_TOKEN is empty — map will not load until rebuilt with a pk. token.'
  );
} else {
  console.log(
    `[build:prod] REACT_APP_MAPBOX_TOKEN present (pk.=${token.startsWith('pk.')}, len=${token.length})`
  );
}

console.log('[build:prod] REACT_APP_UI_VERSION=v2 REACT_APP_API_BASE=/api');

// Static Mapbox worker — avoids CRA production minification breaking tile workers.
const workerSrc = path.join(
  __dirname,
  'node_modules',
  'mapbox-gl',
  'dist',
  'mapbox-gl-csp-worker.js'
);
const workerDest = path.join(__dirname, 'public', 'mapbox-gl-csp-worker.js');
if (!fs.existsSync(workerSrc)) {
  console.error('[build:prod] Missing mapbox-gl CSP worker at', workerSrc);
  process.exit(1);
}
fs.copyFileSync(workerSrc, workerDest);
console.log('[build:prod] copied mapbox-gl-csp-worker.js → public/');

const reactScripts = require.resolve('react-scripts/bin/react-scripts.js');
const child = spawn(process.execPath, [reactScripts, 'build'], {
  stdio: 'inherit',
  env,
});
child.on('exit', (code) => process.exit(code ?? 0));
