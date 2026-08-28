/**
 * i18n — label dictionary loader.
 *
 * No user-facing string is ever hardcoded in a view. Views call t('key')
 * and the dictionary decides the wording. Adding a language means adding
 * one JSON file under i18n/, nothing else.
 *
 * Locale resolution order: ?lang= → stored choice → browser → default.
 */

const SUPPORTED = ['es', 'en'];
const STORAGE_KEY = 'onpe_locale';

let dictionary = {};
let locale = 'es';

export function resolveLocale(fallback = 'es') {
  const fromQuery = new URLSearchParams(location.search).get('lang');
  const stored = safeGet(STORAGE_KEY);
  const fromBrowser = (navigator.language || '').slice(0, 2);

  for (const candidate of [fromQuery, stored, fromBrowser, fallback]) {
    if (candidate && SUPPORTED.includes(candidate)) return candidate;
  }
  return fallback;
}

export async function load(requested) {
  locale = SUPPORTED.includes(requested) ? requested : 'es';
  const response = await fetch(`i18n/${locale}.json`, { cache: 'no-cache' });
  if (!response.ok) throw new Error(`Missing dictionary for locale "${locale}"`);
  dictionary = await response.json();
  document.documentElement.lang = locale;
  return locale;
}

export function setLocale(next) {
  if (!SUPPORTED.includes(next)) return;
  safeSet(STORAGE_KEY, next);
  const url = new URL(location.href);
  url.searchParams.set('lang', next);
  location.href = url.toString();
}

export function current() {
  return locale;
}

export function locales() {
  return SUPPORTED.slice();
}

/**
 * Look up a dotted key and interpolate {placeholders}.
 * A missing key returns the key itself: visible in the UI during
 * development, never a blank space in production.
 */
export function t(key, vars = {}) {
  const value = key.split('.').reduce((node, part) => (node ?? {})[part], dictionary);
  if (typeof value !== 'string') {
    if (Array.isArray(value)) return value;
    console.warn(`[i18n] missing key: ${key}`);
    return key;
  }
  return value.replace(/\{(\w+)\}/g, (match, name) =>
    Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : match
  );
}

/** Apply translations to every [data-i18n] node in a subtree. */
export function apply(root = document) {
  root.querySelectorAll('[data-i18n]').forEach(node => {
    node.textContent = t(node.dataset.i18n);
  });
  root.querySelectorAll('[data-i18n-label]').forEach(node => {
    node.setAttribute('aria-label', t(node.dataset.i18nLabel));
  });
}

function safeGet(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function safeSet(key, value) {
  try { localStorage.setItem(key, value); } catch { /* private mode */ }
}
