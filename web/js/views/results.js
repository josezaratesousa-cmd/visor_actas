/**
 * Results panel.
 *
 * Two denominators are in play and mixing them is the classic mistake:
 *   share of an option = votes / valid_votes
 *   turnout            = voters / eligible_voters
 * Blank and null votes are shown as their own rows, never as bars competing
 * with the political organisations.
 */

import { esc, fmt, growBars } from '../core/dom.js';
import { t, current } from '../core/i18n.js';

const PALETTE = ['#D6403E', '#2FA37A', '#E08A2B', '#3B7DD8', '#8B5CF6', '#0E9BA8', '#C2557E'];

export function render(target, record) {
  const r = record.results;
  if (!r) { target.closest('.sheet').hidden = true; return; }

  const locale = current() === 'en' ? 'en-US' : 'es-PE';
  const top = Math.max(...r.options.map(o => o.votes), 1);
  const turnout = r.eligible_voters ? r.voters / r.eligible_voters * 100 : 0;

  const rows = [
    ['results.voters', r.voters, ''],
    ['results.valid', r.valid_votes, ' tally__value--valid'],
    ['results.null', r.null_votes, ' tally__value--null'],
    ['results.blank', r.blank_votes, '']
  ].map(([key, value, cls]) => `
    <div class="tally__row">
      <span class="tally__label">${esc(t(key))}</span>
      <span class="tally__value${cls}">${value}</span>
    </div>`).join('');

  const options = r.options.map((option, index) => {
    const share = r.valid_votes ? option.votes / r.valid_votes * 100 : 0;
    const colour = option.color || PALETTE[index % PALETTE.length];
    return `
      <div class="opt">
        <div class="opt__row">
          <span class="opt__name">${esc(option.name)}</span>
          <span class="opt__votes">${option.votes}</span>
        </div>
        <div class="opt__track">
          <span class="opt__fill" style="background:${esc(colour)}"
                data-width="${(option.votes / top * 100).toFixed(1)}"></span>
        </div>
        <div class="opt__foot">${fmt(share, locale, 2)}%${
          option.party ? ` · ${esc(option.party)}` : ''}</div>
      </div>`;
  }).join('');

  target.innerHTML = `
    <div class="res-head">
      <div>
        <div class="res-head__eyebrow">${esc(t('app.table'))}</div>
        <div class="res-head__title">${esc(t('app.table'))} ${esc(record.station)}</div>
      </div>
      <div class="export">
        <button id="export-json">JSON</button>
        <button id="export-csv">CSV</button>
      </div>
    </div>

    <div class="tally">${rows}</div>

    <div class="rubric">${esc(t('results.turnout'))}</div>
    <div class="turnout">
      <span class="turnout__pct">${fmt(turnout, locale, 1)}%</span>
      <span class="turnout__track">
        <span class="turnout__fill" data-width="${turnout.toFixed(1)}"></span>
      </span>
      <span class="turnout__of">${esc(t('results.turnout_of', { total: r.eligible_voters }))}</span>
    </div>

    <div class="rubric">${esc(t('results.heading'))}</div>
    ${options}
    <p class="provenance">${t('results.source')}</p>`;

  target.querySelector('#export-json')?.addEventListener('click',
    () => download(`${record.station}.json`, JSON.stringify(r, null, 2), 'application/json'));
  target.querySelector('#export-csv')?.addEventListener('click',
    () => download(`${record.station}.csv`, toCsv(r), 'text/csv'));
}

export function animate(target) { growBars(target); }

function toCsv(r) {
  const rows = [['field', 'value'],
    ['eligible_voters', r.eligible_voters], ['voters', r.voters],
    ['valid_votes', r.valid_votes], ['null_votes', r.null_votes],
    ['blank_votes', r.blank_votes]];
  r.options.forEach(o => rows.push([o.name, o.votes]));
  return rows.map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\n');
}

function download(filename, content, mime) {
  const url = URL.createObjectURL(new Blob([content], { type: mime }));
  const link = Object.assign(document.createElement('a'), { href: url, download: filename });
  document.body.appendChild(link); link.click(); link.remove();
  URL.revokeObjectURL(url);
}
