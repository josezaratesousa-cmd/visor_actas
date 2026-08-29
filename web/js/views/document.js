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
      <a class="doc-btn" href="${esc(doc.pdf_url)}" download>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 3v12"/><path d="m7 11 5 5 5-5"/><path d="M4 20h16"/>
        </svg>${esc(t('document.download'))}
      </a>
    </div>
    <p class="doc-note">${esc(t('document.meta', {
      pages: doc.page_count, size: doc.size
    }))}</p>`;
}
