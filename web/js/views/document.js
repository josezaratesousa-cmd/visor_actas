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
      <button class="doc-btn" id="btn-download" data-url="${esc(doc.pdf_url)}"
              data-name="acta-${esc(record.station)}.pdf">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 3v12"/><path d="m7 11 5 5 5-5"/><path d="M4 20h16"/>
        </svg>${esc(t('document.download'))}
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
 * Descarga con progreso.
 *
 * En un telefono, tocar "Descargar" y que no pase nada visible durante unos
 * segundos se lee como que el boton no funciono, y la persona vuelve a
 * tocarlo. Mostrar el avance responde esa duda antes de que aparezca.
 *
 * Se usa fetch con lectura por trozos para poder contar bytes. Si algo de
 * eso falla -navegador viejo, respuesta sin Content-Length, memoria justa-
 * se cae a la descarga normal del navegador, que siempre funciona aunque no
 * se pueda medir.
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

  button.addEventListener('click', async () => {
    const url = button.dataset.url;
    const filename = button.dataset.name;

    button.closest('.doc-actions').hidden = true;
    panel.hidden = false;
    paint(0);

    try {
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
        // Sin Content-Length no hay porcentaje honesto que mostrar, asi que
        // el indicador avanza acercandose al final sin llegar nunca.
        paint(total ? received / total * 100 : Math.min(95, received / 51200 * 100));
      }

      paint(100);
      label.textContent = t('document.downloaded');

      const blob = new Blob(chunks, { type: 'application/pdf' });
      const href = URL.createObjectURL(blob);
      const link = Object.assign(document.createElement('a'), { href, download: filename });
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(href), 4000);
    } catch {
      // El navegador sabe descargar aunque nosotros no sepamos medirlo.
      label.textContent = t('document.download_direct');
      window.location.href = url;
    }

    setTimeout(() => {
      panel.hidden = true;
      button.closest('.doc-actions').hidden = false;
    }, 1600);
  });
}
