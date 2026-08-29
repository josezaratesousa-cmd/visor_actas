"""Security headers, checked as configuration rather than as prose.

A policy that exists only in a commit message stops existing the first time
someone rewrites the middleware.
"""

import pytest

from app.main import CSP, SECURITY_HEADERS


def test_scripts_come_only_from_this_origin():
    """No 'unsafe-inline' on scripts: that is what makes a CSP worth having."""
    assert "script-src 'self'" in CSP
    directive = [d for d in CSP.split("; ") if d.startswith("script-src")][0]
    assert "unsafe-inline" not in directive
    assert "unsafe-eval" not in directive


@pytest.mark.parametrize("directive", [
    "default-src 'self'",
    "frame-ancestors 'none'",   # the sheet must not be framed by anyone
    "base-uri 'none'",          # no rewriting where relative URLs resolve
    "object-src 'none'",
    "form-action 'none'",
])
def test_policy_includes(directive):
    assert directive in CSP


def test_only_google_fonts_is_external():
    external = {part for part in CSP.replace(";", " ").split()
                if part.startswith("https://")}
    assert external == {"https://fonts.googleapis.com", "https://fonts.gstatic.com"}


@pytest.mark.parametrize("header,value", [
    ("X-Frame-Options", "DENY"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
])
def test_header_present(header, value):
    assert SECURITY_HEADERS[header] == value


def test_referrer_never_leaks_the_code():
    """The code is in the path, so a referrer would hand it to block explorers."""
    assert SECURITY_HEADERS["Referrer-Policy"] == "no-referrer"
