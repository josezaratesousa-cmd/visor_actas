# Visor de actas electorales

Verificador público de actas de escrutinio. El ciudadano escanea el código QR
impreso en el acta, ve el documento, y puede comprobar que es idéntico al que
se selló en blockchain cuando cerró el conteo.

**El visor solo lee.** No tiene capacidad de registrar evidencia: la clase que
habla con el API de atestación rechaza cualquier método HTTP que no sea GET,
así que el código alcanzable desde una petición no tiene camino para falsificar
una atestación. El registro es una herramienta aparte que corre desde consola.

- **Backend** FastAPI (Python 3.11). Guarda las credenciales; el navegador
  nunca ve un token.
- **Frontend** HTML, CSS y módulos ES a secas. Sin framework y sin compilación.
  Lo que se despliega es lo que corre, que es también lo que lee un auditor.
- **Guía de integración** [`docs/integration-guide.es.md`](docs/integration-guide.es.md)
  — qué debe enviar la entidad electoral para que el visor funcione.

> **Idiomas.** El código está en inglés: funciones, variables, directorios.
> La documentación está en español, porque la leen personas y el proyecto es
> para una entidad peruana. La interfaz es bilingüe (ver más abajo).

---

## Requisitos

| | |
|---|---|
| Python | 3.11 o superior |
| Proxy inverso | Cualquiera. Debe reenviar a un puerto local |
| Almacenamiento | Una ruta del sistema de archivos o un bucket S3 |
| Salida | HTTPS hacia el API de atestación |

Sin base de datos. El estado vive en el API de atestación y en la custodia.

---

## Instalación

```bash
git clone https://github.com/josezaratesousa-cmd/visor_actas.git
cd visor_actas
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Configuración

La configuración se lee de un archivo `.env` que vive **fuera del
repositorio**. No hay copia por defecto dentro del árbol del proyecto: un
despliegue mal configurado falla al arrancar, en lugar de correr en silencio
con credenciales de relleno.

```bash
sudo mkdir -p /etc/visor-actas
sudo cp .env.example /etc/visor-actas/.env
sudo chmod 600 /etc/visor-actas/.env
sudo chown <usuario-del-servicio> /etc/visor-actas/.env
export APP_ENV_FILE=/etc/visor-actas/.env
```

Complete el `.env`. Cada ajuste está documentado ahí. Los tres que deben estar
puestos antes de que nada funcione:

| Ajuste | Qué es |
|---|---|
| `STAMPING_TOKEN` | Token del API de atestación. Alcanza con uno de solo lectura, y es el que conviene usar |
| `CODE_CIPHER_KEY` | 32 bytes en hexadecimal. Descifra el parámetro del código QR |
| `CUSTODY_*` | Dónde están los PDF firmados. Ver más abajo |

Generar una clave de cifrado:

```bash
.venv/bin/python -m app.services.code_cipher
```

### Custodia: el componente que se reemplaza

Dónde viven los PDF es la única costura que un despliegue está pensado para
mover. Todo lo que está por encima solo sabe que algún objeto le devuelve los
bytes de un acta.

El proyecto trae dos drivers:

```ini
CUSTODY_DRIVER=local          # lee <CUSTODY_PATH>/<identificador>.pdf
CUSTODY_DRIVER=s3             # AWS o cualquier servicio compatible con S3
```

Para usar un sistema documental propio, se escribe una clase y se cambia un
valor. Nada más cambia:

```python
# app/services/custody/your_backend.py
from app.services.custody import Document, register, safe_identifier

@register("nombre-propio")
class YourBackend:
    def __init__(self, settings): ...
    async def fetch(self, identifier: str) -> Document: ...
    async def exists(self, identifier: str) -> bool: ...
```

Se importa en `app/services/custody/__init__.py` para que corra el decorador,
y se pone `CUSTODY_DRIVER=nombre-propio`.

**Los identificadores llegan de un código QR descifrado y se tratan como
entrada hostil.** Llame a `safe_identifier()` antes de tocar el
almacenamiento: un driver que concatena uno en una ruta o una clave sin
validar está a un código preparado de servir un archivo arbitrario.

## Recursos de marca

`web/assets/brand/logo-source.png` es el logotipo institucional. Todo lo demás
en ese directorio se genera a partir de él:

```bash
.venv/bin/python -m tools.build_brand
```

Cambiar la marca es reemplazar ese archivo y volver a correr el script.
Ver [`web/assets/brand/README.md`](web/assets/brand/README.md).

---

## Ejecución

```bash
APP_ENV_FILE=/etc/visor-actas/.env \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8081
```

Escuche solo en localhost y ponga un proxy inverso delante. La aplicación no
termina TLS ni espera dar a internet directamente.

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

### Proxy inverso

nginx:

```nginx
location / {
    proxy_pass http://127.0.0.1:8081;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

Apache, con `mod_proxy` y `mod_proxy_http` habilitados:

```apache
ProxyPreserveHost On
ProxyPass        / http://127.0.0.1:8081/
ProxyPassReverse / http://127.0.0.1:8081/
```

Si el visor se monta bajo un subdirectorio en vez de la raíz, ponga ese
prefijo en `APP_ROOT_PATH` para que las URL generadas sigan siendo correctas.

---

## El código QR

El QR impreso apunta a `https://<dominio>/<codigo>`. El código se descifra del
lado servidor para obtener un identificador interno.

**El código no debe ser el número de mesa ni derivable de él.** Si lo fuera,
cualquiera podría enumerar todas las actas del país modificando la URL.
Tampoco debe ser el hash ni el trxid: los dos son públicos por otras vías.

Los códigos se generan cuando se produce el material electoral, porque el QR
va impreso en el acta antes del escrutinio. Eso lo convierte en un plazo
logístico, no en una tarea de despliegue.

```bash
.venv/bin/python -c "
from app.config import get_settings
from app.services.code_cipher import CodeCipher
print(CodeCipher(get_settings().code_cipher_key).encode('EMC-2026/035253'))"
```

---

## Datos de prueba

El visor no puede registrar. Esta herramienta sí, y es lo único en el
repositorio que escribe en el API de atestación.

```bash
# Genera dos actas sintéticas: una íntegra y otra alterada después del hash
.venv/bin/python -m tools.make_fixtures

# Renderiza sus páginas a WebP, que es lo que muestra el visor
.venv/bin/python -m tools.render_pages tests/fixtures/valid.pdf --out web/assets/sample

# La registra
.venv/bin/python -m tools.register_record tests/fixtures/valid.pdf \
    --results tests/fixtures/results.json \
    --data    tests/fixtures/data.json \
    --lat -12.0768 --long -77.0916
```

Con `--dry-run` arma y valida el cuerpo sin enviar nada.

**El orden importa.** El hash debe cubrir el PDF final, ya firmado, byte por
byte, tal como quedará almacenado y como se servirá. Si se calcula el hash
antes de firmar, todas las actas se reportan como alteradas. La sección 3 de
la guía de integración explica por qué, y es la forma más común en que esta
integración falla.

**Las actas de prueba son sintéticas.** Un acta real lleva los nombres y
documentos de identidad de los miembros de mesa dentro de su firma PAdES, y
este repositorio es público. Nunca versione una real.

---

## Pruebas

```bash
.venv/bin/python -m pytest
```

Cubren las partes donde un error sale caro: los tres cuadres aritméticos que
debe satisfacer un acta, los dos denominadores distintos que se usan para los
porcentajes, el escape de rutas y de enlaces simbólicos en la custodia, y el
cifrado del código QR incluido su rechazo de codificaciones no canónicas.

---

## Estructura

```
app/                backend FastAPI
  config.py         configuración, leída del .env externo
  models.py         contrato de datos, validado en la ingesta
  routers/          endpoints HTTP
  services/
    stamping.py     cliente de solo lectura del API de atestación
    code_cipher.py  código QR, AES-256-GCM
    custody/        drivers de almacenamiento — la costura reemplazable
web/                frontend, servido como archivos estáticos
  index.html
  css/              tokens.css tiene la paleta; nada más fija un color
  js/core/          i18n, tema, frontera de red, utilidades de DOM
  js/views/         documento, verificación, resultados, compartir
  i18n/             es.json y en.json, paridad exacta de claves
  assets/brand/     logotipo institucional e iconos generados
tools/              scripts de operador, nunca importados por la aplicación
tests/
docs/
```

## Idioma y apariencia

**Español y modo claro son los valores por defecto**, y no se consulta ni el
idioma del navegador ni el esquema de color del sistema. Este es un
verificador público cuyas capturas se comparten y se comparan: un ciudadano
que le muestra a su vecino "mirá, dice que es auténtica" tiene que estar
mostrando la misma pantalla. Inglés y modo oscuro siguen disponibles como
elección explícita, y una vez elegidos sobreviven a las recargas.

Ninguna cadena visible está escrita a mano en una vista. Agregar un idioma es
agregar un archivo JSON en `web/i18n/` y listarlo en `web/js/core/i18n.js`.

## Notas de seguridad

- Las credenciales viven en un `.env` fuera del repositorio, `chmod 600`. Nada
  en el árbol apunta a una máquina o una cuenta concreta.
- El token viaja por cabecera. Las query strings quedan escritas en texto
  plano en los logs de acceso y permanecen ahí a través de cada rotación y
  cada respaldo.
- La aplicación escucha en localhost. El TLS es del proxy inverso.
- El visor es de solo lectura por construcción, no por política.
- La validación PAdES y el renderizado de páginas ocurren una sola vez, al
  registrar el acta, y el resultado se cachea. Correr criptografía de firmas
  por petición no sobrevive al tráfico de una noche electoral.

## Licencia

A definir con la entidad contratante.
