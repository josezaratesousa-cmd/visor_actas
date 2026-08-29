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
| `CODE_CIPHER_KEY` | 32 bytes en hexadecimal. Descifra el parámetro del código QR |
| `EXPECTED_ISSUER_ID` | Cuenta que debe haber registrado el acta. Ver más abajo |
| `CUSTODY_*` | Dónde están los PDF firmados. Ver más abajo |

`STAMPING_TOKEN` es **opcional pero recomendable**, y alcanza con uno de solo
lectura.

El identificador de transacción se deriva del hash del archivo, así que una
segunda cuenta que selle el mismo documento genera una fila con el mismo
identificador. La consulta pública devuelve **la registrada más tarde**, es
decir la del impostor. Con token, la consulta se acota a la propia cuenta y
devuelve la legítima.

Sin token el visor tampoco muestra el registro ajeno —`EXPECTED_ISSUER_ID` lo
rechaza— pero informa el acta como todavía en trámite en vez de mostrar la
verdadera. Son dos defensas contra el mismo ataque: **el token recupera el
registro correcto, y la comprobación de emisor impide que uno incorrecto se
presente como verificado.** Conviene tener las dos.

La herramienta de registro necesita un token con permiso de escritura, y esa
corre desde consola, no en la máquina que da a internet.

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

#### Usar S3

El driver de S3 ya viene incluido: **no hay que escribir código**. Sirve para
AWS y para cualquier servicio compatible —MinIO, Wasabi, Backblaze, una
pasarela propia— a través de `CUSTODY_ENDPOINT`.

```ini
CUSTODY_DRIVER=s3
CUSTODY_BUCKET=onpe-actas-2026
CUSTODY_REGION=us-east-1
CUSTODY_PATH=actas/2026          ; prefijo dentro del bucket, puede ir vacío
; CUSTODY_ENDPOINT=https://s3.example.com   ; solo si no es AWS
```

El acta se busca en `s3://<CUSTODY_BUCKET>/<CUSTODY_PATH>/<identificador>.pdf`,
donde el identificador es lo que devuelve el descifrado del código QR.

Hay que instalar la dependencia, que no viene por defecto para no cargarla en
despliegues que usan otro almacenamiento:

```bash
.venv/bin/pip install boto3
```

**Sobre las credenciales:** dejar `CUSTODY_ACCESS_KEY` y `CUSTODY_SECRET_KEY`
vacías es lo preferible en AWS. Sin ellas, boto3 usa el rol de la instancia o
el archivo compartido de credenciales, y no queda ningún secreto en disco. Si
se rellenan, la política de ese usuario debería permitir únicamente
`s3:GetObject` sobre ese prefijo: el visor solo lee, nunca escribe.

El artefacto que implementa esto es **`app/services/custody/s3.py`**. No hace
falta tocarlo para usarlo, solo para cambiar su comportamiento.

#### Usar otro sistema de almacenamiento

Si los PDF no están ni en disco ni en S3 sino en un gestor documental propio,
se escribe una clase y se cambia un valor. Nada más cambia:

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

## Verificación contra las cadenas

El visor puede comprobar el anclaje por su cuenta, sin pasar por el servicio
de atestación ni por su infraestructura:

```ini
LACCHAIN_RPC=                       # nodo de la entidad. Sin esto no se verifica
ROLLUX_RPC=https://rpc.rollux.com
RPC_TIMEOUT=15
```

**El nodo debe ser de la entidad.** Consultar un nodo del proveedor haría que
la verificación pareciera independiente sin serlo: se estaría preguntando a
la misma parte que se quiere comprobar.

LACChain es **público-permisionado**. No hay endpoints abiertos publicados;
los nodos se obtienen registrándose ante la LACChain Alliance. Mientras no
haya uno propio, ese anclaje **no se verifica y el resultado lo dice**:
informa *verificada parcialmente*, no *verificada*. Rollux sí tiene RPC
públicos.

```bash
STAMPING_TOKEN=... .venv/bin/python -m tools.verify_chain acta.pdf \
    --issuer <userId de la entidad>
```

Comprueba, en este orden: que el SHA-256 del archivo es la evidencia
registrada, que la registró la entidad esperada, que el acta figura en el
bloque publicado en IPFS, que las hojas de ese bloque reconstruyen la raíz
declarada, y que esa raíz está escrita en una transacción minada de cada
cadena, con la fecha de su bloque.

Todos esos pasos salvo el del emisor se apoyan en algo que el proveedor no
controla: IPFS es direccionable por contenido, el árbol es aritmética
comprobable, y los nodos responden a cualquiera. Un servicio comprometido que
inventara un hash de transacción quedaría en evidencia: el nodo no la conoce.

## Emisor esperado

El identificador de transacción se deriva del hash del archivo. Eso significa
que **cualquiera que selle ese mismo PDF con su propia cuenta produce un
registro que encaja**: sin comprobar quién lo registró, el visor estaría
confirmando que *alguien* selló el documento, no que lo selló la entidad
electoral.

```ini
EXPECTED_ISSUER_ID=ef60e6d0b2603e41328af4aa4c00a5ee3df7c47d
EXPECTED_ISSUER_NAME=ONPE
```

El identificador se obtiene del campo `result.ownership.userId` de cualquier
consulta a la API con un acta ya registrada por la entidad.

Cuando no coincide, el visor responde **el mismo estado que un acta en
proceso**. No dice "emisor incorrecto": a quien esté sondeando no se le
informa nada, y a un ciudadano nunca se le muestra un tilde verde sobre un
registro de origen desconocido. La discrepancia sí queda registrada como
error en el log, porque durante una jornada electoral un acta atestada por
una cuenta inesperada es algo que un operador tiene que ver el mismo día.

Dejar `EXPECTED_ISSUER_ID` vacío desactiva la comprobación. **No conviene en
producción.**

## Cambiar el descifrado del código QR

El código impreso se convierte en un identificador interno mediante un
**resolvedor**, que es la segunda pieza pensada para reemplazarse.

Por defecto es `aes-gcm`: AES-256-GCM autenticado, con el identificador dentro
del propio código. No necesita ninguna tabla, pero un código autocontenido no
puede ser corto —el sobre criptográfico son 28 bytes— y ronda los 58
caracteres.

Para usar otra técnica, por ejemplo códigos cortos resueltos contra una tabla:

```python
# app/services/code_cipher.py, o un módulo propio importado desde ahí
from app.services.code_cipher import InvalidCode, register

@register("lookup-table")
class TableResolver:
    def __init__(self, settings): ...

    def decode(self, code: str) -> str:
        """Devuelve el identificador, o lanza InvalidCode."""
        ...
```

Después, en el `.env`:

```ini
CODE_RESOLVER=lookup-table
```

Solo hace falta `decode`. Si el resolvedor también genera códigos, conviene
añadir `encode` para que `tools/make_code.py` siga sirviendo.

**Tres reglas que cualquier resolvedor debe cumplir**, y que valen sea cual
sea la técnica:

- **Fallar cerrado.** Un código manipulado tiene que lanzar `InvalidCode`, no
  devolver un identificador plausible.
- **No filtrar la mesa.** Si el código deja adivinar el número de mesa,
  cualquiera enumera todas las actas del país editando la URL.
- **Ser canónico.** Dos cadenas distintas no deben resolver al mismo acta, o
  el límite por dirección se esquiva rotando la representación.

Los artefactos implicados son `app/services/code_cipher.py` —el registro y el
resolvedor por defecto— y `CODE_RESOLVER` en el `.env`.

## Recursos de marca

`web/assets/brand/logo-source.png` es el logotipo institucional. Todo lo demás
en ese directorio se genera a partir de él:

```bash
.venv/bin/python -m tools.build_brand
```

Cambiar la marca es reemplazar ese archivo y volver a correr el script.
Ver [`web/assets/brand/README.md`](web/assets/brand/README.md).

---

## Límite de peticiones y caché

Ajustables en el `.env`, donde están documentados con sus valores:

| Ajuste | Por defecto | Qué hace |
|---|---|---|
| `RATE_LIMIT_BURST` | 60 | Peticiones seguidas admitidas por dirección |
| `RATE_LIMIT_PER_SECOND` | 4 | Ritmo sostenido una vez agotada la ráfaga |
| `RATE_LIMIT_ENABLED` | true | `false` solo para pruebas de carga propias |
| `RECORD_CACHE_SECONDS` | 60 | Cuánto se sirve de memoria un acta ya verificada |

Los techos son altos a propósito. Las operadoras móviles ponen miles de
abonados detrás de una misma dirección, así que un límite estrecho bloquea a
una ciudad y no a un abusador. **Una visita normal gasta unas ocho
peticiones**, de modo que bajar `RATE_LIMIT_BURST` de 20 empieza a rechazar
gente que no hizo nada raro. Un rechazo es un 429 con `Retry-After`, nunca un
bloqueo, y nada se recuerda más allá de la ventana.

La caché es la defensa real: un acta atestada no cambia, así que una que se
comparte mucho llega al servicio de atestación una sola vez. Las actas en
proceso no se cachean, porque quien vuelva después del anclaje tiene que ver
el cambio.

Para volumen electoral conviene además una CDN por delante. El PDF y las
imágenes ya se sirven con `ETag` y `max-age` de un día, y responden `304` a
las peticiones condicionales, así que una CDN absorbe casi todo el tráfico
repetido sin tocar la aplicación.

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
