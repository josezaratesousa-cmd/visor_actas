/**
 * The tally sheet itself.
 *
 * Pages arrive as images rendered on the server, not as an embedded PDF.
 * No PDF viewer works reliably across phones: iOS Safari renders only the
 * first page inside an iframe, Android Chrome downloads instead of showing,
 * and PDF.js is over a megabyte before it draws anything. An image loads on
 * every device, needs no JavaScript, and survives a rural connection. The
 * signed PDF stays one tap away for whoever actually needs the file.
 */

import { esc } from '../core/dom.js';
import { t } from '../core/i18n.js';

/**
 * iOS no tiene "descargas" como el escritorio: Safari previsualiza el PDF
 * aunque el servidor mande attachment y aunque el tipo sea octet-stream,
 * porque mira la extension del nombre. Lo que si guarda es la hoja de
 * compartir del sistema, con "Guardar en Archivos" a un toque.
 *
 * Por eso el boton cambia de nombre y de icono segun la plataforma: debe
 * decir lo que realmente va a pasar al tocarlo, no lo que se llama en otro
 * sistema operativo.
 */
const IS_IOS = (() => {
  const ua = navigator.userAgent;

  // Un sistema que no es de Apple nunca toma el camino de iOS, pase lo que
  // pase con el resto del user agent. Extensiones y modos de compatibilidad
  // lo reescriben, y una cadena alterada estaba mandando un portatil Windows
  // a la hoja de compartir. Aqui la exclusion manda sobre la deteccion.
  if (/Windows|Android|CrOS|X11|Linux/.test(ua)) return false;

  if (/iPad|iPhone|iPod/.test(ua)) return true;

  // Un iPad en Safari se presenta como "Macintosh". Distinguirlo de un Mac
  // necesita las dos condiciones juntas: un Mac reporta puntos tactiles por
  // el trackpad pero nunca expone ontouchstart.
  return /Macintosh|Mac OS X/.test(ua)
    && navigator.maxTouchPoints > 1
    && 'ontouchstart' in window;
})();

export function render(target, record) {
  const doc = record.document;
  const pages = doc.pages.map((src, index) =>
    `<img class="page" src="${esc(src)}" srcset="${esc(src)} 1x, ${esc(src)}?density=%402x 2x" alt="${esc(t('document.page_of', {
      current: index + 1, total: doc.page_count
    }))}" loading="${index ? 'lazy' : 'eager'}">`
  ).join('');

  const dots = doc.page_count > 1
    ? `<div class="dots">${Array.from({ length: doc.page_count }, (_, i) =>
        `<span class="dot${i === 0 ? ' dot--on' : ''}"></span>`).join('')}</div>`
    : '';

  target.innerHTML = `
    ${pages}${dots}
    <div class="doc-actions">
      <a class="doc-btn" href="${esc(doc.pdf_url)}" target="_blank" rel="noopener">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 3h7v7"/><path d="M10 14 21 3"/>
          <path d="M19 14v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h6"/>
        </svg>${esc(t('document.open'))}
      </a>
      <button class="doc-btn" id="btn-download"
              data-url="${esc(doc.download_url || doc.pdf_url)}"
              data-name="${esc(doc.filename || 'acta.pdf')}">
        ${IS_IOS ? `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 3v11"/><path d="m8 6.6 4-3.6 4 3.6"/>
          <path d="M5 13v6a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-6"/>
        </svg>` : `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 3v12"/><path d="m7 11 5 5 5-5"/><path d="M4 20h16"/>
        </svg>`}${esc(t('document.download'))}
      </button>
    </div>

    <!-- Ocupa el sitio de los botones mientras baja, en vez de aparecer
         encima: en un telefono, algo que se superpone tapa justo lo que la
         persona esta mirando. -->
    <div class="dl" id="dl" hidden>
      <span class="dl__end" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7Z"/><path d="M14 3v4h4"/>
        </svg>
      </span>
      <span class="dl__track" id="dl-track" aria-hidden="true"></span>
      <span class="dl__end dl__end--phone" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
          <rect x="6" y="2.5" width="12" height="19" rx="2.4"/><path d="M10.6 18.6h2.8"/>
        </svg>
      </span>
      <span class="dl__label" id="dl-label"></span>
    </div>
    <p class="doc-note">${esc(t('document.meta', {
      pages: doc.page_count, size: doc.size
    }))}</p>`;
}


const DOTS = 9;

/**
 * iOS no tiene "descargas" como el escritorio.
 *
 * Safari previsualiza el PDF aunque el servidor mande attachment y aunque el
 * tipo sea octet-stream: mira la extension del nombre. El resultado es que la
 * persona ve el documento, lo cierra, y no tiene ningun archivo.
 *
 * El camino que sí guarda es la hoja de compartir del sistema, donde aparece
 * "Guardar en Archivos". Se llega con navigator.share pasando el archivo, que
 * en iOS 15+ funciona y es el gesto que la persona ya conoce.
 */
export function wireDownload(root) {
  const button = root.querySelector('#btn-download');
  const panel = root.querySelector('#dl');
  const track = root.querySelector('#dl-track');
  const label = root.querySelector('#dl-label');
  if (!button || !panel) return;

  track.innerHTML = Array.from({ length: DOTS },
    () => '<span class="dl__dot"></span>').join('');
  const dots = [...track.children];

  const paint = pct => {
    const filled = Math.round(pct / 100 * DOTS);
    dots.forEach((dot, index) => { dot.dataset.on = index < filled ? '1' : '0'; });
    label.textContent = `${t('document.downloading')} ${Math.round(pct)}%`;
  };

  const show = () => { button.closest('.doc-actions').hidden = true; panel.hidden = false; };
  const hide = () => { panel.hidden = true; button.closest('.doc-actions').hidden = false; };

  // Safari restaura la pagina desde su cache al volver atras, con el
  // temporizador a medio camino: sin esto, el indicador reaparece unos
  // segundos como si algo siguiera pasando.
  window.addEventListener('pageshow', hide);

  /** Lee el cuerpo contando bytes, para poder mostrar el avance real. */
  async function fetchWithProgress(url) {
    const response = await fetch(url);
    if (!response.ok || !response.body) throw new Error('sin cuerpo');
    const total = Number(response.headers.get('content-length')) || 0;
    const reader = response.body.getReader();
    const chunks = [];
    let received = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      received += value.length;
      // Sin Content-Length no hay porcentaje honesto: el indicador se acerca
      // al final sin llegar nunca.
      paint(total ? received / total * 100 : Math.min(95, received / 51200 * 100));
    }
    paint(100);
    return new Blob(chunks, { type: 'application/pdf' });
  }

  button.addEventListener('click', async () => {
    const url = button.dataset.url;
    const filename = button.dataset.name;

    // Una linea al pulsar, no en cada carga: el camino de descarga depende
    // del navegador y del sistema, y cuando falla en el telefono de alguien
    // esto es lo unico que dice por que. Sin datos del acta, solo del equipo.
    console.info('[descarga]', {
      ruta: IS_IOS ? 'compartir (iOS)' : 'descarga directa',
      esIOS: IS_IOS,
      puntosTactiles: navigator.maxTouchPoints,
      eventosTactiles: 'ontouchstart' in window,
      soportaDownload: 'download' in document.createElement('a'),
      soportaCompartirArchivos: !!(navigator.canShare),
    });
    // Aparte del objeto: la consola colapsa las cadenas largas dentro de uno,
    // y el user agent completo es justo lo que hace falta cuando la deteccion
    // se equivoca.
    console.info('[descarga] agente:', navigator.userAgent);

    show();
    paint(0);

    try {
      const blob = await fetchWithProgress(url);
      const file = new File([blob], filename, { type: 'application/pdf' });

      // Compartir es el camino de excepcion, no el preferido. Solo se toma
      // cuando el sistema realmente no sabe descargar: en cualquier otro
      // caso el navegador guarda el archivo sin intermediarios, que es lo
      // que la persona espera al tocar "Descargar".
      const canDownload = 'download' in document.createElement('a') && !IS_IOS;

      if (!canDownload && navigator.canShare && navigator.canShare({ files: [file] })) {
        console.info('[descarga] usando la hoja de compartir');
        label.textContent = t('document.save_prompt');
        await navigator.share({ files: [file] });   // "Guardar en Archivos"
        hide();
        return;
      }

      console.info('[descarga] guardando el archivo directamente');
      label.textContent = t('document.downloaded');
      const href = URL.createObjectURL(blob);
      const link = Object.assign(document.createElement('a'), { href, download: filename });
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(href), 4000);
    } catch (error) {
      if (error && error.name === 'AbortError') { hide(); return; }  // cancelo
      // Ultimo recurso: que lo abra el navegador. No siempre guarda, pero
      // deja el documento a la vista y la persona puede compartirlo desde ahi.
      console.warn('[descarga] fallo el camino previsto, abriendo en pestaña:', error);
      label.textContent = t('document.download_direct');
      window.open(url, '_blank', 'noopener');
    }

    setTimeout(hide, 1400);
  });
}
