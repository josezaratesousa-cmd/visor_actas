/**
 * Orchestrator: loads the record, mounts the views, wires the events.
 *
 * No framework and no build step. The client deploys a directory, not a
 * pipeline, and an auditor reads the same files that run in the browser.
 */

import { $ } from './core/dom.js';
import * as i18n from './core/i18n.js';
import * as theme from './core/theme.js';
import { fetchRecord, currentCode, RecordUnavailable } from './core/api.js';
import * as documentView from './views/document.js';
import * as results from './views/results.js';
import * as verification from './views/verification.js';
import * as share from './views/share.js';
import * as stateView from './views/state.js';

const state = { record: null, verified: false };

async function boot() {
  theme.init();
  await i18n.load(i18n.resolveLocale('es'));
  i18n.apply();

  // Antes de cualquier salida temprana: los controles de idioma y tema
  // valen en todas las pantallas, y en las de estado mas que en ninguna
  // -si el acta no aparece, poder leer el motivo en el propio idioma es
  // justo lo que hace falta.
  $('#btn-lang').textContent = i18n.current().toUpperCase();
  wireChrome();

  const code = currentCode();
  if (!code) { showState('no_code'); return; }

  state.record = await fetchRecord(code);
  const record = state.record;

  // A sheet still in transit has no document and no attestation to show.
  if (record.status === 'pending') { showState('pending'); return; }

  $('#station').textContent = `${i18n.t('app.table')} ${record.station}`;
  $('#process').textContent = record.process.name;
  $('#rail-label').textContent = i18n.t('verify.cta');
  $('#results-note').textContent = i18n.t('results.votes', { count: record.results.voters });

  document.body.dataset.view = 'record';
  documentView.render($('#canvas'), record);
  documentView.wireDownload($('#canvas'));
  results.render($('#results-body'), record);
  share.render($('#share-body'), record);
  verification.renderSteps($('#verify-body'));

  wire();
}

function openSheet(id) {
  closeSheets();
  $(`#${id}`).dataset.open = '1';
  $('#veil').dataset.on = '1';
}

function closeSheets() {
  document.querySelectorAll('.sheet').forEach(sheet => { sheet.dataset.open = '0'; });
  $('#results-handle').setAttribute('aria-expanded', 'false');
  $('#veil').dataset.on = '0';
}

/** Controls that belong to every screen. */
function wireChrome() {
  $('#btn-theme').addEventListener('click', () => theme.toggle());
  $('#btn-lang').addEventListener('click', () => {
    const available = i18n.locales();
    const next = available[(available.indexOf(i18n.current()) + 1) % available.length];
    i18n.setLocale(next);
  });
}

/** Controls that only make sense once a sheet is on screen. */
function wire() {
  $('#veil').addEventListener('click', closeSheets);
  document.querySelectorAll('[data-close]').forEach(button =>
    button.addEventListener('click', closeSheets));

  $('#results-handle').addEventListener('click', () => {
    const sheet = $('#sheet-results');
    const open = sheet.dataset.open === '1';
    closeSheets();
    if (!open) {
      sheet.dataset.open = '1';
      $('#veil').dataset.on = '1';
      $('#results-handle').setAttribute('aria-expanded', 'true');
      results.animate($('#results-body'));
    }
  });

  // Once verified, the result stays in memory: tapping again just reopens it.
  $('#rail').addEventListener('click', async () => {
    openSheet('sheet-verify');
    if (state.verified) return;
    state.verified = true;
    await verification.run($('#verify-body'), state.record);
    $('#rail').dataset.done = '1';
    const status = state.record.signature.status
      || (state.record.signature.valid ? 'valid' : 'invalid');
    $('#rail-label').textContent = i18n.t(
      status === 'valid' ? 'verify.cta_done'
      : status === 'unsigned' ? 'verify.cta_unsigned'
      : 'verify.cta_warning');
  });

  $('#btn-share').addEventListener('click', () =>
    share.share(state.record, () => openSheet('sheet-share')));

}

/** Hand the whole screen over to a state page. */
function showState(kind) {
  document.body.dataset.view = 'state';
  $('#station').textContent = '';
  $('#process').textContent = '';
  stateView.render($('#canvas'), kind);
}

boot().catch(error => {
  console.error(error);
  showState(error instanceof RecordUnavailable ? 'not_found' : 'unavailable');
});
