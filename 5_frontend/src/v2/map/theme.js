/** Map + shell theme tokens. Will sync with day/night logic when ported from legacy App.js */

export const LIGHT_THEME = {
  mode: 'light',
  bg: '#FFFFFF',
  textMain: '#1a1a1a',
  textSub: '#666666',
  border: '#e5e7eb',
  toggleInactive: '#f0f0f0',
  routeGrey: '#555555',
  routeOptimized: '#FF0061',
  routeOptimizedCasing: '#ffffff',
  routeFastestCore: '#d4d4d8',
  routeFastestCasing: '#52525b',
  routeWalkCore: '#a1a1aa',
  litColor: '#FDE74C',
  steepColor: '#8717BF',
  tflCyclewayColor: '#4D9DE0',
  greenColor: '#3BB273',
  vehicularFreeColor: '#4D9DE0',
  nodeBarrier: '#5D4037',
  nodeSignal: '#F57C00',
  nodeJunction: '#795548',
  nodeCalming: '#00838F',
  disruptionColor: '#F18805',
};

export const DARK_THEME = {
  mode: 'dark',
  bg: '#141414',
  textMain: '#f0f0f0',
  textSub: '#a0a0a0',
  border: '#333333',
  toggleInactive: '#333333',
  routeGrey: '#ffffff',
  routeOptimized: '#FF0061',
  routeOptimizedCasing: '#ffffff',
  routeFastestCore: '#e4e4e7',
  routeFastestCasing: '#71717a',
  routeWalkCore: '#a1a1aa',
  litColor: '#FDE74C',
  steepColor: '#8717BF',
  tflCyclewayColor: '#4D9DE0',
  greenColor: '#3BB273',
  vehicularFreeColor: '#4D9DE0',
  nodeBarrier: '#5D4037',
  nodeSignal: '#F57C00',
  nodeJunction: '#795548',
  nodeCalming: '#00838F',
  disruptionColor: '#F18805',
};

export function themeForMode(mode) {
  return mode === 'dark' ? DARK_THEME : LIGHT_THEME;
}
