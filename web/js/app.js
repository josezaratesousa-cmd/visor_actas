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

const state = { record: null, verified: false };

async function boot() {
  theme.init();
  await i18n.load(i18n.resolveLocale('es'));
  i18n.apply();

  const code = currentCode();
  if (!code) { showMessage('errors.no_code'); return; }

  state.record = await fetchRecord(code);
  const record = state.record;

  // A sheet still in transit has no document and no attestation to show.
  if (record.status === 'pending') { showPending(record); return; }

  $('#station').textContent = `${i18n.t('app.table')} ${record.station}`;
  $('#process').textContent = record.process.name;
  $('#rail-label').textContent = i18n.t('verify.cta');
  $('#btn-lang').textContent = i18n.current().toUpperCase();
  $('#results-note').textContent = i18n.t('results.votes', { count: record.results.voters });

  documentView.render($('#canvas'), record);
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

  $('#btn-theme').addEventListener('click', () => theme.toggle());

  $('#btn-lang').addEventListener('click', () => {
    const locales = i18n.locales();
    const next = locales[(locales.indexOf(i18n.current()) + 1) % locales.length];
    i18n.setLocale(next);
  });
}

function showMessage(key) {
  $('#rail').hidden = true;
  document.querySelectorAll('.sheet').forEach(s => { s.hidden = true; });
  $('#canvas').innerHTML = `<p class="provenance">${i18n.t(key)}</p>`;
}

/** The sheet exists but is not verifiable yet: say where it is, not "error". */
function showPending(record) {
  $('#station').textContent = i18n.t('pending.title');
  $('#process').textContent = '';
  $('#rail').hidden = true;
  document.querySelectorAll('.sheet').forEach(s => { s.hidden = true; });
  $('#canvas').innerHTML = `
    <div class="pending">
      <h1 class="pending__title">${i18n.t('pending.title')}</h1>
      <p class="pending__text">${i18n.t('pending.body')}</p>
      <ol class="pending__steps">
        ${['pending.step_count', 'pending.step_receive', 'pending.step_sign',
           'pending.step_seal', 'pending.step_ready']
          .map(k => `<li>${i18n.t(k)}</li>`).join('')}
      </ol>
      <p class="provenance">${i18n.t('pending.retry')}</p>
    </div>`;
}

boot().catch(error => {
  console.error(error);
  showMessage(error instanceof RecordUnavailable
    ? 'errors.not_found' : 'errors.unavailable');
});
