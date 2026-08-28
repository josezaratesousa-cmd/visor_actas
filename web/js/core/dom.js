/** Small DOM helpers. Deliberately tiny: no framework, no build step. */

export const $ = (selector, root = document) => root.querySelector(selector);

/** Escape anything that came from the network before it meets innerHTML. */
export function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));
}

export function fmt(number, locale = 'es-PE', digits = 1) {
  return Number(number).toLocaleString(locale, {
    minimumFractionDigits: digits, maximumFractionDigits: digits
  });
}

/** Animate every [data-width] inside a subtree on the next frame. */
export function growBars(root) {
  root.querySelectorAll('[data-width]').forEach(bar => {
    requestAnimationFrame(() => { bar.style.width = `${bar.dataset.width}%`; });
  });
}
