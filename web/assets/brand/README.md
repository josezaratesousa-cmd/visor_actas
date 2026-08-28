# Institutional brand assets

**These files are placeholders. Replace them with the official ONPE assets
before any public deployment.**

The originals must come from ONPE's visual identity manual, delivered under
the contract. They were not taken from the public website: onpe.gob.pe sits
behind a WAF that answers asset requests with a 403, and a scraped
`favicon.ico` would be 16 or 32 pixels — useless for a header on a retina
phone, and possibly an outdated version of the mark.

## What to drop in

| File | Format | Used for |
|---|---|---|
| `logo.svg` | SVG, horizontal lockup | Top bar. Scales to any density |
| `favicon.ico` | ICO, 16+32+48 px | Browser tab |
| `icon-192.png` | PNG, 192×192, transparent | Home screen, PWA |
| `icon-512.png` | PNG, 512×512, transparent | Splash screen, PWA |
| `og-card.png` | PNG, 1200×630 | Link preview on social networks |

Keep the file names. Nothing else in the project needs to change.

## While they are missing

The top bar falls back to a typographic wordmark rendered in CSS. It is
deliberately plain: it does not imitate the institutional mark, so nobody
mistakes the placeholder for the real thing in a screenshot or a demo.
