/**
 * Orchestrator: loads the record, mounts the views, wires the events.
 *
 * No framework and no build step. The client deploys a directory, not a
 * pipeline, and an auditor reads the same files that run in the browser.
 */

import { $ } from './core/dom.js';
import * as i18n from './core/i18n.js';
import * as theme from './core/theme.js';
import { fetchRecord, currentCode } from './core/api.js';
import * as documentView from './views/document.js';
import * as results from './views/results.js';
import * as verification from './views/verification.js';
import * as share from './views/share.js';

const state = { record: null, verified: false };

async function boot() {
  theme.init();
  await i18n.load(i18n.resolveLocale('es'));
  i18n.apply();

  state.record = await fetchRecord(currentCode());
  const record = state.record;

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
    $('#rail-label').textContent = i18n.t(
      state.record.signature.valid ? 'verify.cta_done' : 'verify.cta_warning');
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

boot().catch(error => {
  console.error(error);
  $('#canvas').innerHTML =
    `<p class="provenance">${i18n.t('errors.unavailable')}</p>`;
});
