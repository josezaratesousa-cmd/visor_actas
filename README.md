# Visor de actas electorales

Public verifier for electoral tally sheets. A citizen scans the QR printed
on the sheet, sees the document, and can check that it is identical to the
one sealed in blockchain when the count closed.

The viewer only reads. It holds no capability to register evidence: the
class that talks to the attestation API refuses any HTTP method other than
GET, so code reachable from a request has no path to forge an attestation.
Registration is a separate operator tool that runs from a shell.

- **Backend** FastAPI (Python 3.11). Holds the credentials; the browser
  never sees an API token.
- **Frontend** Vanilla HTML, CSS and ES modules. No framework, no build
  step. What ships is what runs, which is also what an auditor reads.
- **Integration guide** [`docs/integration-guide.es.md`](docs/integration-guide.es.md)
  — what the electoral body must send for the viewer to work.

---

## Requirements

| | |
|---|---|
| Python | 3.11 or newer |
| Reverse proxy | Any. Needs to forward to a local port |
| Storage | A filesystem path or an S3-compatible bucket |
| Outbound | HTTPS to the attestation API |

No database. State lives in the attestation API and in custody storage.

---

## Install

```bash
git clone https://github.com/josezaratesousa-cmd/visor_actas.git
cd visor_actas
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Configure

Configuration is read from a `.env` file that lives **outside the
repository**. There is no default copy inside the project tree: a
misconfigured deployment fails on start instead of running quietly with
placeholder credentials.

```bash
sudo mkdir -p /etc/visor-actas
sudo cp .env.example /etc/visor-actas/.env
sudo chmod 600 /etc/visor-actas/.env
sudo chown <service-user> /etc/visor-actas/.env
export APP_ENV_FILE=/etc/visor-actas/.env
```

Fill in `.env`. Every setting is documented there. The three that must be
set before anything works:

| Setting | What it is |
|---|---|
| `STAMPING_TOKEN` | Attestation API token. A read-only token is enough and is what should be used |
| `CODE_CIPHER_KEY` | 32 bytes of hex. Deciphers the QR code parameter |
| `CUSTODY_*` | Where the signed PDFs are. See below |

Generate a cipher key:

```bash
.venv/bin/python -m app.services.code_cipher
```

### Custody: the component you replace

Where the PDFs live is the one seam a deployment is expected to move.
Everything above it only knows that some object hands back the bytes of a
tally sheet.

Two drivers ship with the project:

```ini
CUSTODY_DRIVER=local          # reads <CUSTODY_PATH>/<identifier>.pdf
CUSTODY_DRIVER=s3             # AWS or any S3-compatible service
```

To use an internal document system instead, write one class and set one
value. Nothing else changes:

```python
# app/services/custody/your_backend.py
from app.services.custody import Document, register, safe_identifier

@register("your-name")
class YourBackend:
    def __init__(self, settings): ...
    async def fetch(self, identifier: str) -> Document: ...
    async def exists(self, identifier: str) -> bool: ...
```

Import it in `app/services/custody/__init__.py` so the decorator runs, then
set `CUSTODY_DRIVER=your-name`.

Identifiers arrive from a deciphered QR code and are treated as hostile.
Call `safe_identifier()` before touching storage: a driver that concatenates
one into a path or a key without checking is one crafted code away from
serving an arbitrary file.

## Brand assets

`web/assets/brand/logo-source.png` is the institutional mark. Everything
else in that directory is generated from it:

```bash
.venv/bin/python -m tools.build_brand
```

Replacing the brand means replacing that one file and re-running.
See [`web/assets/brand/README.md`](web/assets/brand/README.md).

---

## Run

```bash
APP_ENV_FILE=/etc/visor-actas/.env \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8081
```

Bind to localhost only and put a reverse proxy in front. The application
does not terminate TLS and does not expect to face the internet directly.

### systemd

```ini
[Unit]
Description=Visor de actas electorales
After=network.target

[Service]
User=visor
WorkingDirectory=/opt/visor_actas
Environment=APP_ENV_FILE=/etc/visor-actas/.env
ExecStart=/opt/visor_actas/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8081
Restart=on-failure
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/visor-actas

[Install]
WantedBy=multi-user.target
```

### Reverse proxy

nginx:

```nginx
location / {
    proxy_pass http://127.0.0.1:8081;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

Apache, with `mod_proxy` and `mod_proxy_http` enabled:

```apache
ProxyPreserveHost On
ProxyPass        / http://127.0.0.1:8081/
ProxyPassReverse / http://127.0.0.1:8081/
```

If the viewer is mounted under a subpath rather than at the root, set
`APP_ROOT_PATH` to that prefix so generated URLs stay correct.

---

## The QR code

The printed QR points at `https://<host>/<code>`. The code is deciphered
server-side into an internal identifier.

**The code must not be the polling station number, nor derivable from it.**
If it were, anyone could enumerate every tally sheet in the country by
editing the URL. It must not be the hash or the transaction id either;
both are public and reachable by other means.

Codes are generated when the ballot material is produced, since the QR is
printed on the sheet before the count. That makes it a logistics deadline,
not a deployment task.

```bash
.venv/bin/python -c "
from app.config import get_settings
from app.services.code_cipher import CodeCipher
print(CodeCipher(get_settings().code_cipher_key).encode('EMC-2026/035253'))"
```

---

## Registering test data

The viewer cannot register. This tool can, and it is the only thing in the
repository that writes to the attestation API.

```bash
# Build two synthetic tally sheets: one intact, one altered after hashing
.venv/bin/python -m tools.make_fixtures

# Render its pages to WebP, which is what the viewer displays
.venv/bin/python -m tools.render_pages tests/fixtures/valid.pdf --out web/assets/sample

# Register it
.venv/bin/python -m tools.register_record tests/fixtures/valid.pdf \
    --results tests/fixtures/results.json \
    --data    tests/fixtures/data.json \
    --lat -12.0768 --long -77.0916
```

Use `--dry-run` to build and validate the payload without sending it.

**The order matters.** The hash must cover the final, already signed PDF,
byte for byte, exactly as it will be stored and served. Hash first and sign
afterwards and every sheet reports as altered. Section 3 of the integration
guide explains why, and it is the most common way this integration fails.

**Fixtures are synthetic.** A real tally sheet carries the names and
identity numbers of the polling station members inside its PAdES signature,
and this repository is public. Never commit a real one.

---

## Tests

```bash
.venv/bin/python -m pytest
```

They cover the parts where a mistake is expensive: the three arithmetic
balances a tally sheet must satisfy, the two different denominators used for
percentages, path traversal and symlink escape in custody, and the QR code
cipher including its rejection of non-canonical encodings.

---

## Layout

```
app/                FastAPI backend
  config.py         settings, read from the .env outside the tree
  models.py         wire contract, validated on ingestion
  routers/          HTTP endpoints
  services/
    stamping.py     read-only client for the attestation API
    code_cipher.py  QR code, AES-256-GCM
    custody/        storage drivers — the replaceable seam
web/                frontend, served as static files
  index.html
  css/              tokens.css holds the palette; nothing else hardcodes colour
  js/core/          i18n, theme, network boundary, DOM helpers
  js/views/         document, verification, results, share
  i18n/             es.json and en.json, exact key parity
  assets/brand/     institutional mark and generated icons
tools/              operator scripts, never imported by the app
tests/
docs/
```

## Language and appearance

Spanish and light are the defaults, and neither the browser language nor the
system colour scheme is consulted. This is a public verifier whose
screenshots get shared and compared: a citizen showing a neighbour "look, it
says authentic" should be showing the same screen. English and dark remain
available as explicit choices that survive reloads.

No user-facing string is hardcoded in a view. Adding a language means adding
one JSON file under `web/i18n/` and listing it in `web/js/core/i18n.js`.

## Security notes

- Credentials live in a `.env` outside the repository, `chmod 600`. Nothing
  in the tree points at a particular host or account.
- The API token travels in a header. Query strings are written to access
  logs in plain text and kept through every rotation and backup.
- The application binds to localhost. TLS belongs to the reverse proxy.
- The viewer is read-only by construction, not by policy.
- PAdES validation and page rendering happen once, when a sheet is
  registered, and the result is cached. Running signature cryptography per
  request does not survive election-night traffic.

## Licence

To be defined with the contracting body.
