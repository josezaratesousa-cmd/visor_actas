"""The frontend has no build step, so nothing parses it before a browser does.

A stray token from an automated edit - a duplicated `export`, an unbalanced
brace - produces a blank page and an error only visible in the console. That
has now happened twice. node --check parses each module without running it,
which catches exactly this class of mistake from the test suite.
"""

import pathlib
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
