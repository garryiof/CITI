"""Validate offline demo package for file:// safety."""

from __future__ import annotations

import json
import re
from pathlib import Path

from policy_knowledge.validation.schema_validator import ValidationReport

CDN_RE = re.compile(r"https?://", re.I)
FETCH_RE = re.compile(r"\bfetch\s*\(")


def validate_offline_demo(demo_dir: Path) -> ValidationReport:
    demo_dir = Path(demo_dir)
    errors: list[str] = []
    warnings: list[str] = []

    for required in ("index.html", "app.js", "styles.css", "data.js", "DEMO_MANIFEST.json"):
        if not (demo_dir / required).exists():
            errors.append(f"missing {required}")

    if errors:
        return ValidationReport(ok=False, errors=errors, warnings=warnings)

    html = (demo_dir / "index.html").read_text(encoding="utf-8")
    app = (demo_dir / "app.js").read_text(encoding="utf-8")
    if CDN_RE.search(html) or CDN_RE.search(app):
        errors.append("CDN or absolute http(s) reference found")
    if FETCH_RE.search(app):
        errors.append("fetch() found in app.js")
    if "type=\"module\"" in html:
        errors.append("ES module script found")

    # Relative asset refs only
    for match in re.findall(r"(?:src|href)=\"([^\"]+)\"", html):
        if match.startswith("/") or "://" in match:
            errors.append(f"non-relative asset ref: {match}")

    manifest = json.loads((demo_dir / "DEMO_MANIFEST.json").read_text(encoding="utf-8"))
    if not manifest.get("interactive_ready", False):
        warnings.append("interactive demo not ready (vendor assets missing or stubs)")
    if manifest.get("browser_test") == "BROWSER_TEST_NOT_RUN":
        warnings.append("BROWSER_TEST_NOT_RUN")

    data = (demo_dir / "data.js").read_text(encoding="utf-8")
    if "POLICY_DEMO_DATA" not in data:
        errors.append("data.js missing POLICY_DEMO_DATA")
    if "role_relevance" not in data:
        warnings.append("data.js missing role_relevance (Pass F not embedded)")

    return ValidationReport(ok=not errors, errors=errors, warnings=warnings)
