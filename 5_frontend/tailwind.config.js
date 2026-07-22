/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/v2/**/*.{js,jsx}', './src/index.js'],
  // Keep Mapbox + existing resets intact — do not inject Tailwind Preflight.
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        brand: '#ff0061',
        'shell-bg': 'var(--shell-bg)',
        'shell-border': 'var(--shell-border)',
      },
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        shell: 'var(--shell-shadow)',
      },
      borderRadius: {
        shell: 'var(--shell-radius)',
      },
      transitionTimingFunction: {
        'ease-out-strong': 'cubic-bezier(0.23, 1, 0.32, 1)',
        drawer: 'cubic-bezier(0.32, 0.72, 0, 1)',
      },
    },
  },
  plugins: [],
};
