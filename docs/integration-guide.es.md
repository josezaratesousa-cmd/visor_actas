# Guía de integración — Actas electorales verificables

**Destinatario:** entidad que organiza el proceso electoral
**Servicio:** registro de evidencia digital en blockchain (Stamping.io)
**Versión:** 1.1
**Alcance:** qué enviar al API de atestación para que el visor público funcione

> Este documento está en español a propósito: lo consume el equipo técnico de
> la entidad electoral. El código del proyecto está en inglés.

---

## 1. Qué hace este documento

Define exactamente qué debe enviarse al API de atestación para que cada acta
quede registrada y pueda mostrarse después en el visor público que consulta
el ciudadano al escanear el código QR impreso.

**El visor muestra únicamente lo que se haya enviado.** Un campo que no se
envía no se muestra: no hay valores por defecto, no se infiere nada y no se
completa desde otras fuentes. La sección 8 detalla qué ocurre cuando falta
cada campo.

---

## 2. Vista general

```
  ESCRUTINIO             ENTIDAD                  ATESTACIÓN        CIUDADANO
  ──────────             ───────                  ──────────        ─────────
  Acta física ──▶ Digitaliza y firma (PAdES)
                  Calcula SHA-256 del PDF firmado
                  Sube el PDF a su custodia
                  POST /stamp/  ────────────▶  Registra evidencia
                                               Sella en blockchain
                                               Devuelve trxid
                  Imprime el QR con el código ──────────────────▶  Escanea
                                                                   Ve el acta
                  El visor resuelve: código → PDF → hash → trxid   Verifica
                  GET /stamp/get/  ─────────▶  Devuelve atestación ▶ Resultado
```

**El hash es el vínculo.** Todo depende de que el SHA-256 enviado sea el del
archivo exacto que después verá el ciudadano.

---

## 3. Regla crítica: el orden del hash

> **El SHA-256 debe calcularse sobre el PDF final, ya firmado con PAdES,
> byte por byte, tal como quedará almacenado y como se entregará al
> ciudadano.**

Esta es la causa número uno de falla en integraciones de este tipo. Si el
hash se calcula antes de firmar, o si después de enviarlo el PDF se vuelve a
guardar con cualquier herramienta que lo reescriba, el hash deja de coincidir
y **el visor reportará el acta como alterada** aunque el contenido sea
correcto.

Secuencia obligatoria:

1. Generar el PDF del acta
2. Aplicar **todas** las firmas PAdES (sección 7)
3. Cerrar el archivo. No volver a abrirlo ni reescribirlo
4. Calcular `SHA-256` sobre los bytes de ese archivo
5. Subir ese archivo a custodia
6. Enviar el hash

Operaciones que rompen el hash después del paso 3: linealizar, optimizar,
comprimir, agregar metadatos XMP, re-guardar desde cualquier visor, aplicar
OCR, rotar páginas, o agregar una firma adicional.

Si hay que agregar una firma después, el acta debe **volver a registrarse**
como evidencia nueva, con su nuevo hash.

---

## 4. Endpoint de registro

### 4.1 Petición

```
POST https://api.stamping.io/stamp/
Content-Type: application/json
Authorization: Bearer <token>
```

**Autenticación.** En orden de preferencia:

| Forma | Cabecera |
|---|---|
| Bearer | `Authorization: Bearer <token>` |
| Token propio | `X-API-Token: <token>` |
| Basic | `Authorization: Basic base64(customerid:token)` |

> **Aviso de seguridad.** No enviar el token como parámetro de query string
> (`?token=...`). Las query strings quedan escritas en texto plano en los
> logs de acceso del servidor web, y ahí permanecen a través de cada rotación
> y cada respaldo. Un credencial enviado así es un credencial publicado a
> cualquiera que pueda leer un archivo de log. Use siempre cabecera.

**El modo debe ser asíncrono.** El campo `info` solo se acepta con
`async: "true"` y por cuerpo POST. Enviarlo por GET produce un rechazo 400.

### 4.2 Campos

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `evidence` | string(64) hex | **Sí** | SHA-256 del PDF firmado. Minúsculas, sin `0x` |
| `async` | `"true"` | **Sí** | Exactamente esa cadena |
| `transactionType` | string | **Sí** | Código del proceso electoral. Ver 4.3 |
| `subject` | string | **Sí** | Formato: `Mesa NNNNNN` |
| `info` | base64 | **Sí** | JSON de resultados. Ver sección 5 |
| `data` | base64 | Recomendado | JSON de identificación y ubicación. Ver sección 6 |
| `lat` | number | Opcional | Latitud decimal, −90 a 90 |
| `long` | number | Opcional | Longitud decimal, −180 a 180 |
| `external_key` | string | Recomendado | Clave propia para consultar sin trxid |
| `timestamp` | number | Opcional | Epoch en milisegundos del escrutinio |

No enviar: `server` (obsoleto), `hash2`, `hash3`, `userid`.

### 4.3 `transactionType`

Código corto y estable por proceso. Se muestra junto al número de mesa.

- Máximo 12 caracteres visibles; el resto se trunca
- Solo `A–Z`, `0–9` y guion
- Único e inmutable por proceso, sin reutilizar entre procesos

Ejemplos: `EMC-2026`, `EG-2026-1V`, `EG-2026-2V`

El nombre completo para mostrar va en `data.proceso.nombre`, no aquí.

### 4.4 `external_key`

Permite consultar un acta con nomenclatura propia sin guardar el `trxid`.

Formato sugerido: `<ENTIDAD>-<transactionType>-<mesa>`

Debe ser único dentro de la cuenta. La consulta por `external_key` **exige
token válido**: no es pública, a diferencia de la consulta por hash.

### 4.5 Respuesta

```json
{
  "code": 200,
  "message": "OK",
  "result": {
    "trxid": "…", "evidence": "…", "nonce": "…", "timestamp": 1791234567890,
    "proof": {
      "algorithm": "Ed25519", "signature": "…", "publicKey": "…",
      "signedFields": ["evidence", "trxid", "timestamp"]
    }
  }
}
```

`trxid` es siempre `sha1(evidence)`, así que puede calcularse sin depender
de la respuesta.

**Sobre `proof`:** es el comprobante firmado de que el servicio recibió esa
evidencia en ese momento. **No se almacena del lado del servicio.** Quien
registra debe conservarlo: es la prueba ante una discrepancia futura del tipo
"envié el acta y nunca se registró".

### 4.6 Códigos de error

| Código | Significado | Acción |
|---|---|---|
| 200 | Registrado | Guardar `trxid` y `proof` |
| 200 + `duplicated` | Hash ya registrado | Verificar si es reenvío legítimo |
| 303 | `async` ausente o inválido | Corregir a `"true"` |
| 400 | `evidence` ausente, o `info` mal enviado | Revisar 4.2 |
| 401 / 402 | Token ausente o inválido | Revisar cabecera |
| 403 | Origen o IP no autorizados | Registrar la IP de salida |
| 500 | Error interno | Reintentar citando la referencia `err_<id>` |

**Duplicados.** Dos actas distintas nunca producen el mismo hash, así que un
duplicado significa reenvío del mismo archivo. El registro es idempotente por
hash: reenviar no crea un registro nuevo. Use retroceso exponencial.

---

## 5. Campo `info` — resultados del escrutinio

JSON codificado en **base64 estándar** (RFC 4648, con relleno `=`).

### 5.1 Esquema

Los valores del ejemplo son ilustrativos. **La estructura no lo es:** el
visor lee exactamente estos campos, con estos nombres, y no infiere ninguno
a partir de otro.

```json
{
  "version": "1.0",
  "mesa": "035253",
  "electores_habiles": 287,
  "votantes": 241,
  "votos_validos": 223,
  "votos_nulos": 7,
  "votos_blancos": 11,
  "opciones": [
    { "orden": 1, "codigo": "MRU", "nombre": "Movimiento Regional Unidad",
      "partido": "M.R.U. + Alianza", "votos": 86 },
    { "orden": 2, "codigo": "ACL", "nombre": "Alianza Cívica del Litoral",
      "partido": "ACL", "votos": 62 }
  ]
}
```

### 5.2 Qué muestra el visor

| Campo | Dónde aparece |
|---|---|
| `votantes` | Tarjeta "Cantidad de votantes" |
| `votos_validos` | Tarjeta "Votos válidos" |
| `votos_nulos` | Tarjeta "Votos nulos" |
| `votos_blancos` | Tarjeta "Votos en blanco" |
| `electores_habiles` | Denominador de la participación |
| `opciones[].nombre` | Título de cada barra |
| `opciones[].votos` | Cifra a la derecha |
| `opciones[].partido` | Línea inferior, junto al porcentaje |

### 5.3 Reglas

| Campo | Obligatorio | Regla |
|---|---|---|
| `mesa` | Sí | Debe coincidir con `subject` |
| `electores_habiles` | Sí | Electores registrados en la mesa |
| `votantes` | Sí | No puede superar `electores_habiles` |
| `votos_validos` | Sí | |
| `votos_nulos` | Sí | Enviar `0` si no hubo. **No omitir** |
| `votos_blancos` | Sí | Enviar `0` si no hubo. **No omitir** |
| `opciones` | Sí | Solo organizaciones políticas |
| `opciones[].partido` | Recomendado | Partido o alianza |
| `opciones[].orden` | Recomendado | Define el orden de presentación |
| `opciones[].color` | Opcional | Hex. Ver 5.5 |

**Blancos y nulos no van dentro de `opciones`.** Van en sus propios campos:
el visor los presenta como tarjetas separadas, no como barras que compiten
con las organizaciones políticas.

### 5.4 Los dos denominadores

La fuente de error más frecuente al armar el JSON. Se usan **dos
denominadores distintos**:

- **Porcentaje de cada organización** = `votos / votos_validos`
  En el ejemplo: 86 / 223 = **38,57 %**
- **Participación** = `votantes / electores_habiles`
  En el ejemplo: 241 / 287 = **84,0 %**

El porcentaje de una organización **no** se calcula sobre `votantes`: los
nulos y blancos no se atribuyen a ninguna opción, y contarlos en el
denominador subestimaría a todas por igual.

**Cuadres obligatorios.** El visor no corrige las cifras; las muestra como
llegan. Si no cuadran, la inconsistencia queda visible para cualquier
ciudadano:

```
suma(opciones[].votos)                      = votos_validos
votos_validos + votos_nulos + votos_blancos = votantes
votantes                                    ≤ electores_habiles
```

### 5.5 Color por organización

Sin `color`, el visor asigna colores de una paleta propia por posición,
solo para distinguir las barras.

Si se prefieren los colores oficiales de cada organización, deben enviarse
explícitamente en hex. Conviene definir esta política de forma expresa: en
contexto electoral, que un tercero elija los colores de los partidos puede
leerse como toma de posición, aunque la asignación sea secuencial.

### 5.6 Tamaño

Mantener el JSON por debajo de 32 KB antes de codificar.

---

## 6. Campo `data` — identificación y ubicación

También base64 de un JSON.

### 6.1 Esquema

```json
{
  "version": "1.0",
  "mesa": "035253",
  "folio": "A-035253-6",
  "proceso": {
    "codigo": "EMC-2026",
    "nombre": "Elecciones Municipales 2026",
    "tipo": "Concejo municipal distrital"
  },
  "ubicacion": {
    "local": "I.E. 1120 Pedro A. Labarthe",
    "direccion": "Av. Precursores 1120",
    "distrito": "San Miguel", "provincia": "Lima",
    "departamento": "Lima", "ubigeo": "150132"
  },
  "acta": { "tipo": "escrutinio", "paginas": 2 }
}
```

### 6.2 Reglas

| Campo | Obligatorio | Regla |
|---|---|---|
| `mesa` | Sí | Debe coincidir con `info.mesa` y con `subject` |
| `folio` | Recomendado | Folio impreso en el acta física |
| `proceso.codigo` | Sí | Debe coincidir con `transactionType` |
| `proceso.nombre` | Sí | Nombre completo, tal como se muestra |
| `ubicacion` | Recomendado | Ver 6.3 |
| `ubigeo` | Recomendado | Seis dígitos, **como cadena** |

### 6.3 Ubicación

Todo lo relativo a la ubicación viaja dentro de `data.ubicacion`. Si no
viene, la sección no se muestra: no aparece un espacio vacío ni un mensaje
de "sin datos".

Las coordenadas son lo único que va fuera de `data`: en `lat` y `long`, en
el nivel superior de la petición.

| Lo que se envía | Qué muestra el visor |
|---|---|
| `ubicacion` + `lat`/`long` | Local, zona y coordenadas, con botón "Abrir en Mapas" |
| `ubicacion` sin coordenadas | Local y zona en texto. Sin botón |
| Solo `ubigeo` dentro de `ubicacion` | El ubigeo como texto de zona |
| Sin `ubicacion` | La sección no aparece |

El botón aparece **únicamente** con coordenadas. Sin ellas no se intenta
ubicar la mesa por otro medio.

Motivo: un ubigeo identifica un distrito, no un local de votación. El
centroide de un distrito puede estar a kilómetros del colegio donde se
instaló la mesa, y mostrar ese punto le diría al ciudadano algo falso sobre
dónde votó. Sin coordenadas exactas, el visor muestra la zona como texto y
nada más.

No enviar `lat: 0, long: 0` para indicar "sin ubicación": son coordenadas
válidas frente a la costa de África. Si no hay coordenadas, omitir ambos
campos.

### 6.4 Nota sobre el ubigeo

Debe enviarse **como cadena de 6 caracteres**, conservando los ceros a la
izquierda. Enviado como número, `010101` se convierte en `10101` y deja de
identificar al distrito correcto.

Si se envían además `distrito`, `provincia` y `departamento`, se muestran tal
cual llegan. El visor no normaliza ni corrige esos valores, así que conviene
que la escritura sea consistente entre actas.

---

## 7. Requisitos de la firma PAdES

El visor valida la firma del PDF y muestra quién firmó.

### 7.1 Perfil

**Requerido: PAdES-LTA** (o como mínimo PAdES-LT).

Un acta electoral puede impugnarse años después. Con PAdES-B o PAdES-T,
cuando el certificado del firmante caduque nadie podrá validar la firma,
porque la información de revocación no queda embebida. PAdES-LTA la
incorpora junto al sello de tiempo de archivo.

### 7.2 Requisitos

| Requisito | Detalle |
|---|---|
| Sello de tiempo | Obligatorio, de una TSA acreditada. No la hora del equipo firmante |
| Certificado | Emitido por un prestador acreditado |
| Cadena de confianza | Completa y embebida, incluidos los intermedios |
| Revocación | OCSP o CRL embebidos en el documento (DSS) |
| Cobertura | La última firma debe cubrir el documento completo |

### 7.3 Cobertura y revisiones incrementales

El visor muestra qué porción del PDF cubre cada firma. Un PDF admite
revisiones incrementales: se puede firmar en la revisión 2 y anexar
contenido en la 3, y muchos lectores siguen mostrando un tilde verde
engañoso.

**Regla:** después de la última firma no se agrega nada. Si el flujo incluye
varias firmas, la última en aplicarse debe cubrir el documento completo, y el
hash de la sección 3 se calcula después de esa última firma.

### 7.4 Datos personales de los firmantes

Si entre los firmantes hay personas naturales, sus certificados contienen
nombre y número de documento. **El visor es público:** cualquiera que escanee
el QR verá esos datos.

La entidad debe definir, antes de producción, qué se muestra:

- Nombre completo y documento enmascarado (`DNI 4••••755`) — recomendado
- Solo cargo institucional, sin nombre
- Nombre y documento completos

El visor implementará lo que se indique. La decisión corresponde a la entidad
por ser responsable del tratamiento bajo la Ley 29733 de Protección de Datos
Personales.

---

## 8. Degradación por campo faltante

Ningún caso produce un error visible al ciudadano.

| Falta | Efecto |
|---|---|
| `info` | La hoja "Resultados" no aparece. El resto funciona |
| `data` | Sin folio, proceso completo ni ubicación. Solo mesa y código |
| `data.ubicacion` | La sección de ubicación se omite |
| `lat`/`long` | Ubicación en texto, sin coordenadas ni botón |
| `data.folio` | No se muestra el folio |
| `subject` | **Falla visible:** no se muestra el número de mesa |
| `transactionType` | **Falla visible:** no se muestra el proceso |
| Registro pendiente | Pantalla "el acta está en camino", con las etapas |
| PDF ausente en custodia | El acta no se muestra. Se informa como pendiente |

---

## 9. Contrato del código QR

```
https://<dominio-de-la-entidad>/<codigo>
```

Requisitos del `<codigo>`:

- **No debe ser el número de mesa ni derivable de él.** Si lo fuera,
  cualquiera podría enumerar todas las actas del país modificando la URL
- **No debe ser el hash ni el trxid.** Ambos son públicos por otras vías
- Debe ser un identificador opaco, resuelto del lado servidor
- Si se usa un valor cifrado, el descifrado ocurre solo en el servidor

**Impresión.** El QR va impreso en el acta física antes del escrutinio, así
que los códigos deben generarse y asignarse a cada mesa en la fase de
producción del material electoral, no después. Es un plazo logístico, no una
tarea de despliegue.

**Longitud.** Un código cifrado autocontenido no puede ser corto: solo el
sobre criptográfico son 28 bytes, lo que lleva un identificador breve a unos
58 caracteres. La alternativa es un identificador aleatorio con tabla de
resolución del lado servidor: unos 10 caracteres, revocable por acta, a
cambio de una tabla que debe generarse con el material electoral y mantenerse
disponible. Es una decisión de la entidad.

---

## 10. Ejemplo

### 10.1 Petición

```json
{
  "async": "true",
  "evidence": "9f2c7a41e8b3d05c6a1f94be27d8103ca5e6b7f0294d8a3b1c5e07f6a2d94b83",
  "transactionType": "EMC-2026",
  "subject": "Mesa 035253",
  "external_key": "ONPE-EMC-2026-035253",
  "lat": -12.0768,
  "long": -77.0916,
  "info": "eyJ2ZXJzaW9uIjoiMS4wIiwibWVzYSI6IjAzNTI1MyIsIC4uLn0=",
  "data": "eyJ2ZXJzaW9uIjoiMS4wIiwiZm9saW8iOiJBLTAzNTI1My02IiwgLi4ufQ=="
}
```

### 10.2 Generación en Python

```python
import base64, hashlib, json, requests

def register(pdf_path, results, identification, token, lat=None, lng=None):
    # 1. Hash del PDF YA FIRMADO, byte por byte
    with open(pdf_path, "rb") as handle:
        evidence = hashlib.sha256(handle.read()).hexdigest()

    def b64(obj):
        raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        return base64.b64encode(raw.encode("utf-8")).decode("ascii")

    station = identification["mesa"]
    process = identification["proceso"]["codigo"]

    body = {
        "async": "true",
        "evidence": evidence,
        "transactionType": process,
        "subject": f"Mesa {station}",
        "external_key": f"ONPE-{process}-{station}",
        "info": b64(results),
        "data": b64(identification),
    }
    if lat is not None and lng is not None:
        body["lat"], body["long"] = lat, lng

    response = requests.post(
        "https://api.stamping.io/stamp/",
        json=body,
        headers={"X-API-Token": token},   # cabecera, nunca query string
        timeout=30,
    )
    response.raise_for_status()
    return response.json()   # guardar result.trxid y result.proof
```

### 10.3 Consulta

```
GET https://api.stamping.io/stamp/get/?byTrxid=<trxid>
X-API-Token: <token>
```

También admite `?byHash=<evidence>` y `?byExternalKey=<clave>`. La consulta
por `external_key` requiere token; las otras dos son públicas por diseño,
dado que un hash es una huella criptográfica del contenido y no revela nada
por sí mismo.

---

## 11. Lista blanca de origen

La cuenta puede restringirse por IP de origen. Si se activa, toda petición
desde una IP no registrada se rechaza con 403, incluso con token válido.

Deben informarse las IP de salida de los servidores que harán el registro,
incluidas las de contingencia. Se recomienda activarla: el token deja de ser
suficiente por sí solo para registrar actas.

---

## 12. Recursos derivados del acta

El visor no muestra el PDF con un visor embebido: ninguno funciona de forma
confiable en todos los teléfonos. En iOS Safari un PDF dentro de un `iframe`
renderiza solo la primera página; Chrome en Android lo descarga en lugar de
mostrarlo; y una librería como PDF.js supera el megabyte de descarga.

En su lugar se generan dos recursos por acta, una sola vez, al registrarla.

### 12.1 Páginas renderizadas

| Recurso | Formato | Ancho |
|---|---|---|
| Página N, 1x | WebP, calidad 82 | ~900 px |
| Página N, 2x | WebP, calidad 82 | ~1800 px |

Se sirven con `srcset` para que cada teléfono descargue solo lo que su
pantalla usa. El PDF firmado original queda disponible para descargar.

### 12.2 Tarjeta para compartir (Open Graph)

Cuando un ciudadano comparte el enlace, la vista previa la construye la
plataforma a partir de las etiquetas Open Graph. Sin ellas el enlace aparece
como texto pelado.

**Las etiquetas deben emitirse desde el servidor.** Los rastreadores de
WhatsApp, Facebook y X no ejecutan JavaScript.

```html
<meta property="og:title"       content="Acta de la Mesa 035253">
<meta property="og:description" content="Elecciones Municipales 2026. Acta verificada en blockchain.">
<meta property="og:image"       content="https://…/og/035253-1200x630.png">
<meta name="twitter:card"       content="summary_large_image">
```

| Destino | Dimensiones | Peso máximo |
|---|---|---|
| Facebook, X, LinkedIn | 1200 × 630 | 300 KB |
| WhatsApp (vista previa pequeña) | 600 × 600 | 100 KB |

**Advertencia operativa.** WhatsApp cachea las vistas previas de forma
agresiva. Un enlace compartido con la tarjeta mal configurada seguirá
mostrando la versión incorrecta bastante tiempo aunque se corrija. Validar en
el simulacro, no en la jornada.

### 12.3 Qué se comparte

Se comparte **el enlace al visor**, nunca el archivo PDF. Un PDF reenviado
suelto pierde toda la cadena de confianza: quien lo recibe no puede verificar
nada, y adulterar un PDF fuera de contexto es trivial.

El mecanismo usa la API nativa del navegador (`navigator.share`). No se
incorporan servicios de terceros: cargarían JavaScript externo y cookies de
rastreo en una página del Estado, lo que representa un riesgo bajo la Ley
29733 y superficie de ataque innecesaria en un sistema electoral.

---

## 13. Antes de producción

- [ ] Prueba de extremo a extremo con un acta real de simulacro
- [ ] Verificar que el hash enviado coincide con el del PDF descargado desde custodia
- [ ] Confirmar que las firmas salen como PAdES-LTA y validan en un tercero independiente
- [ ] Confirmar que la última firma cubre el 100% del documento
- [ ] Validar los tres cuadres de la sección 5.4 en cada acta antes de enviarla
- [ ] Verificar que los ubigeos viajan como cadena, con ceros a la izquierda
- [ ] Definir política de datos personales de los firmantes (7.4)
- [ ] Registrar las IP de salida en la lista blanca
- [ ] Confirmar la generación y asignación de códigos QR en la producción del material
- [ ] Definir el mecanismo de reintento y la persistencia de `trxid` y `proof`
- [ ] Probar la vista previa del enlace en WhatsApp, Facebook y X
- [ ] Prueba de carga con el volumen esperado de mesas por hora
- [ ] Definir el procedimiento ante un acta que deba corregirse tras registrarse

---

## 14. Puntos abiertos

1. **Actas corregidas.** Si un acta se rectifica después de registrada, su
   hash cambia. ¿Se registra como evidencia nueva que reemplaza a la
   anterior, o se conservan ambas y el visor muestra el historial? Afecta al
   diseño de la pantalla.

2. **Estado del acta en tránsito.** El visor puede mostrar en qué etapa está
   un acta aún no registrada. Requiere que la entidad exponga ese estado. Si
   no lo expone, se mostrarán las etapas como explicación del proceso, sin
   indicar en cuál se encuentra. **No se infiere la etapa**: en contexto
   electoral, una afirmación de estado que después no se sostiene es un costo
   caro para lo barato que sale no hacerla.

3. **Volumen y ventana.** Número estimado de mesas y ritmo de envío
   esperado, para dimensionar el procesamiento asíncrono.

4. **Varias actas por mesa.** Si una mesa produce varias actas (distintas
   categorías en una misma elección), cada una es evidencia independiente y
   necesita su propio QR y su propio `external_key`.
