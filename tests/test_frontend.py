"""The frontend has no build step, so nothing parses it before a browser does.

A stray token from an automated edit - a duplicated `export`, an unbalanced
brace - produces a blank page and an error only visible in the console. That
has now happened twice. node --check parses each module without running it,
which catches exactly this class of mistake from the test suite.
"""

import pathlib
import re
import shutil
import subprocess

import pytest

WEB = pathlib.Path(__file__).resolve().parent.parent / "web"
MODULES = sorted(WEB.glob("js/**/*.js"))

# node --check does not accept ES module syntax, so these two messages mean
# "parsed fine, and it is a module" rather than a real failure.
MODULE_NOISE = ("Cannot use import statement", "Unexpected token 'export'")

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node is not installed")


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_module_parses(path):
    result = subprocess.run(["node", "--check", str(path)],
                            capture_output=True, text=True)
    healthy = result.returncode == 0 or any(n in result.stderr for n in MODULE_NOISE)
    assert healthy, result.stderr.strip()


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_duplicated_keywords(path):
    """`export export`, `const const`: the signature of a bad automated edit."""
    text = path.read_text(encoding="utf-8")
    for keyword in ("export", "const", "function", "return"):
        assert f"{keyword} {keyword} " not in text, f"duplicated '{keyword}'"


def test_every_module_is_reachable_from_app():
    """A module nobody imports is dead weight nobody will notice is broken."""
    imported = set()
    for path in MODULES:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("import ") and "'" in line:
                imported.add(line.split("'")[1].split("/")[-1])
    names = {p.name for p in MODULES} - {"app.js"}
    assert not names - imported, f"never imported: {sorted(names - imported)}"


def test_hostile_payloads_are_neutralised():
    """Si comprometen el servicio de atestación, la respuesta llega envenenada.

    Las cargas de este archivo se registraron de verdad contra el servicio y
    llegaron intactas hasta el navegador: el backend no puede distinguirlas de
    un nombre de organización política legítimo, así que la defensa está en el
    render. Se ejecuta con node para probar el escapado real, no una copia.
    """
    script = pathlib.Path(__file__).parent / "test_xss.js"
    result = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_record_fields_are_always_wrapped():
    """Los campos que vienen del acta nunca llegan crudos a una plantilla.

    Se comprueba lo que importa y no todo lo que parece una interpolación: el
    contenido que un servicio de atestación comprometido podría envenenar.
    Números calculados, constantes del propio módulo y nombres de etiqueta no
    son datos de nadie, y perseguirlos sólo haría que la prueba se ignorara.

    La regla es simple: si una interpolación menciona uno de estos campos,
    tiene que empezar por una función que neutralice.
    """
    # Campos de texto libre: el emisor pone lo que quiera y ninguna validación
    # del backend los restringe, porque el nombre de una organización política
    # o de un colegio no admite una forma fija.
    #
    # Fuera de esta lista quedan a propósito `station` y `evidence`: el modelo
    # los restringe por patrón en la ingesta -alfanumérico el primero, 64
    # hexadecimales el segundo- así que no pueden contener HTML. Esa es la
    # razón por la que pueden ir en un nombre de archivo sin escapar.
    UNTRUSTED = (".name", ".party", ".venue", ".district", ".province",
                 ".folio", ".network", ".authority", ".role", ".signed_at")
    WRAPPERS = ("esc(", "safeUrl(", "encodeURIComponent(", "t(", "fmt(")

    offenders = []
    for path in sorted(WEB.glob("js/views/*.js")):
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            # Sólo las plantillas que terminan en el DOM.
            if "`" not in line and "${" not in line:
                continue
            for expr in re.findall(r"\$\{([^}]+)\}", line):
                value = expr.strip()
                if not any(field in value for field in UNTRUSTED):
                    continue
                if value.startswith(WRAPPERS) or " ? " in value:
                    continue
                offenders.append(f"{path.name}:{number} ${{{value}}}")

    assert not offenders, (
        "campos del acta sin neutralizar: " + ", ".join(offenders))
