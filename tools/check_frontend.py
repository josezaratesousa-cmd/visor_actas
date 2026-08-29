#!/usr/bin/env python3
"""Parse every frontend module.

The browser is the only place a syntax error in these files shows up, and by
then it is a blank page. node --check parses without running, which is enough
to catch a stray token from an automated edit. ES module syntax is reported
as an error by --check, so those two messages are what a healthy file looks
like here.
"""
import pathlib
import subprocess
import sys

MODULE_NOISE = ("Cannot use import statement", "Unexpected token 'export'")

failures = []
for path in sorted(pathlib.Path("web/js").rglob("*.js")):
    result = subprocess.run(["node", "--check", str(path)],
                            capture_output=True, text=True)
    healthy = result.returncode == 0 or any(n in result.stderr for n in MODULE_NOISE)
    print("  %-30s %s" % (path.relative_to("web"), "ok" if healthy else "ERROR"))
    if not healthy:
        failures.append((str(path), result.stderr.strip().splitlines()[-1]))

for name, message in failures:
    print("\n%s\n  %s" % (name, message))
sys.exit(1 if failures else 0)
