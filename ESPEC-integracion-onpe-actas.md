# Especificación de integración — Actas electorales verificables

**Destinatario:** Oficina Nacional de Procesos Electorales (ONPE)
**Servicio:** Stamping.io — registro de evidencia digital en blockchain
**Versión del documento:** 1.0 · Borrador para revisión
**Alcance:** envío de actas electorales al API de Stamping y datos requeridos por el verificador público

---

## 1. Qué hace este documento

Define exactamente qué debe enviar ONPE al API de Stamping para que cada acta electoral quede
registrada y, después, pueda mostrarse en el verificador público que consulta el ciudadano
al escanear el código QR impreso.

El verificador muestra únicamente lo que ONPE haya enviado. Un campo que no se envía no se
muestra: no hay valores por defecto, no se infiere nada y no se completa con otras fuentes.
La sección 8 detalla qué se degrada cuando falta cada campo.

---

## 2. Vista general del flujo

```
  ESCRUTINIO                    ONPE                      STAMPING           CIUDADANO
  ──────────                    ────                      ────────           ─────────
  Acta física  ──▶  Digitaliza y firma (PAdES)
                    Calcula SHA-256 del PDF firmado
                    Sube el PDF a su custodia (S3)
                    POST /api/stamp/  ──────────────▶  Registra evidencia
                                                       Sella en blockchain
                                                       Devuelve trxid
                    Imprime QR con el código  ─────────────────────────────▶  Escanea
                                                                              Ve el acta
                    Backend resuelve código → PDF → hash → trxid              Verifica
                    GET /api/stamp/get/  ───────────▶  Devuelve atestación ──▶ Resultado
```

Punto clave: **el hash es el vínculo**. Todo el sistema depende de que el SHA-256 que ONPE
envía sea el del archivo PDF exacto que después va a ver el ciudadano. Ver sección 3.

---

## 3. Regla crítica: el orden del hash

> **El SHA-256 debe calcularse sobre el PDF final, ya firmado con PAdES, byte por byte,
> tal como quedará almacenado y como se entregará al ciudadano.**

Esta es la causa de falla número uno en integraciones de este tipo. Si el hash se calcula
antes de firmar, o si después de enviarlo se vuelve a guardar el PDF con cualquier
herramienta que lo reescriba, el hash deja de coincidir y **el verificador reportará el acta
como alterada** aunque el contenido sea correcto.

Secuencia obligatoria:

1. Generar el PDF del acta
2. Aplicar **todas** las firmas PAdES (ver sección 7)
3. Cerrar el archivo. No volver a abrirlo ni reescribirlo
4. Calcular `SHA-256` sobre los bytes de ese archivo
5. Subir ese archivo a custodia
6. Enviar el hash a Stamping

Operaciones que rompen el hash y deben evitarse después del paso 3: linealizar, optimizar,
comprimir, agregar metadatos XMP, re-guardar desde cualquier visor, aplicar OCR, rotar
páginas, o agregar una firma adicional.

Si por razones operativas hay que agregar una firma después, el acta debe **volver a
registrarse** como una evidencia nueva, con su nuevo hash.

---

## 4. Endpoint de registro

### 4.1 Petición

```
POST https://api.stamping.io/stamp/
Content-Type: application/json
Authorization: Bearer <token>
```

**Autenticación.** Se acepta cualquiera de estas formas, en este orden de preferencia:

| Forma | Cabecera | Nota |
|---|---|---|
| Bearer | `Authorization: Bearer <token>` | Recomendada |
| Token propio | `X-API-Token: <token>` | Equivalente |
| Basic | `Authorization: Basic base64(customerid:token)` | Soportada |
| En el cuerpo | `"token": "<token>"` | Desaconsejada, ver aviso |

> **Aviso de seguridad.** No enviar el token como parámetro de query string
> (`?token=...`). Los servidores web registran la query en los logs de acceso en texto
> plano. Use siempre cabecera.

**El modo debe ser asíncrono.** El campo `info` solo se acepta con `async: "true"` y
únicamente por cuerpo POST. Enviarlo por GET o con `async: "false"` produce un rechazo 400.

### 4.2 Campos

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `evidence` | string(64) hex | **Sí** | SHA-256 del PDF firmado. Minúsculas, sin prefijo `0x` |
| `async` | `"true"` | **Sí** | Debe ser exactamente la cadena `"true"` |
| `transactionType` | string | **Sí** | Código del proceso electoral. Ver 4.3 |
| `subject` | string | **Sí** | Identificación de la mesa. Formato: `Mesa NNNNNN` |
| `info` | base64 | **Sí** | JSON de resultados codificado en base64. Ver sección 5 |
| `data` | base64 | Recomendado | JSON de identificación y ubicación. Ver sección 6 |
| `lat` | number | Opcional | Latitud decimal. Rango −90 a 90 |
| `long` | number | Opcional | Longitud decimal. Rango −180 a 180 |
| `external_key` | string | Recomendado | Clave propia de ONPE para consultar sin trxid. Ver 4.4 |
| `url` | string | Opcional | URL pública del PDF si existe. Si no, omitir |
| `reference` | string | Opcional | Referencia libre de ONPE |
| `timestamp` | number | Opcional | Epoch en milisegundos del escrutinio. Si se omite, usa la hora de recepción |

Campos que **no** deben enviarse: `server` (obsoleto, se descarta), `hash2` y `hash3`
(reservados para hashes alternativos, sin uso en este caso), `userid` (ignorado).

### 4.3 `transactionType` — código del proceso

Un código corto y estable por proceso electoral. Se muestra como distintivo junto al
número de mesa.

- Máximo 12 caracteres visibles en pantalla; el resto se trunca
- Solo `A–Z`, `0–9` y guion
- Debe ser único e inmutable por proceso, y no reutilizarse entre procesos

Ejemplos: `EMC-2026`, `ERG-2026`, `EG-2026-1V`, `EG-2026-2V`

El nombre completo para mostrar (`Elecciones Municipales 2026`) va en `data.proceso.nombre`,
no aquí.

### 4.4 `external_key` — recomendación operativa

Permite a ONPE consultar un acta con su propia nomenclatura, sin tener que guardar el
`trxid` que devuelve Stamping.

Formato sugerido: `ONPE-<transactionType>-<mesa>` → `ONPE-EMC-2026-035253`

Debe ser único dentro de la cuenta de ONPE. La consulta por `external_key` exige token
válido: no es pública, a diferencia de la consulta por hash.

### 4.5 Respuesta

```json
{
  "code": 200,
  "message": "OK",
  "result": {
    "trxid": "5bd834c40bfb63bfa02b325629908b99ab29bf51",
    "evidence": "9f2c7a41e8b3d05c6a1f94be27d8103ca5e6b7f0294d8a3b1c5e07f6a2d94b83",
    "nonce": "…",
    "timestamp": 1791234567890,
    "proof": {
      "algorithm": "Ed25519",
      "signature": "…",
      "publicKey": "…",
      "signedFields": ["evidence", "trxid", "timestamp"]
    }
  }
}
```

`trxid` es siempre `sha1(evidence)`, por lo que ONPE puede calcularlo por su cuenta sin
depender de la respuesta.

**Sobre `proof`:** es un comprobante firmado de que Stamping recibió esa evidencia en ese
momento. **No se almacena del lado de Stamping.** ONPE debe guardarlo. Es la prueba que
permite demostrar el envío ante una discrepancia futura del tipo "envié el acta y nunca se
registró". Recomendamos persistirlo junto al registro del acta.

### 4.6 Códigos de error

| Código | Significado | Acción de ONPE |
|---|---|---|
| 200 | Registrado | Guardar `trxid` y `proof` |
| 200 + `duplicated` | Ese hash ya estaba registrado | Verificar si es reenvío legítimo |
| 303 | `async` ausente o inválido | Corregir a `"true"` |
| 400 | `evidence` ausente, o `info` mal enviado | Revisar sección 4.2 |
| 401 | Token ausente | Revisar cabecera |
| 402 | Token inválido | Contactar a Stamping |
| 403 | Origen o IP no autorizados | Registrar la IP de salida en la lista blanca |
| 500 | Error interno | Reintentar. Si persiste, citar la referencia `err_<id>` que devuelve |

**Duplicados.** Por defecto, un hash ya registrado no se vuelve a registrar. Como dos actas
distintas nunca producen el mismo hash, un duplicado significa reenvío del mismo archivo.
Si el flujo de ONPE requiere permitir reenvíos, debe solicitarse la exención para su cuenta.

**Reintentos.** Use retroceso exponencial. El registro es idempotente por hash: reenviar el
mismo `evidence` no crea un registro duplicado.

---

## 5. Campo `info` — resultados del escrutinio

`info` es un JSON codificado en **base64 estándar** (RFC 4648, con relleno `=`). Es el
contenido que el verificador muestra en la hoja "Resultados".

### 5.1 Esquema

```json
{
  "version": "1.0",
  "mesa": "035253",
  "electores_habiles": 287,
  "votos_emitidos": 241,
  "opciones": [
    { "orden": 1, "codigo": "MRU", "nombre": "Movimiento Regional Unidad", "votos": 86, "tipo": "organizacion" },
    { "orden": 2, "codigo": "ACL", "nombre": "Alianza Cívica del Litoral",  "votos": 62, "tipo": "organizacion" },
    { "orden": 3, "codigo": "FVI", "nombre": "Frente Vecinal Independiente","votos": 44, "tipo": "organizacion" },
    { "orden": 4, "codigo": "PPL", "nombre": "Partido del Progreso Local",  "votos": 31, "tipo": "organizacion" },
    { "nombre": "Votos en blanco",  "votos": 11, "tipo": "blanco" },
    { "nombre": "Votos nulos",      "votos": 7,  "tipo": "nulo" },
    { "nombre": "Votos impugnados", "votos": 0,  "tipo": "impugnado" }
  ]
}
```

### 5.2 Reglas

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `version` | string | Sí | `"1.0"` para esta especificación |
| `mesa` | string | Sí | Debe coincidir con el número en `subject` |
| `electores_habiles` | entero ≥ 0 | Sí | |
| `votos_emitidos` | entero ≥ 0 | Sí | No puede superar `electores_habiles` |
| `opciones` | array | Sí | Mínimo un elemento |
| `opciones[].nombre` | string | Sí | Nombre a mostrar |
| `opciones[].votos` | entero ≥ 0 | Sí | |
| `opciones[].tipo` | enum | Sí | `organizacion` \| `blanco` \| `nulo` \| `impugnado` |
| `opciones[].orden` | entero | Solo si `tipo=organizacion` | Posición en la cédula |
| `opciones[].codigo` | string | Opcional | Código de la organización política |

**Consistencia.** La suma de `opciones[].votos` debe ser igual a `votos_emitidos`. El
verificador calcula los porcentajes sobre `votos_emitidos`; si la suma no cuadra, los
porcentajes no sumarán 100% y quedará visible para cualquier ciudadano.

**Presentación.** Las opciones de tipo `organizacion` se muestran numeradas y con barra en
color; `blanco`, `nulo` e `impugnado` se muestran sin numeración y en gris, para que no
compitan visualmente con las organizaciones políticas. Las opciones se muestran en el orden
en que llegan en el array: ONPE decide el criterio (por votos o por número de cédula).

**Tamaño.** Mantener el JSON por debajo de 32 KB antes de codificar.

---

## 6. Campo `data` — identificación y ubicación

También base64 de un JSON. Es lo que identifica la mesa más allá de su número, y de donde
sale el bloque "Dónde se instaló la mesa".

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
    "distrito": "San Miguel",
    "provincia": "Lima",
    "departamento": "Lima",
    "ubigeo": "150132"
  },
  "acta": {
    "tipo": "escrutinio",
    "paginas": 2
  }
}
```

### 6.2 Reglas

| Campo | Obligatorio | Regla |
|---|---|---|
| `mesa` | Sí | Debe coincidir con `info.mesa` y con `subject` |
| `folio` | Recomendado | Folio impreso en el acta física |
| `proceso.codigo` | Sí | Debe coincidir con `transactionType` |
| `proceso.nombre` | Sí | Nombre completo del proceso, tal como se muestra |
| `proceso.tipo` | Opcional | Tipo de elección |
| `ubicacion` | Recomendado | Objeto completo o ausente. Ver 6.3 |
| `ubicacion.local` | Recomendado | Nombre del local de votación |
| `ubigeo` | Recomendado | Código de ubigeo de 6 dígitos, como cadena, conservando ceros a la izquierda |
| `acta.paginas` | Recomendado | Número de páginas del PDF |

### 6.3 Ubicación

Todo lo relativo a la ubicación viaja dentro de `data.ubicacion`. Si `data` no la trae, la
sección "Dónde se instaló la mesa" no se muestra: no aparece un espacio vacío ni un mensaje
de "sin datos".

Las coordenadas son el único campo que va fuera de `data`: en `lat` y `long`, en el nivel
superior de la petición.

| Lo que se envía | Qué muestra el verificador |
|---|---|
| `ubicacion` + `lat`/`long` | Local, zona y coordenadas, con botón "Abrir en Mapas" |
| `ubicacion` sin coordenadas | Local y zona en texto. Sin botón |
| Solo `ubigeo` dentro de `ubicacion` | El ubigeo como texto de zona |
| Sin `ubicacion` | La sección no aparece |

El botón "Abrir en Mapas" abre la aplicación de mapas del propio teléfono en el punto
indicado. Aparece **únicamente** cuando hay coordenadas: sin ellas no se intenta ubicar la
mesa por otro medio.

Motivo: un ubigeo identifica un distrito, no un local de votación. El centroide de un
distrito puede estar a kilómetros del colegio donde se instaló la mesa, y mostrar ese punto
le diría al ciudadano algo falso sobre dónde votó. Sin coordenadas exactas, el verificador
muestra la zona como texto y nada más.

No enviar `lat: 0, long: 0` para indicar "sin ubicación": esas son coordenadas válidas y el
verificador mostraría un punto frente a la costa de África. Si no hay coordenadas, omitir
ambos campos.

### 6.4 Nota sobre el ubigeo

El ubigeo debe enviarse **como cadena de 6 caracteres**, conservando los ceros a la
izquierda. Enviado como número, `010101` se convierte en `10101` y deja de identificar al
distrito correcto.

Si ONPE envía además `distrito`, `provincia` y `departamento`, se muestran tal cual llegan.
Se recomienda que la escritura sea consistente entre actas, ya que el verificador no
normaliza ni corrige estos valores.


## 7. Requisitos de la firma PAdES

El verificador valida la firma del PDF y muestra quién firmó. Para que eso funcione:

### 7.1 Perfil de firma

**Requerido: PAdES-LTA** (o como mínimo PAdES-LT).

Un acta electoral puede impugnarse años después del proceso. Con perfiles PAdES-B o
PAdES-T, cuando el certificado del firmante caduque nadie podrá validar la firma, porque la
información de revocación no queda embebida en el documento. PAdES-LTA incorpora esa
información y el sello de tiempo de archivo, y mantiene la firma verificable en el largo
plazo.

### 7.2 Requisitos

| Requisito | Detalle |
|---|---|
| Sello de tiempo | Obligatorio, de una TSA acreditada. No usar la hora del equipo firmante |
| Certificado | Emitido por un prestador acreditado (RENIEC o un QTSP reconocido) |
| Cadena de confianza | Completa y embebida, incluidos los certificados intermedios |
| Información de revocación | OCSP o CRL embebidos en el documento (DSS) |
| Cobertura | La última firma debe cubrir el documento completo. Ver 7.3 |

### 7.3 Cobertura y revisiones incrementales

El verificador muestra qué porción del PDF cubre cada firma. Un PDF admite revisiones
incrementales: es posible firmar en la revisión 2 y anexar contenido en la revisión 3, y
muchos lectores siguen mostrando un tilde verde engañoso.

**Regla:** después de la última firma no se agrega nada. Si el flujo de ONPE incluye varias
firmas (miembros de mesa, luego ONPE al digitalizar), la última en aplicarse debe cubrir el
documento completo, y el hash de la sección 3 se calcula después de esa última firma.

### 7.4 Datos personales de los firmantes

Si entre los firmantes hay personas naturales, sus certificados contienen nombre y número de
documento. El verificador es **público**: cualquiera que escanee el QR verá esos datos.

ONPE debe definir, antes de la puesta en producción, qué se muestra:

- Nombre completo y documento enmascarado (`DNI 4••••755`) — recomendado
- Solo cargo institucional, sin nombre
- Nombre y documento completos

El verificador implementará lo que ONPE indique. Esta decisión corresponde a ONPE por ser
la responsable del tratamiento bajo la Ley 29733 de Protección de Datos Personales.

---

## 8. Degradación por campo faltante

Qué muestra el verificador cuando falta cada dato. Ningún caso produce un error visible al
ciudadano.

| Falta | Efecto en el verificador |
|---|---|
| `info` | La hoja "Resultados" no aparece. El resto funciona normalmente |
| `data` | No se muestran folio, proceso completo ni ubicación. Solo mesa y proceso por código |
| `data.ubicacion` | La sección "Dónde se instaló la mesa" se omite |
| `lat`/`long` | Ubicación en texto, sin coordenadas ni botón "Abrir en Mapas" |
| `data.folio` | No se muestra el folio |
| `subject` | **Falla visible:** el encabezado no puede mostrar el número de mesa |
| `transactionType` | **Falla visible:** no se muestra el proceso electoral |
| Registro en blockchain aún pendiente | Pantalla "Su acta todavía está en camino", con las etapas del proceso |
| PDF ausente en custodia | El acta no se muestra. Se informa como pendiente |

---

## 9. Contrato del código QR

El QR impreso en el acta apunta a una URL bajo dominio de ONPE:

```
https://<dominio-onpe>/<codigo>
```

Requisitos del `<codigo>`:

- **No debe ser el número de mesa en claro ni derivable de él.** Si lo fuera, cualquiera
  podría enumerar todas las actas del país modificando la URL
- **No debe ser el hash ni el trxid.** Ambos son públicos y consultables por otras vías
- Debe ser un identificador opaco, resuelto del lado servidor a la mesa correspondiente
- Longitud sugerida: 8 a 12 caracteres alfanuméricos, para que el QR se imprima pequeño y
  legible aun con la calidad de impresión de campo
- Si se usa un valor cifrado, el descifrado ocurre solo en el servidor

El backend resuelve: `código → mesa → PDF en custodia → SHA-256 → trxid → consulta a Stamping`.

**Impresión.** El QR va impreso en el acta física antes del escrutinio, por lo que el código
debe generarse y asignarse a cada mesa en la fase de producción del material electoral, no
después.

---

## 10. Ejemplo completo

### 10.1 Petición

```http
POST /stamp/ HTTP/1.1
Host: api.stamping.io
Content-Type: application/json
Authorization: Bearer <token>
```

```json
{
  "async": "true",
  "evidence": "9f2c7a41e8b3d05c6a1f94be27d8103ca5e6b7f0294d8a3b1c5e07f6a2d94b83",
  "transactionType": "EMC-2026",
  "subject": "Mesa 035253",
  "external_key": "ONPE-EMC-2026-035253",
  "lat": -12.0768,
  "long": -77.0916,
  "timestamp": 1791234567890,
  "info": "eyJ2ZXJzaW9uIjoiMS4wIiwibWVzYSI6IjAzNTI1MyIsIC4uLn0=",
  "data": "eyJ2ZXJzaW9uIjoiMS4wIiwiZm9saW8iOiJBLTAzNTI1My02IiwgLi4ufQ=="
}
```

### 10.2 Generación en Python

```python
import base64, hashlib, json, requests

def registrar_acta(ruta_pdf: str, resultados: dict, identificacion: dict,
                   token: str, lat=None, lng=None) -> dict:
    # 1. Hash del PDF YA FIRMADO, byte por byte
    with open(ruta_pdf, "rb") as f:
        evidence = hashlib.sha256(f.read()).hexdigest()

    def b64(obj: dict) -> str:
        crudo = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        return base64.b64encode(crudo.encode("utf-8")).decode("ascii")

    cuerpo = {
        "async": "true",
        "evidence": evidence,
        "transactionType": identificacion["proceso"]["codigo"],
        "subject": f"Mesa {identificacion['mesa']}",
        "external_key": f"ONPE-{identificacion['proceso']['codigo']}-{identificacion['mesa']}",
        "info": b64(resultados),
        "data": b64(identificacion),
    }
    if lat is not None and lng is not None:
        cuerpo["lat"], cuerpo["long"] = lat, lng

    r = requests.post(
        "https://api.stamping.io/stamp/",
        json=cuerpo,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()   # guardar result.trxid y result.proof
```

### 10.3 Consulta posterior

```http
GET /stamp/get/?byTrxid=5bd834c40bfb63bfa02b325629908b99ab29bf51 HTTP/1.1
Host: api.stamping.io
X-API-Token: <token>
```

También admite `?byHash=<evidence>` y `?byExternalKey=<clave>`. La consulta por
`external_key` requiere token; las otras dos son públicas por diseño, dado que un hash es
una huella criptográfica del contenido y no revela nada por sí misma.

---

## 11. Lista blanca de origen

La cuenta de ONPE puede restringirse por IP de origen. Si se activa, toda petición desde una
IP no registrada será rechazada con 403, incluso con token válido.

ONPE debe informar las IP de salida de los servidores que harán el registro, incluidas las
de contingencia. Se recomienda activarla: el token deja de ser suficiente por sí solo para
registrar actas.

---

## 12. Antes de producción

Lista de comprobación para la puesta en marcha.

- [ ] Prueba de extremo a extremo con un acta real de simulacro
- [ ] Verificar que el hash enviado coincide con el del PDF descargado desde custodia
- [ ] Confirmar que las firmas salen como PAdES-LTA y que validan en un tercero independiente
- [ ] Confirmar que la última firma cubre el 100% del documento
- [ ] Validar que `info.opciones` suma exactamente `votos_emitidos`
- [ ] Definir política de datos personales de los firmantes (sección 7.4)
- [ ] Verificar que los ubigeos viajan como cadena, con ceros a la izquierda
- [ ] Probar la vista previa del enlace en WhatsApp, Facebook y X antes de la jornada
- [ ] Registrar las IP de salida en la lista blanca
- [ ] Confirmar la generación y asignación de códigos QR en la producción del material
- [ ] Definir el mecanismo de reintento y la persistencia de `trxid` y `proof`
- [ ] Prueba de carga con el volumen esperado de mesas por hora
- [ ] Definir el procedimiento ante un acta que deba corregirse tras haber sido registrada

---

## 13. Recursos derivados del acta

El verificador no muestra el PDF con un visor embebido: ningún visor de PDF funciona de
forma confiable en todos los teléfonos. En iOS Safari un PDF dentro de un `iframe` renderiza
solo la primera página; Chrome en Android lo descarga en lugar de mostrarlo; y una librería
como PDF.js supera el megabyte de descarga, lo que la vuelve inviable en la gama baja de
Android con conexión móvil rural.

En su lugar, el backend genera dos recursos derivados por acta, una sola vez, en el momento
del registro. Ambos se guardan junto al PDF en la custodia y se sirven cacheados.

### 13.1 Páginas renderizadas

| Recurso | Formato | Tamaño | Uso |
|---|---|---|---|
| Página N, 1x | WebP, calidad 82 | 900 px de ancho | Lectura en pantalla |
| Página N, 2x | WebP, calidad 82 | 1800 px de ancho | Pantallas de alta densidad |

Se sirven con `srcset` para que cada teléfono descargue solo la resolución que necesita. El
PDF firmado original queda disponible en los botones "Abrir el PDF" y "Descargar", para
quien necesite el archivo con validez legal: personeros, observadores, periodistas.

Ventaja adicional: la imagen carga instantáneamente y no requiere JavaScript, por lo que el
acta se ve incluso si algo falla en el resto de la página.

### 13.2 Tarjeta para compartir (Open Graph)

Cuando un ciudadano comparte el enlace por WhatsApp o redes sociales, la vista previa la
construye la plataforma a partir de las etiquetas Open Graph del HTML. Sin ellas, el enlace
aparece como texto pelado y prácticamente nadie lo abre.

**Las etiquetas deben emitirse desde el servidor.** Los rastreadores de WhatsApp, Facebook y
X no ejecutan JavaScript: etiquetas insertadas por el navegador no las verán nunca.

Etiquetas requeridas:

```html
<meta property="og:title"       content="Acta de la Mesa 035253 — ONPE">
<meta property="og:description" content="Elecciones Municipales 2026. Acta verificada en blockchain.">
<meta property="og:image"       content="https://…/og/035253-1200x630.png">
<meta property="og:url"         content="https://…/v/8fk3nq2">
<meta property="og:type"        content="website">
<meta name="twitter:card"       content="summary_large_image">
```

La imagen `og:image` se genera por acta e incluye el número de mesa, el proceso electoral y
el distintivo de verificada. Requiere dos tamaños:

| Destino | Dimensiones | Peso máximo |
|---|---|---|
| Facebook, X, LinkedIn | 1200 × 630 px | 300 KB |
| WhatsApp (vista previa pequeña) | 600 × 600 px | 100 KB |

**Advertencia operativa.** WhatsApp almacena en caché las vistas previas de forma agresiva.
Un enlace compartido con la tarjeta mal configurada seguirá mostrando la versión incorrecta
durante bastante tiempo, aunque se corrija en el servidor. Esto debe validarse en el
simulacro, no en la jornada electoral.

### 13.3 Qué se comparte

Se comparte **el enlace al verificador**, nunca el archivo PDF.

Un PDF reenviado suelto por WhatsApp pierde toda la cadena de confianza: quien lo recibe no
puede verificar nada, y adulterar un PDF que circula fuera de contexto es trivial. Con el
enlace, cada reenvío lleva al receptor al verificador, donde puede comprobar por sí mismo la
autenticidad del acta.

El mecanismo de compartir usa la API nativa del navegador (`navigator.share`), que abre la
bandeja del sistema operativo con las aplicaciones que el ciudadano tenga instaladas. No se
incorporan servicios de terceros como AddToAny o ShareThis: cargarían JavaScript externo y
cookies de rastreo en una página del Estado, lo que representa un riesgo de protección de
datos bajo la Ley 29733 y una superficie de ataque innecesaria en un sistema electoral.

---

## 14. Puntos abiertos

Requieren decisión conjunta antes de cerrar la especificación.

1. **Actas corregidas.** Si un acta se rectifica después de registrada, su hash cambia.
   ¿Se registra como evidencia nueva que reemplaza a la anterior, o se conservan ambas y el
   verificador muestra el historial? Afecta al diseño de la pantalla.

2. **Estado del acta en tránsito.** El verificador puede mostrar en qué etapa está un acta
   aún no registrada (recepción, digitalización, firma, sellado). Requiere que ONPE exponga
   ese estado. Si no lo expone, se mostrarán las etapas como explicación del proceso, sin
   indicar en cuál se encuentra.

3. **Volumen y ventana.** Número estimado de mesas y ritmo de envío esperado, para
   dimensionar el procesamiento asíncrono y el anclaje en blockchain.

4. **Actas de procesos distintos en la misma jornada.** Si una mesa produce varias actas
   (por ejemplo, distintas categorías en una misma elección), cada una es una evidencia
   independiente y necesita su propio QR y su propio `external_key`.
