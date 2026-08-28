/**
 * Sharing.
 *
 * The link is shared, never the file. A PDF forwarded loose through
 * WhatsApp carries no chain of trust: the person receiving it cannot verify
 * anything, and tampering with a file out of context is trivial. Sharing the
 * URL means every forward lands the reader on the verifier.
 *
 * navigator.share is a browser API, not a library. No third-party script and
 * no tracking cookies on a page of the State.
 */

import { esc } from '../core/dom.js';
import { t } from '../core/i18n.js';

export function link() { return location.href.split('#')[0]; }

function message(record) {
  return t('share.message', { table: record.station, process: record.process.name });
}

export async function share(record, openSheet) {
  const payload = { title: `${t('app.table')} ${record.station} — ONPE`,
                    text: message(record), url: link() };
  if (navigator.share) {
    try { await navigator.share(payload); return; }
    catch (error) { if (error?.name === 'AbortError') return; }
  }
  openSheet();
}

export function render(target, record) {
  const url = link();
  const text = message(record);
  const networks = [
    { name: 'WhatsApp', colour: '#25D366',
      url: `https://wa.me/?text=${encodeURIComponent(`${text} ${url}`)}`,
      path: '<path d="M20.5 3.5A10.4 10.4 0 0 0 3.6 16L2.5 21.5l5.7-1.1A10.4 10.4 0 1 0 20.5 3.5Z" fill="currentColor" stroke="none"/>' },
    { name: 'Facebook', colour: '#1877F2',
      url: `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(url)}`,
      path: '<path d="M14 9V7c0-1 .3-1.5 1.5-1.5H17V2.5h-2.5C11.8 2.5 11 4 11 6.3V9H8.5v3H11v9.5h3V12h2.3l.4-3H14Z" fill="currentColor" stroke="none"/>' },
    { name: 'X', colour: '#14171C',
      url: `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}`,
      path: '<path d="M3 3h4.2l5 6.6L17.6 3H21l-7 8.2L21.4 21h-4.2l-5.3-7-6 7H2.6l7.5-8.7L3 3Z" fill="currentColor" stroke="none"/>' },
    { name: 'Telegram', colour: '#229ED9',
      url: `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`,
      path: '<path d="M21.5 3.5 2.8 10.6c-1 .4-1 1.7 0 2l4.6 1.4 1.8 5.4c.3.8 1.3 1 1.8.3l2.5-2.8 4.7 3.5c.7.5 1.7.1 1.9-.7l3-14.6c.2-1-.7-1.8-1.6-1.6Z" fill="currentColor" stroke="none"/>' }
  ];

  target.innerHTML = `
    <p class="share-note">${esc(t('share.note'))}</p>
    <div class="networks">${networks.map(net => `
      <a class="net" href="${esc(net.url)}" target="_blank" rel="noopener">
        <span class="net__icon" style="background:${net.colour}">
          <svg viewBox="0 0 24 24">${net.path}</svg>
        </span>${esc(net.name)}
      </a>`).join('')}
    </div>
    <button class="copy" id="copy-link">
      <span class="copy__url">${esc(url)}</span>
      <span class="copy__label" id="copy-label">${esc(t('share.copy'))}</span>
    </button>`;

  target.querySelector('#copy-link').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(url); } catch { /* insecure context */ }
    const label = target.querySelector('#copy-label');
    label.textContent = t('share.copied');
    setTimeout(() => { label.textContent = t('share.copy'); }, 1800);
  });
}
