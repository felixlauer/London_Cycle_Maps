/**
 * Dev launcher: `npm start [-- --day|--night] [-- --v2] [-- --mobile]`.
 *
 * CRA apps cannot read CLI flags in the browser, so this wrapper turns
 * --day / --night into REACT_APP_FORCE_MODE and --v2 into REACT_APP_UI_VERSION
 * before starting react-scripts.
 * --mobile binds the dev server to 0.0.0.0 and sets REACT_APP_MOBILE_DEBUG so
 * the API client uses window.location.hostname (LAN IP) instead of 127.0.0.1.
 * Plain `npm start` behaves exactly as before (legacy UI, auto day/night).
 */
const { spawn } = require('child_process');

const args = process.argv.slice(2);
const env = { ...process.env };

const wantDay = args.includes('--day');
const wantNight = args.includes('--night');
const wantV2 = args.includes('--v2');
const wantMobile = args.includes('--mobile');

if (wantDay && wantNight) {
  console.error('Choose one of --day or --night, not both.');
  process.exit(1);
}
if (wantDay) env.REACT_APP_FORCE_MODE = 'day';
if (wantNight) env.REACT_APP_FORCE_MODE = 'night';
if (wantV2) env.REACT_APP_UI_VERSION = 'v2';
if (wantMobile) {
  env.HOST = '0.0.0.0';
  env.DANGEROUSLY_DISABLE_HOST_CHECK = 'true';
  env.REACT_APP_MOBILE_DEBUG = '1';
}

if (env.REACT_APP_FORCE_MODE) {
  console.log(`[start] FORCED ${env.REACT_APP_FORCE_MODE.toUpperCase()} MODE - sun position ignored`);
}
if (env.REACT_APP_UI_VERSION === 'v2') {
  console.log('[start] UI v2 rebuild shell (legacy App.js unchanged)');
}
if (wantMobile) {
  console.log('[start] MOBILE DEBUG: listening on 0.0.0.0 — open http://<PC_LAN_IP>:3000 on your phone');
}

const reactScripts = require.resolve('react-scripts/bin/react-scripts.js');
const child = spawn(process.execPath, [reactScripts, 'start'], {
  stdio: 'inherit',
  env,
});
child.on('exit', (code) => process.exit(code ?? 0));
