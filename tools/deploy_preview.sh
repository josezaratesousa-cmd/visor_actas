#!/usr/bin/env bash
# Publish web/ as a static preview while the FastAPI layer is being built.
# Temporary: once uvicorn serves the app, Apache only proxies to it.
#
# Apache runs under the "nobody" group on this host, so the published tree
# has to be group-readable by it. rsync alone leaves the source group, which
# yields a 403 on every file.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)/web"
DST="/home/votolibre/public_html/peru/2026"
WEB_GROUP="nobody"

mkdir -p "$DST"
rsync -a --delete --exclude '.git*' "$SRC/" "$DST/"

cat > "$DST/.htaccess" <<'HT'
Options -Indexes
AddType image/webp .webp
<FilesMatch "\.(json|js|css|html)$">
  Header set Cache-Control "no-store, no-cache, must-revalidate, max-age=0"
</FilesMatch>
HT

chgrp -R "$WEB_GROUP" "$DST"
find "$DST" -type d -exec chmod 2750 {} +
find "$DST" -type f -exec chmod 640 {} +

echo "published -> $DST"
