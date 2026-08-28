#!/usr/bin/env python3
"""Generate synthetic tally sheets for testing.

Everything here is invented: the polling station, the political
organisations, the members of the table. Nothing comes from a real election.

That is not squeamishness. A real tally sheet carries the names and national
identity numbers of the table members inside its PAdES signature, and this
repository is public. Synthetic fixtures are the only ones that can be
committed.

Produces two files:

    valid.pdf     registered as-is; hash matches, viewer reports authentic
    altered.pdf   a copy with a page appended AFTER the hash was taken, so
                  the viewer reports it as altered

Usage:
    python -m tools.make_fixtures [--out tests/fixtures]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import fitz

STATION = "035253"
PROCESS = {"codigo": "EMC-2026", "nombre": "Elecciones Municipales 2026",
           "tipo": "Concejo municipal distrital"}

RESULTS = {
    "version": "1.0",
    "mesa": STATION,
    "electores_habiles": 287,
    "votantes": 241,
    "votos_validos": 223,
    "votos_nulos": 7,
    "votos_blancos": 11,
    "opciones": [
        {"orden": 1, "codigo": "MRU", "nombre": "Movimiento Regional Unidad",
         "partido": "M.R.U. + Alianza", "votos": 86},
        {"orden": 2, "codigo": "ACL", "nombre": "Alianza Civica del Litoral",
         "partido": "ACL", "votos": 62},
        {"orden": 3, "codigo": "FVI", "nombre": "Frente Vecinal Independiente",
         "partido": "Frente Vecinal", "votos": 44},
        {"orden": 4, "codigo": "PPL", "nombre": "Partido del Progreso Local",
         "partido": "P.P.L.", "votos": 31},
    ],
}

DATA = {
    "version": "1.0",
    "mesa": STATION,
    "folio": f"A-{STATION}-6",
    "proceso": PROCESS,
    "ubicacion": {
        "local": "I.E. 1120 Pedro A. Labarthe",
        "direccion": "Av. Precursores 1120",
        "distrito": "San Miguel", "provincia": "Lima",
        "departamento": "Lima", "ubigeo": "150132",
    },
    "acta": {"tipo": "escrutinio", "paginas": 1},
}

INK = (0.08, 0.09, 0.11)
RED = (0.55, 0.07, 0.10)
GREY = (0.46, 0.49, 0.52)


def draw_sheet(page: fitz.Page) -> None:
    width = page.rect.width
    margin = 48
    y = 60

    page.insert_text((margin, y), "ONPE", fontname="hebo", fontsize=20, color=RED)
    page.insert_text((margin, y + 15), "OFICINA NACIONAL DE PROCESOS ELECTORALES",
                     fontname="helv", fontsize=6.5, color=GREY)
    page.insert_text((width - margin - 90, y), f"A-{STATION}-6",
                     fontname="cobo", fontsize=11, color=INK)
    page.insert_text((width - margin - 90, y + 12), "FOLIO",
                     fontname="helv", fontsize=6, color=GREY)
    page.draw_line((margin, y + 26), (width - margin, y + 26), color=INK, width=1.4)

    y += 56
    page.insert_text((margin, y), "ACTA DE ESCRUTINIO — DOCUMENTO SINTETICO DE PRUEBA",
                     fontname="hebo", fontsize=10, color=INK)

    y += 26
    fields = [("MESA", STATION), ("UBIGEO", "150132"),
              ("HABILES", "287"), ("VOTARON", "241")]
    box = (width - 2 * margin) / 4
    for index, (label, value) in enumerate(fields):
        x = margin + index * box
        page.draw_rect(fitz.Rect(x, y, x + box, y + 34), color=GREY, width=0.6)
        page.insert_text((x + 6, y + 12), label, fontname="helv", fontsize=6, color=GREY)
        page.insert_text((x + 6, y + 26), value, fontname="cobo", fontsize=10, color=INK)

    y += 58
    page.insert_text((margin, y), "ORGANIZACION POLITICA", fontname="hebo",
                     fontsize=7, color=INK)
    page.insert_text((width - margin - 40, y), "VOTOS", fontname="hebo",
                     fontsize=7, color=INK)
    y += 6
    page.draw_line((margin, y), (width - margin, y), color=INK, width=0.8)

    rows = [(o["nombre"], o["votos"]) for o in RESULTS["opciones"]]
    rows += [("Votos en blanco", RESULTS["votos_blancos"]),
             ("Votos nulos", RESULTS["votos_nulos"])]
    for name, votes in rows:
        y += 18
        page.insert_text((margin, y), name, fontname="helv", fontsize=8, color=INK)
        page.insert_text((width - margin - 36, y), str(votes),
                         fontname="cobo", fontsize=9, color=INK)
        page.draw_line((margin, y + 4), (width - margin, y + 4), color=GREY, width=0.3)

    y += 60
    slot = (width - 2 * margin) / 3
    for index, role in enumerate(["PRESIDENTE", "SECRETARIO", "TERCER MIEMBRO"]):
        x = margin + index * slot
        page.draw_line((x, y), (x + slot - 16, y), color=INK, width=0.8)
        page.insert_text((x, y + 10), role, fontname="helv", fontsize=6, color=GREY)

    page.insert_text((margin, page.rect.height - 40),
                     "Documento sintetico generado por tools/make_fixtures.py. "
                     "Datos ficticios, sin relacion con ningun proceso electoral real.",
                     fontname="helv", fontsize=6, color=GREY)


def build(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    document = fitz.open()
    draw_sheet(document.new_page(width=595, height=842))
    valid = out_dir / "valid.pdf"
    document.save(str(valid), garbage=4, deflate=True)
    document.close()

    # The altered copy: content appended AFTER the hash was taken. This is
    # the failure the viewer has to catch, and the reason the specification
    # insists on hashing the final file.
    tampered = fitz.open(str(valid))
    extra = tampered.new_page(width=595, height=842)
    extra.insert_text((48, 80), "PAGINA AGREGADA DESPUES DE FIRMAR",
                      fontname="hebo", fontsize=13, color=RED)
    extra.insert_text((48, 104),
                      "Esta pagina no existia cuando se calculo la huella.",
                      fontname="helv", fontsize=9, color=INK)
    altered = out_dir / "altered.pdf"
    tampered.save(str(altered), incremental=False, garbage=0, deflate=True)
    tampered.close()

    (out_dir / "results.json").write_text(
        json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "data.json").write_text(
        json.dumps(DATA, ensure_ascii=False, indent=2), encoding="utf-8")

    for path in (valid, altered):
        print(f"{path}  {path.stat().st_size} bytes")
    print(f"{out_dir / 'results.json'}\n{out_dir / 'data.json'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=Path("tests/fixtures"))
    build(parser.parse_args().out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
