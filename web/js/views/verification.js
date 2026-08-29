/**
 * Verification sheet.
 *
 * Two independent claims, shown separately on purpose:
 *   integrity — the file matches the hash sealed in blockchain
 *   signature — the PAdES signature is valid and covers the whole document
 * They can fail apart. Collapsing them into one green tick would leave no
 * way to explain which one broke, to a citizen or in a challenge.
 *
 * The sequence takes a couple of seconds deliberately. An instant verdict
 * reads as decoration; the wait is part of the message. Once it has run, the
 * result stays in memory until the page is reloaded.
 */

import { esc, growBars } from '../core/dom.js';
import { t } from '../core/i18n.js';

const TICK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 5 5L19 8"/></svg>';
const PEN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 18c3.5-1 4.5-11 7-11s1.5 9 4 9c1.5 0 2-2 3.5-2"/><path d="M4 21h16"/></svg>';

const STEPS = ['verify.step_hash', 'verify.step_record', 'verify.step_compare', 'verify.step_signature'];

export function renderSteps(target) {
  target.innerHTML = `
    <div class="steps">${STEPS.map((key, index) => `
      <div class="step" data-state="" data-step="${index}">
        <span class="step__mark">${TICK}</span>
        <span class="step__text">${esc(t(key))}<small data-detail></small></span>
      </div>`).join('')}
    </div>
    <div class="verdict" id="verdict" hidden></div>`;
}

export async function run(target, record, { instant = false } = {}) {
  const steps = [...target.querySelectorAll('.step')];
  const pace = instant ? 0 : 1;
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms * pace));

  steps[0].dataset.state = 'busy';
  await wait(850);
  steps[0].querySelector('[data-detail]').textContent =
    `${record.attestation.evidence.slice(0, 30)}…`;
  steps[0].dataset.state = 'done'; steps[1].dataset.state = 'busy';
  await wait(900);
  steps[1].dataset.state = 'done'; steps[2].dataset.state = 'busy';
  await wait(700);
  steps[2].dataset.state = 'done'; steps[3].dataset.state = 'busy';
  await wait(900);
  steps[3].querySelector('[data-detail]').textContent =
    record.signature.status === 'unsigned' ? t('verify.axis_signature_none') : `${record.signature.profile} · ${record.signature.signers.length}`;
  steps[3].dataset.state = 'done';

  // Primero se van los pasos, despues llega el veredicto. Verlos juntos y
  // que uno desaparezca delante del otro se lee como un fallo de la pagina;
  // encadenados, se lee como una sola secuencia que termina.
  const stepList = target.querySelector('.steps');
  if (stepList) {
    await wait(450);                    // lo justo para ver marcarse el ultimo
    stepList.dataset.done = '1';
    await wait(420);                    // que termine de replegarse
  }

  renderVerdict(target.querySelector('#verdict'), record);
}

function renderVerdict(node, record) {
  // Three states, not two. "unsigned" is a legitimate outcome: the sheet is
  // intact but carries no electronic signature. Folding it into "valid" would
  // invent the one thing this product exists to prove; folding it into
  // "invalid" would accuse a document that is fine.
  const state = record.signature.status
    || (record.signature.valid ? 'valid' : 'invalid');
  const ok = state === 'valid';
  const unsigned = state === 'unsigned';
  const a = record.attestation;

  node.innerHTML = `
    <div class="seal" data-bad="${state === 'invalid' ? 1 : 0}">
      <svg class="seal__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 2.5 4 6v6c0 4.6 3.2 8.4 8 9.5 4.8-1.1 8-4.9 8-9.5V6l-8-3.5Z"/><path d="m9 12 2 2 4-4"/>
      </svg>
      <div>
        <div class="seal__title">${esc(t(
          ok ? 'verify.verdict_ok'
             : unsigned ? 'verify.verdict_unsigned' : 'verify.verdict_warning'))}</div>
        <div class="seal__detail">${esc(t(
          ok ? 'verify.verdict_ok_detail'
             : unsigned ? 'verify.verdict_unsigned_detail' : 'verify.verdict_warning_detail'))}</div>
      </div>
    </div>

    <div class="axes">
      <div class="axis">
        <span class="axis__dot"></span>
        <span><b>${esc(t('verify.axis_integrity'))}</b>
          <span>${esc(t('verify.axis_integrity_detail'))}</span></span>
      </div>
      <div class="axis" data-bad="${state === 'invalid' ? 1 : 0}"
           data-neutral="${unsigned ? 1 : 0}">
        <span class="axis__dot"></span>
        <span><b>${esc(t(
            ok ? 'verify.axis_signature'
               : unsigned ? 'verify.axis_signature_none' : 'verify.axis_signature_bad'))}</b>
          <span>${esc(
            ok ? t('verify.axis_signature_detail', { count: record.signature.signers.length })
               : unsigned ? t('verify.axis_signature_none_detail')
               : t('verify.axis_signature_bad_detail'))}</span></span>
      </div>
    </div>

    <div class="rubric">${esc(t('verify.fingerprint'))}</div>
    <div class="print" id="print" role="img"
         aria-label="${esc(t('verify.fingerprint'))}"></div>
    <div class="print__hex">${esc(a.evidence)}</div>

    <div class="rubric">${esc(t(
      ok ? 'verify.signers' : unsigned ? 'verify.signers_none' : 'verify.signers_bad'))}</div>
    ${unsigned ? `<p class="provenance">${esc(t('verify.no_signature'))}</p>` : ''}
    ${record.signature.signers.map(signer => `
      <div class="anchor">
        <div class="anchor__badge" style="background:var(--green-faint);color:var(--green)">${PEN}</div>
        <div>
          <div class="anchor__name">${esc(signer.name)}
            <span class="anchor__net">${esc(signer.role)}</span></div>
          <div class="print__hex">${esc(signer.id)} · ${esc(signer.signed_at)}</div>
          <div class="opt__foot">${esc(t('verify.issued_by'))}
            <b>${esc(signer.authority)}</b> — ${esc(signer.authority_kind)}</div>
        </div>
      </div>`).join('')}

    <div class="rubric">${esc(t('verify.registered_in'))}</div>
    ${a.anchors.map(anchor => `
      <div class="anchor${anchor.is_root ? ' anchor--root' : ''}">
        <div class="anchor__badge">${anchor.logo
          ? `<img src="${esc(anchor.logo)}" alt="" loading="lazy"
                  data-fallback="${esc(anchor.key)}">`
          : esc(anchor.key)}</div>
        <div>
          <div class="anchor__name">${esc(t(anchor.label_key))}
            <span class="anchor__net">${esc(anchor.network)}</span></div>
          <a class="anchor__hash" href="${esc(anchor.url)}" target="_blank" rel="noopener">${esc(anchor.value)}</a>
          ${anchor.action_key ? `<a class="anchor__go" href="${esc(anchor.url)}" target="_blank" rel="noopener">
            ${esc(t(anchor.action_key))}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h13"/><path d="m12 5 7 7-7 7"/></svg></a>` : ''}
        </div>
      </div>`).join('')}

    <div class="rubric">${esc(t('verify.timestamp'))}</div>
    <div class="pair"><span class="pair__k">${esc(t('verify.sealed'))}</span>
      <span class="pair__v mono">${esc(a.sealed_at)}</span></div>
    <div class="pair"><span class="pair__k">${esc(t('verify.anchored'))}</span>
      <span class="pair__v mono">${esc(a.anchored_at)}</span></div>
    <div class="pair"><span class="pair__k">TrxID</span>
      <span class="pair__v mono">${esc(a.trx_id)}</span></div>

    ${renderPlace(record.location)}`;

  node.hidden = false;

  // Respaldo del logo sin atributos onerror: un manejador en linea obliga a
  // abrir la CSP con 'unsafe-inline', que es justo lo que la vuelve inutil
  // contra la inyeccion de scripts.
  node.querySelectorAll('img[data-fallback]').forEach(img => {
    img.addEventListener('error', () => {
      img.replaceWith(document.createTextNode(img.dataset.fallback));
    }, { once: true });
  });

  paintFingerprint(node.querySelector('#print'), a.evidence);
  growBars(node);
}

/** The hash as 64 bars: two sheets are comparable at a glance. */
function paintFingerprint(node, hash) {
  node.innerHTML = '';
  [...hash].forEach((char, index) => {
    const value = parseInt(char, 16);
    const bar = document.createElement('span');
    bar.className = 'print__bar';
    bar.style.height = '0';
    bar.style.opacity = (0.3 + (value / 15) * 0.7).toFixed(2);
    node.appendChild(bar);
    setTimeout(() => { bar.style.height = `${18 + (value / 15) * 82}%`; }, index * 7);
  });
}

/**
 * Location. No map: a ubigeo identifies a district, not a school, so a pin
 * on a district centroid would tell the citizen something false about where
 * they voted. Coordinates present means the phone's own map app can open it.
 */
function renderPlace(place) {
  if (!place) return '';
  const zone = [place.district, place.province].filter(Boolean).join(', ');
  if (!place.venue && !zone && !place.ubigeo) return '';

  const hasCoords = typeof place.latitude === 'number' && typeof place.longitude === 'number';
  const title = place.venue || zone || `Ubigeo ${place.ubigeo}`;
  const sub = [place.venue ? zone : '', place.ubigeo ? `ubigeo ${place.ubigeo}` : '']
    .filter(Boolean).join(' · ');
  const tag = hasCoords ? 'a' : 'div';
  const href = hasCoords
    ? ` href="geo:${place.latitude},${place.longitude}?q=${place.latitude},${place.longitude}"`
    : '';

  return `
    <div class="rubric">${esc(t('verify.location'))}</div>
    <${tag} class="place"${href}>
      <span class="place__pin">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20 10c0 5.5-8 12-8 12s-8-6.5-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="2.8"/>
        </svg>
      </span>
      <span class="place__body">
        <span class="place__venue">${esc(title)}</span>
        ${sub ? `<span class="place__zone">${esc(sub)}</span>` : ''}
        ${hasCoords ? `<span class="place__coord">${place.latitude.toFixed(6)}, ${place.longitude.toFixed(6)}</span>` : ''}
      </span>
      ${hasCoords ? `<span class="place__go">${esc(t('verify.open_in_maps'))}</span>` : ''}
    </${tag}>`;
}
