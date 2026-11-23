# Offline workstation demo

Extract the approved DEMO ZIP → open `demo/index.html` via `file://`.

Requirements: relative classic scripts, preloaded `data.js` (`window.POLICY_DEMO_DATA`), no `fetch()`/CDN/ES modules. Vendor JS must be copied into `demo/`. Missing vendors → not interactive-demo-ready.

Modes: **full-fidelity by default** (`include_policy_excerpts_in_demo=True` → `data.js` embeds parsed text for `index.html`) vs optional redacted. Mode is recorded in `DEMO_MANIFEST.json` and the demo header.
