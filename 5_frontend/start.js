/**
 * Dev launcher: `npm start [-- --day|--night]`.
 *
 * CRA apps cannot read CLI flags in the browser, so this wrapper turns
 * --day / --night into REACT_APP_FORCE_MODE before starting react-scripts.
 * App.js reads that env var and skips the sunrise/sunset auto-detection.
 * Plain `npm start` behaves exactly as before (auto day/night).
 */
const { spawn } = require('child_process');

const args = process.argv.slice(2);
const env = { ...process.env };

const wantDay = args.includes('--day');
const wantNight = args.includes('--night');

if (wantDay && wantNight) {
  console.error('Choose one of --day or --night, not both.');
  process.exit(1);
}
if (wantDay) env.REACT_APP_FORCE_MODE = 'day';
if (wantNight) env.REACT_APP_FORCE_MODE = 'night';

if (env.REACT_APP_FORCE_MODE) {
  console.log(`[start] FORCED ${env.REACT_APP_FORCE_MODE.toUpperCase()} MODE - sun position ignored`);
}

const reactScripts = require.resolve('react-scripts/bin/react-scripts.js');
const child = spawn(process.execPath, [reactScripts, 'start'], {
  stdio: 'inherit',
  env,
});
child.on('exit', (code) => process.exit(code ?? 0));
