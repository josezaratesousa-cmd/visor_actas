# Especificación de integración — Actas electorales verificables

**Destinatario:** Oficina Nacional de Procesos Electorales (ONPE)
**Servicio:** Stamping.io — registro de evidencia digital en blockchain
**Versión del documento:** 1.1 · Revisado contra el código fuente de la API y del verificador
**Alcance:** envío de actas electorales al API de Stamping y datos requeridos por el verificador público

---

## 1. Qué hace este documento

Define exactamente qué debe enviar ONPE al API de Stamping para que cada acta electoral quede
registrada y, después, pueda mostrarse en el verificador público que consulta el ciudadano
al escanear el código QR impreso.

**Esta versión (1.1) fue verificada línea por línea contra el código real de la API de
Stamping y del verificador** — no solo redactada a partir del diseño. Donde ambos sistemas
difieren de lo que un borrador anterior asumía, este documento describe lo que
**efectivamente ocurre hoy**, con avisos explícitos (`>` con negrita) marcando puntos
pendientes de implementación o comportamientos que conviene conocer aunque no sean errores.

El verificador muestra lo que ONPE envía, con dos matices importantes: (1) varios campos se
aceptan y se guardan pero **no se presentan en ninguna pantalla actual** — se marcan como
tales en las secciones 5 y 6, en vez de prometerse como visibles; y (2) un par de campos sí
tienen un valor por defecto cuando faltan — no todo lo que falta produce un vacío, algunos
casos degradan a un valor genérico (`transactionType` ausente se convierte en el literal
`"DEFAULT"`, por ejemplo). La sección 8 detalla, campo por campo, qué pasa exactamente
cuando algo falta.

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

> **Dos niveles de "obligatorio".** Stamping (la API que recibe este POST) y el
> verificador (lo que ve el ciudadano) no exigen lo mismo. Stamping solo rechaza la
> petición si falta `evidence` o si `async` no es `"true"`/`"false"` — todo lo demás lo
> acepta aunque venga vacío, sin devolver ningún error. El verificador, en cambio, necesita
> varios de esos campos para poder mostrar algo coherente; si faltan, el acta se registra
> igual (Stamping responde `200 OK`) pero el verificador la muestra incompleta o con datos
> genéricos, sin ningún aviso en el momento del registro. La columna "Si falta" distingue
> ambos casos.

| Campo | Tipo | Obligatorio para el visor | Si falta |
|---|---|---|---|
| `evidence` | string(64) hex | **Sí** | La API rechaza la petición con 400. No es negociable |
| `async` | `"true"`/`"false"` | **Sí**, y debe ser `"true"` | Solo `"true"` habilita `info`; con `"false"` la API rechaza `info` con 400. La API en general también acepta `"false"`, pero para este flujo siempre debe ir `"true"` |
| `transactionType` | string | **Sí** | La API **no** rechaza la petición: si llega vacío, lo reemplaza en silencio por el literal `"DEFAULT"`. El verificador mostraría "DEFAULT" en vez del proceso, y mesas de procesos distintos podrían mezclarse bajo ese mismo código |
| `subject` | string | **Sí** | La API **no** rechaza la petición: si llega vacío, el verificador no tiene número de mesa que mostrar en el encabezado (se degrada al `mesa` de `data`/`info`, si vino) |
| `info` | base64 | **Sí** | La hoja "Resultados" no aparece. Ver sección 5 |
| `data` | base64 | **Sí** (para todo salvo resultados) | Sin `data`, el verificador solo tiene el número de mesa (por `subject`) y el código de proceso (por `transactionType`, sin su nombre completo); no hay ubicación, ni nombre del proceso. Ver sección 6 |
| `lat` | number | Recomendado | Sin coordenadas, la ubicación se muestra solo como texto, sin botón "Abrir en Mapas". Rango −90 a 90 |
| `long` | number | Recomendado | Igual que `lat`. Rango −180 a 180 |
| `external_key` | string | Recomendado (operativo, no visual) | No afecta lo que ve el ciudadano; solo la forma en que ONPE puede consultar el acta más adelante sin guardar el `trxid`. Ver 4.4 |
| `url` | string | No usado por el visor | El verificador no lo lee. Si no se tiene, omitir |
| `reference` | string | No usado por el visor | Campo libre de ONPE, el verificador no lo muestra |
| `timestamp` | number | No usado por el visor hoy | Si se omite, Stamping usa la hora de recepción |

Campos que **no** deben enviarse: `server` (obsoleto, se descarta), `hash2` y `hash3`
(reservados para hashes alternativos, sin uso en este caso), `userid` (ignorado).

**Nota sobre `evidence`.** Stamping solo rechaza el hash si supera 64 caracteres o si
contiene algo no hexadecimal — **no** exige que tenga exactamente 64 caracteres, y acepta
(y descarta) un prefijo `0x` si viene. Un hash truncado por error en el pipeline de ONPE
pasaría esta validación igual, así que el "hex(64), sin `0x`" de la tabla sigue siendo la
regla que ONPE debe seguir — solo que Stamping no la hace cumplir por ustedes.

### 4.3 `transactionType` — código del proceso

Un código corto y estable por proceso electoral. Se muestra como distintivo junto al
número de mesa.

- Máximo 12 caracteres visibles en pantalla; el resto se trunca
- Solo `A–Z`, `0–9` y guion
- Debe ser único e inmutable por proceso, y no reutilizarse entre procesos

**Estas tres reglas son convención, no algo que Stamping valide.** La API acepta cualquier
cadena en `transactionType` — cualquier longitud, cualquier carácter — así que nada del
lado del servidor va a avisar si ONPE se desvía de este formato. Seguirlo importa porque el
verificador y el panel de administración asumen esta forma para mostrarlo bien.

**Detalle importante:** Stamping convierte `transactionType` a **mayúsculas
automáticamente** antes de guardarlo (`emc-2026` se guarda como `EMC-2026`). Como
`proceso.codigo` (dentro de `data`) debe coincidir con `transactionType`, y `data` no pasa
por esa conversión, conviene que ONPE genere ambos valores ya en mayúsculas desde origen —
si `data.proceso.codigo` se genera en minúsculas y `transactionType` no, van a dejar de
coincidir sin que nadie lo note hasta compararlos.

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

`info` es un JSON codificado en **base64 estándar** (RFC 4648, con relleno `=`).

> **Esta sección describe el contrato del visor, no solo el de la API.** Stamping acepta
> el campo `info` como texto libre y no valida su contenido; es el **verificador** el que
> decodifica este JSON y exige exactamente esta estructura. Si no calza, el verificador
> descarta el JSON completo (ver "Qué pasa si no calza" al final de esta sección) — sin que
> Stamping haya devuelto ningún error al momento del registro.

### 5.1 Esquema

Los valores del ejemplo son ilustrativos. **La estructura no lo es:** el verificador lee
exactamente estos campos, con estos nombres, y no infiere ninguno a partir de otro ni a
partir del PDF.

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
    { "nombre": "Movimiento Regional Unidad",   "partido": "M.R.U. + Alianza",  "votos": 86 },
    { "nombre": "Alianza Cívica del Litoral",   "partido": "ACL",               "votos": 62 },
    { "nombre": "Frente Vecinal Independiente", "partido": "Frente Vecinal",    "votos": 44 },
    { "nombre": "Partido del Progreso Local",   "partido": "P.P.L.",            "votos": 31 }
  ]
}
```

**Cambio importante frente a versiones anteriores de este documento:** ya no existe un
`tipo` que distinga organización/blanco/nulo/impugnado dentro de `opciones`. `opciones[]`
contiene **únicamente organizaciones políticas**; blancos y nulos van en sus propios campos
al mismo nivel que `mesa`. **No existe un campo para votos impugnados** — si ese concepto
aplica al proceso, es un punto abierto a resolver con el equipo del visor antes de
producción (ver sección 14).

### 5.2 Qué muestra el verificador, campo por campo

| Campo | Obligatorio | Dónde aparece | Si falta o no calza |
|---|---|---|---|
| `mesa` | Sí | Encabezado (respaldo si falta en `subject`) | — |
| `electores_habiles` | Sí | Denominador de la tarjeta "Participación" | — |
| `votantes` | Sí | Tarjeta "Cantidad de votantes", numerador de participación | — |
| `votos_validos` | Sí | Tarjeta "Votos válidos", denominador del % de cada organización | — |
| `votos_nulos` | Sí | Tarjeta "Votos nulos" | — |
| `votos_blancos` | Sí | Tarjeta "Votos en blanco" | — |
| `opciones[].nombre` | Sí | Título de cada barra | — |
| `opciones[].votos` | Sí | Cifra a la derecha de la barra, y su ancho | — |
| `opciones[].partido` | Recomendado | Línea inferior, junto al porcentaje | Si falta, esa línea no aparece para esa opción |
| `opciones[].color` | Opcional, hex `#RRGGBB` | Color de la barra | Si falta, el verificador asigna un color de su propia paleta por posición |
| `opciones[].orden` | No usado hoy | — | El verificador **no reordena** las barras: se muestran en el orden en que llegan en el array. `orden` se acepta y se guarda, pero no tiene ningún efecto visual todavía |
| `opciones[].codigo` | No usado hoy | — | Se acepta pero **no se muestra en ningún lado** de la pantalla actual |

### 5.3 Reglas de consistencia

El verificador no corrige las cifras; las muestra como llegan, pero **rechaza el JSON
completo** si no cuadran estas tres sumas (ver 5.4 sobre qué implica el rechazo):

```
suma(opciones[].votos)                      = votos_validos
votos_validos + votos_nulos + votos_blancos = votantes
votantes                                    ≤ electores_habiles
```

Enviar `0` explícito en `votos_nulos`/`votos_blancos` si no hubo — no omitir el campo.

**Los dos denominadores.** Es el error más frecuente al armar este JSON:

- **Porcentaje de cada organización** = `votos / votos_validos` (no sobre `votantes`:
  nulos y blancos no se atribuyen a ninguna opción, y contarlos en el denominador
  subestimaría a todas por igual)
- **Participación** = `votantes / electores_habiles`

### 5.4 Qué pasa si el JSON no calza

Esto es distinto de lo que documenta la sección 8 para campos ausentes. Si `info` llega
pero el JSON **no tiene esta forma exacta** — falta un campo obligatorio, un tipo no
coincide, o alguna de las tres sumas de 5.3 no cuadra — el verificador descarta el bloque
completo: la hoja "Resultados" no aparece, igual que si `info` nunca se hubiera enviado.
No hay una versión parcial ni un aviso de error visible para el ciudadano. Stamping, por su
parte, ya devolvió `200 OK` al momento del registro — el problema solo se nota después, al
abrir el verificador.

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

### 6.2 Reglas y qué se presenta hoy en pantalla

| Campo | Obligatorio | Se muestra en el verificador | Regla |
|---|---|---|---|
| `mesa` | Sí | Sí — identifica la mesa en toda la pantalla | Debe coincidir con `info.mesa` y con `subject` |
| `proceso.codigo` | Sí | Sí — distintivo junto al número de mesa | Debe coincidir con `transactionType` |
| `proceso.nombre` | Sí | Sí — descripción del proceso | Nombre completo, tal como se muestra |
| `ubicacion.local` | Recomendado | Sí — título del bloque de ubicación | Nombre del local de votación |
| `ubicacion.distrito` | Recomendado | Sí — línea de zona | |
| `ubicacion.provincia` | Recomendado | Sí — línea de zona | |
| `ubicacion.ubigeo` | Recomendado | Sí — se usa si falta local/distrito/provincia | 6 dígitos, como cadena, con ceros a la izquierda |
| `folio` | — | **No.** El verificador lo decodifica pero no lo pinta en ningún lado hoy | Enviarlo igual si ONPE lo necesita para su propio control interno — no le cuesta nada a la petición, solo no aparece en pantalla |
| `proceso.tipo` | — | **No.** Se decodifica pero no se muestra | Igual que `folio`: inofensivo enviarlo, pero no esperar verlo reflejado |
| `ubicacion.direccion` | — | **No.** Se decodifica pero no se muestra | Idem |
| `ubicacion.departamento` | — | **No.** Se decodifica pero no se muestra | Idem |
| `acta.tipo` / `acta.paginas` | — | **No, y además es redundante.** El número de páginas que muestra el verificador se calcula directamente del PDF real en custodia, nunca de este campo | Se puede omitir todo el objeto `acta` sin ningún efecto |

Los campos marcados "No" no rompen nada si se envían — el verificador los decodifica sin
error y simplemente no los usa. Pero tampoco vale la pena que ONPE invierta tiempo en
poblarlos pensando que van a aparecer en el verificador: hoy no aparecen. Si en algún
momento se agrega esa presentación, se actualiza esta tabla.

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

**Advertencia adicional, distinta a la anterior.** Si `lat`/`long` llegan **fuera de
rango** (por ejemplo, invertidos: `lat: -77.09` en vez de `long: -77.09`), Stamping los
reemplaza en silencio por `(0, 0)` — sin devolver ningún error de validación. Es decir, el
mismo escenario "punto en el Golfo de Guinea" que este documento pide evitar a propósito
puede darse igual por un error de formato, no de intención, y Stamping no lo va a avisar. El
verificador ya neutraliza ese caso específico de `(0,0)` tratándolo como "sin coordenadas",
así que el ciudadano no ve el pin mal puesto — pero ONPE no va a recibir ninguna señal de
que sus coordenadas no llegaron. Vale la pena validar el rango del lado de ONPE antes de
enviarlas.

### 6.4 Nota sobre el ubigeo

El ubigeo debe enviarse **como cadena de 6 caracteres**, conservando los ceros a la
izquierda. Enviado como número, `010101` se convierte en `10101` y deja de identificar al
distrito correcto.

Si ONPE envía además `distrito` y `provincia`, se muestran tal cual llegan (junto con
`local` y `ubigeo` — ver la tabla de 6.2 para el resto de campos de `ubicacion`, que se
aceptan pero no se presentan hoy). Se recomienda que la escritura sea consistente entre
actas, ya que el verificador no normaliza ni corrige estos valores.


## 7. Requisitos de la firma PAdES

El verificador valida la firma del PDF y muestra quién firmó. Para que eso funcione:

> **Estado actual de esta funcionalidad: pendiente.** Hoy el verificador solo detecta si el
> PDF trae una firma digital presente (`unsigned` / `unverified`) — todavía no valida la
> cadena de confianza PAdES ni extrae nombre o documento de los firmantes; la interfaz ya
> tiene el espacio listo para mostrar esa lista, pero llega siempre vacía. Los requisitos
> de esta sección (7.1 a 7.3) siguen siendo correctos y hay que exigírselos a ONPE desde
> ya — son requisitos sobre el PDF que firma ONPE, no sobre nada que dependa del visor —
> pero la política de datos personales de 7.4 aplica recién cuando se implemente la
> extracción de firmantes. No es un campo de la API: sale de leer el certificado dentro
> del propio PDF, así que no hay nada adicional que ONPE deba enviar para esto.

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

> **Orden real de fallback.** El verificador no combina `data` con `subject`/
> `transactionType` — cuando `data` llega y decodifica bien, **manda por completo** sobre
> el número de mesa y el proceso: usa `data.mesa` y `data.proceso.{codigo,nombre}`, e
> ignora `subject`/`transactionType` para eso. Estos dos últimos solo entran en juego como
> respaldo si `data` falta o no decodifica. Por eso las filas de `subject` y
> `transactionType` de abajo solo aplican cuando `data` **también** está ausente o
> corrupto — con `data` presente y válido, da igual lo que traigan.

| Falta | Efecto en el verificador |
|---|---|
| `info`, o `info` mal formado (ver 5.4) | La hoja "Resultados" no aparece. El resto funciona normalmente |
| `data`, o `data` mal formado | Mesa y proceso se leen de `subject`/`transactionType` en su lugar (ver nota arriba). Sin ubicación, sin nombre completo del proceso |
| `data.ubicacion` | La sección "Dónde se instaló la mesa" se omite |
| `lat`/`long` | Ubicación en texto, sin coordenadas ni botón "Abrir en Mapas" |
| `data.folio` | Nada — el verificador no muestra este campo tenga o no tenga valor (ver 6.2) |
| `subject`, con `data` presente y válido | Sin efecto: el número de mesa sale de `data.mesa` |
| `subject`, con `data` **también** ausente | **Falla visible:** el encabezado no puede mostrar el número de mesa |
| `transactionType`, con `data` presente y válido | Sin efecto: el proceso sale de `data.proceso` |
| `transactionType`, con `data` **también** ausente | **Falla visible:** no se muestra el proceso electoral |
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

> **Punto abierto, no solo sugerencia.** El propio código del verificador señala esta
> tensión: un código cifrado autocontenido (AES-256-GCM, sin tabla de búsqueda) no puede
> ser corto — el sobre criptográfico por sí solo agrega ~28 bytes, así que un identificador
> cifrado termina en unos **58 caracteres**, muy por encima de los 8-12 sugeridos aquí. La
> alternativa que sí cumple la longitud sugerida es un identificador aleatorio opaco con
> tabla de resolución del lado del servidor (~10 caracteres, revocable por acta), a cambio
> de mantener esa tabla generada junto con el material electoral. Cuál de las dos usar es
> una decisión de ONPE, no un detalle técnico — hay que cerrarla antes de fijar el tamaño
> del QR en el diseño del material impreso.

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

En su lugar, el backend genera dos recursos derivados por acta. Corrección sobre el
momento: **no se generan al registrar el acta**, sino la primera vez que alguien la
consulta — el backend renderiza la página bajo demanda y guarda el resultado en un caché
en disco, indexado por el hash del PDF, para que la segunda consulta en adelante sea
inmediata. Para ONPE esto es transparente (no requiere ninguna acción ni campo adicional),
pero conviene no prometerle al equipo de campo que la imagen "ya existe" apenas se
registra el acta: existe recién tras la primera visita.

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

> **Estado actual: parcialmente implementado.** El verificador ya emite `og:title`,
> `og:description`, `og:url`, `og:type` y `twitter:card` por acta. **`og:image` todavía no
> existe** — no hay generador de la imagen 1200×630/600×600 descrita más abajo. Hoy, quien
> comparte el enlace ve una tarjeta de texto sin miniatura. Esta subsección describe el
> diseño objetivo, no algo que ya esté funcionando; no depende de ningún dato que envíe
> ONPE, es trabajo pendiente del lado del visor.

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
