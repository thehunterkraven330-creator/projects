import type { Config } from 'tailwindcss';

const config: Config = {
  // Dark mode is a class on <html> (set by lib/theme.ts before first paint), not the OS setting directly,
  // so the person can choose Light / Dark / Match my device.
  darkMode: 'class',
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: 'rgb(var(--c-surface) / <alpha-value>)',
        ink: '#0B0B0F',
        'ink-2': '#1c1a22',
        panel: 'rgb(var(--c-panel) / <alpha-value>)',
        box: 'rgb(var(--c-box) / <alpha-value>)',
        line: 'rgb(var(--c-line) / <alpha-value>)',
        text: 'rgb(var(--c-text) / <alpha-value>)',
        'text-mute': 'rgb(var(--c-mute) / <alpha-value>)',
        price: 'rgb(var(--c-price) / <alpha-value>)',
        sale: 'rgb(var(--c-sale) / <alpha-value>)',
        // ---- Volt palette (to go back to coral: see COLOURS.md) ----
        accent: 'rgb(var(--c-accent) / <alpha-value>)', // fills: lime
        'on-accent': 'rgb(var(--c-on-accent) / <alpha-value>)', // text and icons on a lime fill
        accent2: 'rgb(var(--c-accent2) / <alpha-value>)', // partner colour: violet
        mark: 'rgb(var(--c-mark) / <alpha-value>)', // thin lines and selected rings: ink on light, lime on dark
        danger: 'rgb(var(--c-danger) / <alpha-value>)', // errors and destructive actions
        'accent-ink': 'rgb(var(--c-accent-ink) / <alpha-value>)', // small accent text: ink on light, lime on dark
        violet: '#7C3AED',
      },
      borderRadius: {
        xl2: '14px',
      },
    },
  },
  plugins: [],
};

export default config;
