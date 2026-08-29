/** Small DOM helpers. Deliberately tiny: no framework, no build step. */

export const $ = (selector, root = document) => root.querySelector(selector);

/** Escape anything that came from the network before it meets innerHTML. */
export function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));
}

/**
 * Escapa una URL que viene de datos, no de nuestro codigo.
 *
 * esc() no basta para un href. Escapa comillas, asi que nadie puede salirse
 * del atributo, pero `javascript:alert(1)` no lleva ninguna comilla y sigue
 * ejecutandose al hacer clic. Solo http y https pasan; cualquier otro esquema
 * se descarta y el enlace queda inerte en vez de peligroso.
 */
export function safeUrl(value) {
  const raw = String(value ?? '').trim();
  try {
    const url = new URL(raw, location.origin);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return '';
    return esc(url.href);
  } catch {
    return '';
  }
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
