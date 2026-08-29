#!/usr/bin/env python3
"""Verificación independiente de un acta, sin creerle nada al servicio.

Cada paso se apoya en algo que Stamping no controla: IPFS es direccionable
por contenido, el árbol de Merkle es aritmética comprobable, y los nodos de
Rollux y LACChain responden a cualquiera. Si el servicio de atestación
estuviera comprometido e inventara un hash de transacción, el paso 4 lo
delataría: el nodo diría que esa transacción no existe.

    python -m tools.verify_chain <ruta-del-pdf> [--trxid <id>]
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
import os
import urllib.request
from pathlib import Path

STAMPING = "https://api.stamping.io"
IPFS_GATEWAY = "https://ipfs.stamping.io/"


def nodes() -> dict[str, str]:
    """Nodos a consultar, tomados de la configuración.

    Deliberadamente sin valores por defecto para LACChain: la entidad debe
    declarar el suyo. Un nodo por defecto del proveedor haría que la
    verificación pareciera independiente sin serlo.
    """
    from app.config import get_settings
    settings = get_settings()
    return {
        "Rollux": settings.rollux_rpc,
        "LACChain": settings.lacchain_rpc,
    }

OK, BAD, INFO = "  [ok]  ", "  [FALLA]", "  [--]  "


def get(url: str, token: str = "", timeout: int = 25):
    """Consulta al servicio.

    Con token la búsqueda se acota a esa cuenta. Importa: el identificador de
    transacción sale del hash del archivo, así que otra cuenta que selle el
    mismo documento genera una fila con el mismo identificador, y la consulta
    anónima devuelve la registrada más tarde. Sin token se verifica lo que
    haya, que puede no ser lo que se busca.
    """
    headers = {"Accept": "application/json", "User-Agent": "visor-actas/1.0"}
    if token:
        headers["X-API-Token"] = token
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def rpc(node: str, method: str, params: list):
    body = json.dumps({"jsonrpc": "2.0", "method": method,
                       "params": params, "id": 1}).encode()
    # Sin User-Agent, algunos RPC públicos responden 403.
    request = urllib.request.Request(node, body, {
        "Content-Type": "application/json",
        "User-Agent": "visor-actas/1.0",
    })
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response).get("result")


def merkle_root(leaves: list[str]) -> str:
    """Reconstruye la raíz igual que el motor de anclaje.

    Concatena las cadenas hexadecimales -no los bytes- y, cuando un nivel
    tiene cantidad impar, duplica el último consigo mismo. Ese detalle
    importa: rellenar con cadena vacía en su lugar produce una raíz distinta
    y haría que un acta legítima se reportara como no verificada.
    """
    level = list(leaves)
    while len(level) > 1:
        level = [hashlib.sha256((level[i] + (level[i + 1] if i + 1 < len(level)
                                             else level[i])).encode()).hexdigest()
                 for i in range(0, len(level), 2)]
    return level[0]


def readable(hex_input: str) -> str:
    """Extrae el texto ASCII embebido en el input de una transacción."""
    body = hex_input[10:]
    out = []
    for word in (body[i:i + 64] for i in range(0, len(body), 64)):
        try:
            text = bytes.fromhex(word).decode("utf-8").strip("\x00")
            if text.isprintable() and len(text) > 3:
                out.append(text)
        except Exception:
            pass
    return "".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--trxid", default=None)
    parser.add_argument("--issuer", default=None,
                        help="userId que debe haber registrado el acta")
    args = parser.parse_args()

    fallos = 0

    # ── 1. El documento que tengo es el que se selló ────────────────────
    evidence = hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    trxid = args.trxid or hashlib.sha1(evidence.encode()).hexdigest()  # noqa: S324
    print("1. Huella del documento")
    print(f"{INFO}sha256 {evidence}")
    print(f"{INFO}trxid  {trxid}")

    token = os.environ.get("STAMPING_TOKEN", "")
    if not token:
        print(f"{INFO}sin STAMPING_TOKEN: la consulta es anónima y puede "
              f"devolver el registro de otra cuenta")
    record = get(f"{STAMPING}/stamp/get/?byTrxid={trxid}", token).get("result")
    if not record:
        print(f"{BAD}el servicio no conoce esa huella")
        return 1
    sellada = record["integrity"]["evidence"]
    if sellada == evidence:
        print(f"{OK}coincide con la evidencia registrada")
    else:
        print(f"{BAD}la evidencia registrada es otra: {sellada}")
        fallos += 1

    # ── 1b. Quién la registró ───────────────────────────────────────────
    #
    # Los pasos criptográficos prueban que el documento fue sellado y cuándo,
    # pero no por quién. Un tercero que selle el mismo archivo con su propia
    # cuenta produce un registro que supera todas las demás comprobaciones:
    # es correcto, y no es de la entidad electoral.
    propietario = record.get("ownership", {})
    print(f"\n1b. Emisor")
    print(f"{INFO}{propietario.get('name')} ({str(propietario.get('userId'))[:16]}…)")
    if args.issuer:
        if str(propietario.get("userId", "")).lower() == args.issuer.lower():
            print(f"{OK}registrada por la entidad esperada")
        else:
            print(f"{BAD}registrada por OTRA cuenta, no por la esperada")
            fallos += 1
    else:
        print(f"{INFO}sin --issuer no se comprueba de quién es")

    # ── 2. El acta está en el bloque publicado en IPFS ──────────────────
    cid = record.get("block", {}).get("ipfs")
    print(f"\n2. Bloque publicado en IPFS")
    if not cid:
        print(f"{INFO}el bloque aún no tiene CID: anclaje en curso")
        return fallos
    print(f"{INFO}CID {cid}")
    bloque = get(f"{IPFS_GATEWAY}{cid}")
    hojas = [a["evidence"] for a in bloque["attestations"]]
    if evidence in hojas:
        print(f"{OK}el acta figura entre las {len(hojas)} del bloque")
    else:
        print(f"{BAD}el acta NO está en el bloque publicado")
        fallos += 1

    # ── 3. Las hojas producen la raíz declarada ─────────────────────────
    print(f"\n3. Árbol de Merkle")
    raiz_declarada = bloque["block"]["hashblock"]
    raiz_calculada = merkle_root(hojas)
    print(f"{INFO}declarada {raiz_declarada}")
    print(f"{INFO}calculada {raiz_calculada}")
    if raiz_declarada == raiz_calculada:
        print(f"{OK}la raíz se reconstruye desde las hojas")
    else:
        print(f"{BAD}la raíz no coincide: el bloque fue alterado")
        fallos += 1

    # ── 4, 5 y 6. La raíz está escrita en una cadena pública ────────────
    sin_comprobar = []
    for nombre, nodo in nodes().items():
        clave = "lacchain" if nombre == "LACChain" else "rollux"
        tx = record.get("networks", {}).get("mainnet", {}).get(clave)
        print(f"\n4. Anclaje en {nombre}")
        if not tx or tx in ("0x", "", "0"):
            print(f"{INFO}sin anclaje todavía")
            continue
        if not nodo:
            # Callar esto sería lo peor que puede hacer un verificador: dar
            # por buena una cadena que nadie miró.
            print(f"{BAD}NO VERIFICADO: no hay nodo configurado para {nombre}")
            sin_comprobar.append(nombre)
            continue
        try:
            datos = rpc(nodo, "eth_getTransactionByHash", [tx])
        except Exception as exc:
            print(f"{BAD}NO VERIFICADO: el nodo no respondió ({exc})")
            sin_comprobar.append(nombre)
            continue
        if not datos:
            print(f"{BAD}el nodo no conoce esa transacción: es inventada")
            fallos += 1
            continue

        contenido = readable(datos["input"])
        if raiz_calculada in contenido.lower() or cid in contenido:
            print(f"{OK}la transacción contiene la raíz o el CID")
        else:
            print(f"{BAD}la transacción no menciona este bloque")
            fallos += 1

        recibo = rpc(nodo, "eth_getTransactionReceipt", [tx])
        if recibo and recibo.get("status") == "0x1":
            print(f"{OK}minada correctamente en el bloque "
                  f"{int(recibo['blockNumber'], 16)}")
        else:
            print(f"{BAD}la transacción no llegó a confirmarse")
            fallos += 1

        cabecera = rpc(nodo, "eth_getBlockByNumber", [datos["blockNumber"], False])
        momento = datetime.datetime.utcfromtimestamp(int(cabecera["timestamp"], 16))
        print(f"{OK}existía antes de "
              f"{momento.strftime('%Y-%m-%d %H:%M:%S')} UTC")

    print()
    if fallos:
        print(f"  {fallos} comprobación(es) FALLARON")
    elif sin_comprobar:
        # Distinto de "verificada": nadie comprobó esos anclajes, y decir que
        # todo está bien porque lo que se miró estaba bien es exactamente el
        # tipo de afirmación que este programa existe para no hacer.
        print(f"  VERIFICADA PARCIALMENTE: sin comprobar "
              f"{', '.join(sin_comprobar)}")
    else:
        print("  VERIFICADA: ningún paso depende de creerle al servicio")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
