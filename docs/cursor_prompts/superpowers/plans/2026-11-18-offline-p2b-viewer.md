# Offline policies2BPMN Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package a file://-openable HTML workspace that matches the policies2BPMN viewer UX, built from the existing notebook without modifying `policies2BPMN/`.

**Architecture:** A notebook-invoked Python builder reads `policies2BPMN/outputs` and copies UMD bpmn-js assets from the reference `viewer/node_modules/bpmn-js` tree into a generated pack (`index.html`, `app.js`, `styles.css`, `data.js`, `vendor/`, `policy_source.html`). The browser app is classic JS only: no `fetch`, no ES modules, no CDN. Layout/review persistence uses `localStorage` plus Download buttons.

**Tech Stack:** Python 3, Jupyter notebook, vanilla JS, bpmn-js UMD Modeler, CSS mirrored from policies2BPMN theme/layout.

**Spec:** `docs/superpowers/specs/2026-11-18-offline-p2b-viewer-design.md`

## Global Constraints

- Do **not** modify anything under `policies2BPMN/` (read-only reference).
- Offline pack must work under `file://` (relative classic scripts; embed workflow data in `data.js`).
- Do not replace or break the existing tabbed `demo/` POC path in the pipeline.
- Persistence: `localStorage` + file Download only (no write API).
- Prefer Modeler UMD for drag/reset; if vendor missing, fail the builder with a clear message (do not silently ship a broken canvas).

## Review Focus

- Opening `index.html` via `file://` with no local server still loads all workflows from `data.js`.
- Missing `bpmn-js` UMD source fails the builder loudly instead of writing a non-interactive pack.
- Policy evidence links open embedded `policy_source.html#anchor` without network.
- Review status / saved layout survive reload via `localStorage` and can be downloaded as `.json`/`.bpmn`.
- `PTP-POLICY` overview phases, duplicates, and analysis panels behave for the embedded BlackRock outputs.

---

### Task 1: Offline pack builder (Python)

**Files:**
- Create: `notebooks/build_offline_p2b.py`
- Test: `tests/test_build_offline_p2b.py`

**Interfaces:**
- Consumes: `policies2BPMN/outputs/index.json`, `*.json`, `*.bpmn`, `policy_source.html`; UMD files under `policies2BPMN/viewer/node_modules/bpmn-js/`
- Produces: `build_offline_p2b(repo_root: Path, out_dir: Path) -> Path` writing a complete offline pack and returning `out_dir`

- [ ] **Step 1: Write failing tests**

```python
def test_build_offline_p2b_writes_required_files(tmp_path, repo_root):
    out = build_offline_p2b(repo_root, tmp_path / "offline_p2b")
    for name in ("index.html", "app.js", "styles.css", "data.js", "policy_source.html"):
        assert (out / name).is_file()
    assert (out / "vendor" / "bpmn-modeler.production.min.js").is_file()
    data = (out / "data.js").read_text(encoding="utf-8")
    assert "window.P2B_DATA" in data
    assert "PTP-PRECLEAR" in data or "PTP-POLICY" in data

def test_build_offline_p2b_fails_without_modeler_umd(tmp_path, monkeypatch, repo_root):
    # force missing vendor path → raises FileNotFoundError with helpful message
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_build_offline_p2b.py -v`
Expected: FAIL (module/function missing)

- [ ] **Step 3: Implement `build_offline_p2b`**

Write pack skeleton from templates living beside the builder (`notebooks/offline_p2b_assets/{index.html,app.js,styles.css}`), embed outputs into `data.js` as:

```js
window.P2B_DATA = {
  "generated_at": "...",
  "index": [/* WorkflowIndexItem */],
  "workflows": { "<id>": { "json": {...}, "bpmn": "<xml>" } },
  "policy_source_html": "<html>...</html>"
};
```

Also write `policy_source.html` as a sibling file for anchor links. Copy UMD + CSS:

- `bpmn-modeler.production.min.js`
- `assets/bpmn-js.css`, `assets/diagram-js.css`, bpmn-font CSS/fonts as needed

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_build_offline_p2b.py -v`
Expected: PASS

- [ ] **Step 5: Commit** (only if user asks)

---

### Task 2: Offline viewer UI (classic JS)

**Files:**
- Create: `notebooks/offline_p2b_assets/index.html`
- Create: `notebooks/offline_p2b_assets/app.js`
- Create: `notebooks/offline_p2b_assets/styles.css`
- Test: extend `tests/test_build_offline_p2b.py` with smoke assertions on asset strings; manual file:// check listed below

**Interfaces:**
- Consumes: `window.P2B_DATA`, global `BpmnJS` from UMD Modeler
- Produces: interactive UI matching policies2BPMN panels (rail / diagram / detail)

- [ ] **Step 1: Add smoke assertions**

```python
def test_offline_assets_reference_p2b_data_and_no_fetch(repo_root):
    app = (repo_root / "notebooks/offline_p2b_assets/app.js").read_text(encoding="utf-8")
    assert "P2B_DATA" in app
    assert "fetch(" not in app
```

- [ ] **Step 2: Implement assets**

Port the reference UX into vanilla JS/CSS:

- Top bar: brand, role select, workflow count
- Left rail: search + workflow list
- Center: diagram heading, review pill, zoom/fit, legend/duplicates/analysis toggles, Reset, Save layout (download + localStorage), overview bar for `PTP-POLICY`
- Right: element detail for step/gateway/event/phase + policy evidence links to `policy_source.html#anchor`
- Markers: inferred / recommended classes on canvas elements when possible
- `localStorage` keys: `p2b-user-role`, `p2b-review-<id>`, `p2b-layout-<id>`

Visual tokens: copy CSS variables from `policies2BPMN/viewer/src/theme.css` + layout patterns from `styles.css` (system/fontstack fallbacks acceptable if font files are heavy).

- [ ] **Step 3: Rebuild pack and spot-check**

Run builder into `notebooks/offline_p2b/` (gitignored or under policy_runs). Open `index.html` via file://. Confirm: switch workflows, click a step, open legend/duplicates/analysis, change role, set review status, rearrange + Reset + Save download.

- [ ] **Step 4: Commit** (only if user asks)

---

### Task 3: Wire notebook

**Files:**
- Modify: `notebooks/00_RUN_ONE_POLICY.ipynb`

**Interfaces:**
- Consumes: `build_offline_p2b`
- Produces: printed absolute path to `index.html` after pipeline (or as its own section)

- [ ] **Step 1: Add markdown + code cells** after the existing run/archive section (new section **3b** or **5**): explain that this builds the policies2BPMN-style offline pack from `policies2BPMN/outputs` without modifying that folder.

- [ ] **Step 2: Cell body**

```python
from build_offline_p2b import build_offline_p2b  # or importlib from notebooks/

out = build_offline_p2b(ROOT, ROOT / "notebooks" / "offline_p2b")
print("Open offline viewer:", (out / "index.html").resolve().as_uri())
```

Ensure `sys.path` includes `notebooks/` (or import via path). Do not call into `policies2BPMN` Python converter.

- [ ] **Step 3: Run the new cell; confirm URI prints and files exist**

- [ ] **Step 4: Commit** (only if user asks)

---

## Execution handoff

After implementation, verify:

1. `pytest tests/test_build_offline_p2b.py -v` passes
2. `notebooks/offline_p2b/index.html` opens under `file://` with workflows interactive
3. `policies2BPMN/` git status shows no modifications
