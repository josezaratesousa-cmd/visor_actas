/**
 * theme — light and dark mode.
 *
 * Order: stored choice → system preference. The system preference is
 * followed live only while the user has not chosen explicitly, so a
 * deliberate choice is never overridden by the OS switching at sunset.
 */

const STORAGE_KEY = 'onpe_theme';
const THEMES = ['light', 'dark'];

const META_COLOR = { light: '#D0202E', dark: '#0D1015' };

export function init() {
  const stored = safeGet(STORAGE_KEY);
  applyTheme(THEMES.includes(stored) ? stored : systemTheme());

  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', event => {
    if (!safeGet(STORAGE_KEY)) applyTheme(event.matches ? 'dark' : 'light');
  });
}

export function toggle() {
  const next = current() === 'dark' ? 'light' : 'dark';
  safeSet(STORAGE_KEY, next);
  applyTheme(next);
  return next;
}

export function current() {
  return document.documentElement.dataset.theme || 'light';
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', META_COLOR[theme]);
  document.dispatchEvent(new CustomEvent('themechange', { detail: { theme } }));
}

function systemTheme() {
  return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function safeGet(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function safeSet(key, value) {
  try { localStorage.setItem(key, value); } catch { /* private mode */ }
}
