/**
 * Full-screen states: nothing found, code unreadable, sheet still in transit.
 *
 * These share one layout on purpose. A citizen who scanned a QR and did not
 * get their tally sheet is already unsure whether they did something wrong;
 * three different-looking error pages would make that worse. Same icon slot,
 * same heading, same explanation, and always a next step.
 *
 * None of them says "error". The reader did nothing wrong in any of these
 * cases, and a page that blames them is a page they abandon.
 */

import { esc } from '../core/dom.js';
import { t } from '../core/i18n.js';

const ICONS = {
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/><path d="M11 8v3.5"/><circle cx="11" cy="14.5" r=".6" fill="currentColor"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  scan: '<path d="M4 8V5a1 1 0 0 1 1-1h3"/><path d="M16 4h3a1 1 0 0 1 1 1v3"/><path d="M20 16v3a1 1 0 0 1-1 1h-3"/><path d="M8 20H5a1 1 0 0 1-1-1v-3"/><path d="M8 12h8"/>',
  offline: '<path d="M12 2.5 4 6v6c0 4.6 3.2 8.4 8 9.5 4.8-1.1 8-4.9 8-9.5V6l-8-3.5Z"/><path d="M12 8v4.5"/><circle cx="12" cy="16" r=".7" fill="currentColor"/>',
};

const TONES = { neutral: 'neutral', waiting: 'waiting' };

/** The stages a sheet goes through before it becomes verifiable. */
const STAGES = ['pending.step_count', 'pending.step_receive', 'pending.step_sign',
                'pending.step_seal', 'pending.step_ready'];

export function render(target, kind) {
  const screens = {
    not_found: {
      icon: 'search', tone: TONES.neutral,
      title: 'state.not_found_title',
      lead: 'state.not_found_lead',
      notes: ['state.not_found_note_typo', 'state.not_found_note_damaged',
              'state.not_found_note_pending'],
    },
    no_code: {
      icon: 'scan', tone: TONES.neutral,
      title: 'state.no_code_title',
      lead: 'state.no_code_lead',
      notes: ['state.no_code_note_where'],
    },
    pending: {
      icon: 'clock', tone: TONES.waiting,
      title: 'pending.title',
      lead: 'pending.body',
      stages: true,
      foot: 'pending.retry',
    },
    unavailable: {
      icon: 'offline', tone: TONES.neutral,
      title: 'state.unavailable_title',
      lead: 'state.unavailable_lead',
      notes: ['state.unavailable_note'],
    },
  };

  const screen = screens[kind] || screens.unavailable;

  target.innerHTML = `
    <section class="state state--${screen.tone}">
      <span class="state__icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
          ${ICONS[screen.icon]}
        </svg>
      </span>

      <h1 class="state__title">${esc(t(screen.title))}</h1>
      <p class="state__lead">${esc(t(screen.lead))}</p>

      ${screen.stages ? `
        <ol class="state__stages">
          ${STAGES.map(key => `<li>${esc(t(key))}</li>`).join('')}
        </ol>` : ''}

      ${screen.notes ? `
        <ul class="state__notes">
          ${screen.notes.map(key => `<li>${esc(t(key))}</li>`).join('')}
        </ul>` : ''}

      ${screen.foot ? `<p class="state__foot">${esc(t(screen.foot))}</p>` : ''}
    </section>`;
}
