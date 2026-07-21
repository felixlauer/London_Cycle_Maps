/**
 * Dev launcher: `npm start [-- --day|--night] [-- --v2]`.
 *
 * CRA apps cannot read CLI flags in the browser, so this wrapper turns
 * --day / --night into REACT_APP_FORCE_MODE and --v2 into REACT_APP_UI_VERSION
 * before starting react-scripts.
 * Plain `npm start` behaves exactly as before (legacy UI, auto day/night).
 */
const { spawn } = require('child_process');

const args = process.argv.slice(2);
const env = { ...process.env };

const wantDay = args.includes('--day');
const wantNight = args.includes('--night');
const wantV2 = args.includes('--v2');

if (wantDay && wantNight) {
  console.error('Choose one of --day or --night, not both.');
  process.exit(1);
}
if (wantDay) env.REACT_APP_FORCE_MODE = 'day';
if (wantNight) env.REACT_APP_FORCE_MODE = 'night';
if (wantV2) env.REACT_APP_UI_VERSION = 'v2';

if (env.REACT_APP_FORCE_MODE) {
  console.log(`[start] FORCED ${env.REACT_APP_FORCE_MODE.toUpperCase()} MODE - sun position ignored`);
}
if (env.REACT_APP_UI_VERSION === 'v2') {
  console.log('[start] UI v2 rebuild shell (legacy App.js unchanged)');
}

const reactScripts = require.resolve('react-scripts/bin/react-scripts.js');
const child = spawn(process.execPath, [reactScripts, 'start'], {
  stdio: 'inherit',
  env,
});
child.on('exit', (code) => process.exit(code ?? 0));
