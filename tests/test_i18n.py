"""The dictionaries are load-bearing, and they broke twice from the shell.

A malformed byte after the closing brace is invisible in a diff and takes
the whole interface down: the fetch fails, every key falls back to its own
name, and the page reports itself unavailable. Neither the Python tests nor
a curl against the API noticed. These checks do.
"""

import json
import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "web"
LOCALES = ["es", "en"]

# Sections whose keys are looked up through t(). Anything else matching the
# dotted shape - a CSS class, a filename - is not a translation key.
SECTIONS = {"app", "verify", "results", "share", "document",
            "pending", "errors", "state", "anchors"}


def load(locale: str) -> dict:
    return json.loads((WEB / "i18n" / f"{locale}.json").read_text(encoding="utf-8"))


def flatten(data: dict, prefix: str = "") -> set[str]:
    keys = set()
    for key, value in data.items():
        dotted = f"{prefix}.{key}" if prefix else key
        keys |= flatten(value, dotted) if isinstance(value, dict) else {dotted}
    return keys


@pytest.mark.parametrize("locale", LOCALES)
def test_dictionary_is_valid_json(locale):
    """Catches trailing bytes after the closing brace."""
    text = (WEB / "i18n" / f"{locale}.json").read_text(encoding="utf-8")
    json.loads(text)
    assert text.rstrip().endswith("}"), "there is content after the root object"


@pytest.mark.parametrize("locale", LOCALES)
def test_no_empty_strings(locale):
    empty = [k for k, v in _pairs(load(locale)) if not v.strip()]
    assert not empty, f"empty translations: {empty}"


def test_locales_have_the_same_keys():
    spanish, english = flatten(load("es")), flatten(load("en"))
    assert not spanish - english, f"missing from en: {sorted(spanish - english)}"
    assert not english - spanish, f"missing from es: {sorted(english - spanish)}"


def test_every_key_used_by_the_code_exists():
    available = flatten(load("es"))
    used = set()
    for path in list((WEB / "js").rglob("*.js")) + [WEB / "index.html"]:
        text = path.read_text(encoding="utf-8")
        used |= set(re.findall(r"t\(['\"]([a-z_]+\.[a-z_]+)['\"]", text))
        used |= set(re.findall(r"'([a-z_]+\.[a-z_]+)'", text))
        used |= set(re.findall(r'data-i18n(?:-label)?="([^"]+)"', text))

    wanted = {k for k in used if k.split(".")[0] in SECTIONS}
    missing = sorted(wanted - available)
    assert not missing, f"used by the code but not translated: {missing}"


def test_spanish_keeps_its_accents():
    """Written from a shell, non-ASCII has been lost more than once."""
    suspicious = re.compile(
        r"\b(codigo|todavia|aqui|numero|informacion|verificacion|ubicacion|"
        r"organizacion|participacion|validos|paginas|electronica|"
        r"digitalizacion|recepcion|direccion|camara|aparecera|publico|"
        r"criptografica|telefono|pagina|cual)\b", re.IGNORECASE)
    offenders = [f"{k}: {v}" for k, v in _pairs(load("es")) if suspicious.search(v)]
    assert not offenders, f"Spanish strings missing accents: {offenders}"


def _pairs(data: dict, prefix: str = ""):
    """Yield every translatable string. Some entries are lists of strings."""
    for key, value in data.items():
        dotted = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            yield from _pairs(value, dotted)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, str):
                    yield f"{dotted}[{index}]", item
        elif isinstance(value, str):
            yield dotted, value
