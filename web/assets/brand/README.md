# Institutional brand assets

`logo-source.png` is the ONPE mark as delivered. Everything else here is
generated from it by `tools/build_brand.py`, so updating the brand means
replacing that one file and re-running the script.

## Two things the script does to a delivered asset

**The white background becomes transparent.** The delivered PNG is opaque
RGB and would render as a white rectangle in dark mode. Only pixels at or
above 240 on every channel are cleared, so the navy and the red are
untouched.

**Square icons pad the horizontal lockup.** A 16-pixel favicon of a wide
lockup is illegible. If the identity manual defines an isotype for small
sizes — and it almost certainly does — that is what should replace
`icon-*.png` and `favicon.ico`.

## Still worth requesting from ONPE

| File | Why |
|---|---|
| `logo.svg` | The source is 178 x 107 px. Fine for a 26 px header today, short for anything larger or for print |
| isotype | For favicon and app icons at small sizes |
| `og-card.png` | 1200 x 630, for the link preview when a citizen shares a tally sheet |

When the SVG arrives, drop it in as `logo.svg` and change one line in
`web/index.html`.

## Generated files

| File | Used for |
|---|---|
| `logo.png` | Top bar, background cleared |
| `favicon.ico` | Browser tab, 16 + 32 + 48 px |
| `icon-192.png` | Home screen, PWA |
| `icon-512.png` | Splash screen, PWA |
