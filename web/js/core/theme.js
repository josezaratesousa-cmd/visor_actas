/**
 * theme — light and dark mode.
 *
 * Light is the default, always. The system preference is deliberately not
 * consulted: this is a public verifier whose screenshots get shared and
 * compared, and a citizen showing a neighbour "look, it says authentic"
 * should be showing the same screen. A deterministic default also matches
 * the printed tally sheet the reader is holding.
 *
 * Dark mode stays available, but only as an explicit choice, and once made
 * it survives reloads.
 */

const STORAGE_KEY = 'onpe_theme';
const THEMES = ['light', 'dark'];
const DEFAULT = 'light';

const META_COLOR = { light: '#D0202E', dark: '#0D1015' };

export function init() {
  const stored = safeGet(STORAGE_KEY);
  applyTheme(THEMES.includes(stored) ? stored : DEFAULT);
}

export function toggle() {
  const next = current() === 'dark' ? 'light' : 'dark';
  safeSet(STORAGE_KEY, next);
  applyTheme(next);
  return next;
}

export function current() {
  return document.documentElement.dataset.theme || DEFAULT;
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', META_COLOR[theme]);
  document.dispatchEvent(new CustomEvent('themechange', { detail: { theme } }));
}

function safeGet(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function safeSet(key, value) {
  try { localStorage.setItem(key, value); } catch { /* private mode */ }
}
