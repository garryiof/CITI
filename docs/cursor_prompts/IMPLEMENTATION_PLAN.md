# Policy Intelligence POC — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` (recommended for this tightly coupled pipeline) or `superpowers:subagent-driven-development`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a JupyterHub-only, one-policy POC that turns a DOCX/PDF/HTML policy into a canonical knowledge model, OKF v0.2, BPMN 2.0+DI, governance matrices, and a portable `file://` offline HTML demo with FULL/DEMO ZIP archives.

**Architecture:** Canonical `PolicyKnowledge` is the single source of truth. Ingestion yields provenance-preserving `SourceBlock`s; a GuardRail-backed (or mock) multi-pass extractor fills typed entities and edges; deterministic exporters derive OKF, BPMN, matrices, and precomputed viewer `data.js`. All artifacts land in one isolated `policy_runs/<POLICY_ID>/<RUN_ID>/` tree; archiving is the final notebook-callable step.

**Tech Stack:** Python 3.11; Pydantic; python-docx; pypdf (+ optional pdfminer); BeautifulSoup4/lxml; Jinja2; NetworkX; pytest/unittest; stdlib `zipfile`/`hashlib`; offline viewer = plain HTML/CSS/JS + bundled bpmn-js Navigated Viewer + Cytoscape.js UMD (no npm/React/Node).

**Spec:** `Cursor_Policy_Intelligence_Master_Prompt.md` (v1.2)

---

## Global Constraints

- JupyterHub is the **only** Python execution environment; sole required UX is `notebooks/00_RUN_ONE_POLICY.ipynb` calling importable `.py` modules.
- No `python -m`, CLI, shell/PowerShell, `!` magics, `%pip`, subprocess installs, or local HTTP server as part of the product path.
- No new package installs; use verified available libs only (`pandas`, `pydantic`, `docx`, `bs4`, `lxml`, `jinja2`, `networkx`, `pytest`, `IPython`, `pypdf`/`PyPDF2`/`pdfminer`).
- LLM access via provider switch: Hub = Citi GuardRail; home full check = optional OpenAI (`llm.provider=openai`); default/tests = mock. Never invent GuardRail paths. Do **not** claim live GuardRail/OpenAI connectivity when using mock. Never commit API keys.
- Do not invent GuardRail import paths, `build_messages`, model IDs, or endpoints; discover or abstract.
- No confidential real policies, SOEIDs, certs, or endpoints in tracked files; develop with synthetic fixtures.
- Canonical model first; OKF/BPMN/matrices/viewer are derived views — never independently regenerated facts.
- Offline demo must open via `file://` with relative classic scripts, preloaded `data.js`, no `fetch()`/CDN/ES modules.
- Vendor JS must be present under `src/policy_knowledge/viewer/vendor/` and **copied** into each run’s `demo/`; missing vendors → not interactive-demo-ready (honest degraded label allowed).
- Archives last; exclude `archive/` from FULL ZIP; transfer gated by explicit `TransferPolicy`.
- Do not install additional dependencies or call external services during development (per user instruction).

## Workspace Inspection Result (Phase 0 baseline)

| Item | Finding |
|---|---|
| Repo contents | Only `Cursor_Policy_Intelligence_Master_Prompt.md` present — **greenfield** |
| Existing Python / GuardRail helpers | **Not found** — implement abstract `LLMAdapter` + `MockLLMAdapter`; document live bootstrap checklist |
| `build_messages` helper | **Not found** — provide thin local helper that formats system/user messages; swap if org helper appears |
| Vendor bpmn-js / Cytoscape builds | **Not found** — ship placeholder vendor directory + readiness checks; bundle stubs or skip interactive claim until approved bytes supplied |
| Real policy document | **Not supplied** — use `tests/fixtures/synthetic_policy.*` for all development |

**Implication:** Implement full skeleton and mock vertical slice end-to-end. GuardRail and approved vendor files are integration checkpoints, not blockers for synthetic delivery.

## Review Focus

1. **Scanned/image-only PDF** — must emit explicit OCR-required warning; never invent text or silent empty success.
2. **Nonprocedural policy** — must emit `no_supported_process.json`; must not fabricate BPMN tasks.
3. **`file://` demo with spaces in path** — relative assets + embedded data must load; no absolute JupyterHub paths.
4. **Transfer gate default-deny** — DEMO ZIP with excerpts blocked unless `TransferPolicy` explicitly approves.
5. **Stable IDs on rerun** — same synthetic input → same entity/source IDs; overwrite refused without `overwrite=True`.

---

## Target Project Structure

```text
policy-knowledge-poc/   # workspace root = d:\PORTFOLIO\CITI
├── IMPLEMENTATION_PLAN.md          # this plan
├── README.md
├── pyproject.toml                  # metadata only
├── requirements.txt                # inventory for Hub review, not install
├── .gitignore
├── config/
│   ├── app.example.yaml
│   ├── role_taxonomy.yaml
│   ├── risk_taxonomy.yaml
│   ├── control_taxonomy.yaml
│   └── relationship_types.yaml
├── notebooks/
│   └── 00_RUN_ONE_POLICY.ipynb     # ONLY required execution interface
├── src/policy_knowledge/
│   ├── __init__.py
│   ├── config.py
│   ├── pipeline.py                 # run_policy_demo()
│   ├── ingestion/                  # readers, normalizer, chunker
│   ├── intelligence/               # GuardRail client, passes, prompts
│   ├── model/                      # schemas, IDs, graph, provenance
│   ├── governance/                 # taxonomies + matrices
│   ├── exporters/                  # json, okf, bpmn, matrix, viewer
│   ├── validation/                 # schema/graph/bpmn/okf/offline/qa
│   ├── packaging/                  # archive, content review, checksums
│   └── viewer/                     # template, app.js, styles, vendor/
├── tests/                          # fixtures + unit/integration tests
├── policy_runs/                    # gitignored isolated runs
└── docs/                           # architecture, contracts, guides
```

Reusable code: **none yet** — create all modules greenfield per this plan. If GuardRail/vendor assets appear later, adapt adapters and readiness checks without rewriting exporters.

---

## Canonical Data Model (interfaces)

All types live in `src/policy_knowledge/model/schemas.py` (Pydantic v2-compatible with env).

```python
# Core aggregate
class PolicyKnowledge(BaseModel):
    policy: Policy
    source_blocks: list[SourceBlock]
    requirements: list[Requirement]
    roles: list[Role]
    actions: list[Action]
    processes: list[Process]
    decisions: list[Decision]
    risks: list[Risk]
    controls: list[Control]
    evidence: list[Evidence]
    edges: list[KnowledgeEdge]
    findings: list[ReviewFinding]
    modeling_notes: list[str] = []

# Entity field contracts (required semantics; Optional where absent in source)
# Policy: id, title, version?, effective_date?, input_path, source_hash, review_status
# SourceBlock: id, policy_id, section_path, text, block_type, source_locator, sequence, document_hash
# Requirement: id, text, modality (must|shall|should|may|unknown), type, source_refs, review_status, confidence?
# Role / Action / Process / Decision / Risk / Control / Evidence — as master prompt §5
# KnowledgeEdge: id, source_id, target_id, relation_type, source_refs, derivation, confidence?, review_status
# ReviewFinding: id, severity, category, description, entity_ids, source_refs, disposition

# Approved relation_type vocabulary (exact strings):
# POLICY_CONTAINS_SECTION, SECTION_STATES_REQUIREMENT, REQUIREMENT_REQUIRES_ACTION,
# ROLE_PERFORMS_ACTION, ROLE_OWNS_CONTROL, ACTION_PART_OF_PROCESS, ACTION_PRECEDES_ACTION,
# DECISION_BRANCHES_TO_ACTION, REQUIREMENT_ADDRESSES_RISK, CONTROL_MITIGATES_RISK,
# ACTION_EXECUTES_CONTROL, CONTROL_PRODUCES_EVIDENCE, EVIDENCE_SUPPORTS_CONTROL,
# ENTITY_GROUNDED_IN_SOURCE

# derivation ∈ {explicit, inferred_for_review, reviewer_confirmed}
# classification_origin ∈ {source_stated, normalized, suggested}
```

**Stable IDs** (`model/entity_ids.py`):

- Source: `SRC-{NNNN}` from ordered content checksum + locator.
- Entities: deterministic hash of `(type, normalized_key, primary_source_id)`.
- Edges: deterministic from `(source_id, relation_type, target_id, provenance_key)`.
- No random UUIDs as sole IDs.

**Graph helper** (`model/graph.py`): build NetworkX DiGraph from edges; export Cytoscape elements.

---

## Public Python APIs

```python
# ingestion
def read_policy(path: Path) -> list[SourceBlock]: ...

# intelligence
def extract_policy(blocks: list[SourceBlock], llm: LLMAdapter) -> PolicyKnowledge: ...

# validation
def validate_knowledge(knowledge: PolicyKnowledge) -> ValidationReport: ...
def validate_offline_demo(demo_dir: Path) -> ValidationReport: ...

# exporters
def export_okf(knowledge: PolicyKnowledge, output_dir: Path) -> list[Path]: ...
def export_bpmn(knowledge: PolicyKnowledge, output_dir: Path) -> BPMNExportResult: ...
def build_offline_demo(knowledge: PolicyKnowledge, run_dir: Path) -> Path: ...

# pipeline + packaging
def run_policy_demo(
    policy_path: Path,
    policy_id: str,
    config: AppConfig,
    llm: LLMAdapter,
) -> PipelineResult: ...

def archive_policy_run(
    run_dir: Path,
    transfer_policy: TransferPolicy,
) -> ArchiveResult: ...
```

```python
class LLMAdapter(Protocol):
    def generate_text(self, messages: list[dict], **kwargs) -> str: ...
    def generate_narrative(self, messages: list[dict], **kwargs) -> str: ...
    def parse_structured(self, messages: list[dict], schema: type[BaseModel], **kwargs) -> BaseModel: ...

class TransferPolicy:
    workstation_transfer_approved: bool = False
    include_source_in_full: bool = False
    include_intermediate_in_full: bool = False
    include_policy_excerpts_in_demo: bool = False

class ArchiveResult:
    full_zip: Path | None
    demo_zip: Path | None
    checksums_path: Path | None
    report_path: Path
    passed: bool
```

---

## Module Interfaces by Package

### `ingestion/`
| Module | Responsibility |
|---|---|
| `base.py` | `PolicyReader` protocol → `list[SourceBlock]` |
| `docx_reader.py` | paragraphs, styles, lists, tables; paragraph/table locators |
| `pdf_reader.py` | `pypdf` primary; optional `pdfminer` fallback; page locators; OCR warning |
| `html_reader.py` | headings/text/tables via bs4; strip scripts/nav; DOM path locators |
| `normalizer.py` | unify headings/lists/tables; section_path; hashes |
| `chunker.py` | heading-aware chunks with token/char budget + overlap metadata |

### `intelligence/`
| Module | Responsibility |
|---|---|
| `guardrail_client.py` | `initialize`, CREATE/PARSE wrappers, retries, redacted logs, Mock |
| `extraction_pipeline.py` | Passes A–E orchestration |
| `reconciliation.py` | dedupe, pronoun/contradiction findings |
| `response_validation.py` | JSON→Pydantic; reject uncited entities |
| `prompts/*.md` | one prompt file per pass |

### `governance/`
| Module | Responsibility |
|---|---|
| `taxonomy_mapper.py` | exact/alias/unmapped; never silent invent |
| `role_matrix.py` | role × requirement/action/control |
| `risk_control_matrix.py` | risk/control/requirement/process links |
| `traceability.py` | entity → source_ref rows |

### `exporters/`
| Module | Responsibility |
|---|---|
| `json_exporter.py` | canonical + graph + provenance JSON |
| `okf_exporter.py` | OKF v0.2 tree (Markdown + manifest) |
| `bpmn_exporter.py` | BPMN 2.0 XML + DI + mappings or `no_supported_process.json` |
| `matrix_exporter.py` | CSV (+ optional HTML) matrices |
| `viewer_exporter.py` | `outputs/viewer/` + staged `demo/` with `data.js` |

### `validation/` + `packaging/`
Schema/graph/BPMN/OKF/offline validators; quality report; content review gate; checksums; ZIP create/verify.

---

## OKF v0.2 Exporter Contract

Output: `outputs/okf/` with `README.md`, `manifest.json`, `index.md`, `policy.md`, typed entity folders, `relationships/{index.md,edges.json}`, `sources/source_index.json`.

Each Markdown item: frontmatter (`id`, `type`, `title`, `policy_id`, `review_status`, `source_refs`, `links`, `generated_at`) + summary + supporting text + adjacent links. Validator checks link targets, frontmatter completeness, entity ID referential integrity.

## BPMN Exporter Contract

Output: `outputs/bpmn/` — either:

- `policy_process.bpmn` (BPMN 2.0 + DI: shapes, edges, waypoints), `process_index.json`, `activity_mappings.json`, `bpmn_validation.json`

or

- `no_supported_process.json` when `Process.modeling_status` is unsupported / no defensible procedure.

Activity mappings: BPMN element ID → canonical action/decision/role IDs + source_refs.

## Viewer / Demo Contract

- Tabs: Overview, Knowledge Map (Cytoscape), BPMN (bpmn-js), OKF (plain JS), Roles, Risks & Controls, Sources, QA.
- `window.POLICY_DEMO_DATA` in `data.js`; classic script load order; safe escaping; cross-view sync by canonical ID.
- Redacted vs full-fidelity mode recorded in `DEMO_MANIFEST.json` and demo header.

---

## Phased Tasks

### Task 0: Inspect & scaffold foundation

**Files:**
- Create: `README.md`, `pyproject.toml`, `requirements.txt`, `.gitignore`, `config/*.yaml`, `src/policy_knowledge/__init__.py`, `src/policy_knowledge/config.py`, `docs/*.md` (stubs for required docs), `src/policy_knowledge/viewer/vendor/README.md` (expected filenames + approval placeholder)

**Interfaces:**
- Produces: `AppConfig` loaded from YAML/env; `load_config(path: Path | None) -> AppConfig`

- [ ] **Step 1:** Create package skeleton and `.gitignore` (`policy_runs/`, `.env`, `__pycache__`, `.ipynb_checkpoints`).
- [ ] **Step 2:** Implement `AppConfig` / `TransferPolicy` dataclasses matching master prompt §8.4 / §20.
- [ ] **Step 3:** Write docs stubs: `architecture.md`, `data_contracts.md`, `guardrail_integration.md`, `jupyterhub_only_execution.md`, `offline_workstation_demo.md`, `approved_js_assets.md`, `archive_and_transfer_policy.md`, `security_and_data_handling.md`, `modeling_rules.md`, `reviewer_guide.md`, `demo_walkthrough.md`.
- [ ] **Step 4:** Record inspection notes in README: GuardRail not found; vendor assets not found; synthetic-first path.

**Checkpoint:** Importable empty package; config loads from `config/app.example.yaml`.

---

### Task 1: Canonical model + GuardRail adapter (mock)

**Files:**
- Create: `src/policy_knowledge/model/{schemas,entity_ids,graph,provenance}.py`
- Create: `src/policy_knowledge/intelligence/guardrail_client.py`
- Create: `tests/test_guardrail_client_mock.py`, `tests/test_knowledge_graph.py`, `tests/conftest.py`
- Create: `tests/fixtures/synthetic_policy.html` (and later docx/pdf)

**Interfaces:**
- Produces: all entity models; `stable_source_id(...)`, `stable_entity_id(...)`, `stable_edge_id(...)`; `LLMAdapter`, `MockLLMAdapter`, `GuardRailClient` (import GuardRail only if present)

- [ ] **Step 1:** Write failing tests for schema required fields, ID stability, mock generate/parse happy path + malformed JSON + retry.
- [ ] **Step 2:** Implement schemas and ID helpers.
- [ ] **Step 3:** Implement adapter: try discover GuardRail; else raise clear `GuardRailUnavailable` on live path; Mock always works.
- [ ] **Step 4:** Run tests via notebook-compatible invocation pattern documented; locally use pytest if available **without** claiming Hub execution. Prefer `pytest` import + `pytest.main([...])` style in a small runner cell later.

**Checkpoint:** Mock CREATE/PARSE tests pass; live GuardRail marked unchecked.

---

### Task 2: Ingestion + provenance

**Files:**
- Create: `src/policy_knowledge/ingestion/{base,docx_reader,pdf_reader,html_reader,normalizer,chunker}.py`
- Create: `tests/test_ingestion.py`
- Create: fixtures `synthetic_policy.html`, generate minimal docx via python-docx in fixture builder if needed; minimal text PDF if creatable with stdlib-only tooling—or HTML-primary + skip PDF binary commit with generator in test

**Interfaces:**
- Produces: `read_policy(path: Path) -> list[SourceBlock]`

- [ ] **Step 1:** Failing tests: HTML headings/tables; DOCX paragraphs/tables; PDF pages; image-only PDF → OCR warning; empty/malformed paths error.
- [ ] **Step 2:** Implement three readers + dispatcher by suffix.
- [ ] **Step 3:** Normalizer + chunker with sequence preservation.
- [ ] **Step 4:** Tests pass with deterministic `SRC-####` for fixed fixture.

**Checkpoint:** Deterministic source blocks; OCR warning path covered.

---

### Task 3: Extraction pipeline (synthetic/mock LLM)

**Files:**
- Create: `src/policy_knowledge/intelligence/{extraction_pipeline,reconciliation,response_validation}.py`
- Create: `src/policy_knowledge/intelligence/prompts/*.md`
- Create: `tests/test_extraction_validation.py`, `tests/test_source_traceability.py`
- Create: `src/policy_knowledge/validation/{schema_validator,graph_validator,quality_report}.py`

**Interfaces:**
- Consumes: `read_policy`, `LLMAdapter`
- Produces: `extract_policy(...)`, `validate_knowledge(...)`

- [ ] **Step 1:** Define structured pass response schemas (Pydantic) for A–E.
- [ ] **Step 2:** MockLLM returns fixture-aligned JSON for synthetic policy (procedural + nonprocedural variants).
- [ ] **Step 3:** Implement passes + reconciliation; reject entities without `source_refs` when `require_source_refs=True`.
- [ ] **Step 4:** Tests: citation presence, ID stability, no invented owners/frequencies, inferred edges flagged `inferred_for_review`.

**Checkpoint:** Synthetic extraction → valid `PolicyKnowledge` with full provenance.

**Vertical slice note:** After Task 3, wire a minimal `run_policy_demo` path that can reach exporters in Tasks 4–6 with mock data even if later passes refine quality.

---

### Task 4: Governance + OKF exporter

**Files:**
- Create: `src/policy_knowledge/governance/{taxonomy_mapper,role_matrix,risk_control_matrix,traceability}.py`
- Create: `src/policy_knowledge/exporters/{json_exporter,okf_exporter,matrix_exporter}.py`
- Create: `src/policy_knowledge/validation/okf_validator.py`
- Create: `tests/test_okf_export.py`
- Update: taxonomy YAMLs with small synthetic aliases

**Interfaces:**
- Produces: `export_okf(...)`, matrix CSV writers, taxonomy map results with `unmapped`/`not_specified`

- [ ] **Step 1:** Failing OKF tests (manifest, frontmatter, link targets).
- [ ] **Step 2:** Implement exporters + validators.
- [ ] **Step 3:** Taxonomy exact/alias/unknown tests.
- [ ] **Step 4:** Export matrices under `outputs/matrices/`.

**Checkpoint:** OKF tree validates; unmapped fields visible.

---

### Task 5: BPMN exporter + validation

**Files:**
- Create: `src/policy_knowledge/exporters/bpmn_exporter.py`
- Create: `src/policy_knowledge/validation/bpmn_validator.py`
- Create: `tests/test_bpmn_export.py`

**Interfaces:**
- Produces: `export_bpmn(knowledge, output_dir) -> BPMNExportResult` with `.bpmn_path | .no_process_path`, mappings, validation report

- [ ] **Step 1:** Failing tests: well-formed XML namespaces; DI shapes/edges; start/end reachability; nonprocedural → `no_supported_process.json` only.
- [ ] **Step 2:** Implement XML builder (lxml) with lanes from performing roles when sourced.
- [ ] **Step 3:** Separate well-formedness vs semantic checks; never claim XSD conformity without schema.
- [ ] **Step 4:** Tests pass on synthetic procedural policy.

**Checkpoint:** BPMN opens conceptually; nonprocedural path honest.

---

### Task 6: Offline viewer + demo packaging data

**Files:**
- Create: `src/policy_knowledge/viewer/{template.html,app.js,styles.css}`
- Create: `src/policy_knowledge/exporters/viewer_exporter.py`
- Create: `src/policy_knowledge/validation/offline_demo_validator.py`
- Create: `tests/test_offline_demo.py`, `tests/test_vendor_asset_readiness.py`
- Create: `src/policy_knowledge/viewer/vendor/` placeholders + `LICENSES` notes

**Interfaces:**
- Produces: `build_offline_demo(knowledge, run_dir) -> Path` (returns `demo/` path)
- Produces: `validate_offline_demo(demo_dir) -> ValidationReport`

- [ ] **Step 1:** Vendor readiness check (exists, size, sha256 if recorded, expected names).
- [ ] **Step 2:** Generate `data.js` with escaped `POLICY_DEMO_DATA` (entities, cy_elements, bpmn_xml or no_process, matrices, QA, excerpts per transfer mode).
- [ ] **Step 3:** Implement `demo.js`/`demo.css` tabs + cross-view selection; no app-level `fetch`.
- [ ] **Step 4:** Offline validator: local href/src, no CDN, licenses, DEMO_MANIFEST.
- [ ] **Step 5:** If vendor binaries absent, tests assert readiness **fails interactive** but redacted static overview still builds; mark `BROWSER_TEST_NOT_RUN`.

**Checkpoint:** `demo/index.html` structure complete; interactive readiness honest.

**Vendor binary strategy (no downloads):** Place README listing required filenames. Optionally include **minimal stub JS** that defines `BpmnJS`/`cytoscape` no-op globals **only for structural tests**, clearly labeled non-production. Real interactive demo requires user-supplied approved vendor files copied into `viewer/vendor/`.

---

### Task 7: Pipeline + end-to-end notebook

**Files:**
- Create: `src/policy_knowledge/pipeline.py`
- Create: `notebooks/00_RUN_ONE_POLICY.ipynb`
- Create: `tests/test_end_to_end_mock.py`

**Interfaces:**
- Produces: `run_policy_demo(...) -> PipelineResult` with `run_dir`, artifact paths, validation summaries

- [ ] **Step 1:** Implement run directory creation: `policy_runs/<POLICY_ID>/<RUN_ID>/` with subfolders; refuse overwrite unless `overwrite=True`.
- [ ] **Step 2:** Orchestrate ingest → extract → validate → export all → build demo → write `manifest.json`.
- [ ] **Step 3:** Notebook cells 1–11 per master prompt §13 (bootstrap, config, GuardRail/mock, ingest, analyze, artifacts, demo, validate, classify, archive placeholder, download instructions).
- [ ] **Step 4:** E2E mock test builds full tree for synthetic HTML policy.

**Checkpoint:** One notebook “Run All” path defined; e2e mock produces isolated run folder.

---

### Task 8: Archive + transfer gates

**Files:**
- Create: `src/policy_knowledge/packaging/{package_policy,content_review,checksums,archive_validator}.py`
- Create: `tests/test_policy_packaging.py`

**Interfaces:**
- Produces: `archive_policy_run(run_dir, transfer_policy) -> ArchiveResult`

- [ ] **Step 1:** Content review inventory by class; block DEMO when transfer not approved (or allow redacted-only mode).
- [ ] **Step 2:** FULL ZIP excludes `archive/`; DEMO ZIP = `demo/` only; zip-slip-safe paths; no symlink escape.
- [ ] **Step 3:** SHA256SUMS + ARCHIVE_REPORT; `testzip()` + extract-to-temp with spaces path check.
- [ ] **Step 4:** Wire as **last** notebook step.

**Checkpoint:** Auditable ZIPs when permitted; transfer gate default deny.

---

## Synthetic Policy Design (development)

Create one **procedural** synthetic policy (HTML primary; DOCX/PDF derived in tests) covering:

- Title, version, sections
- Normative must/shall obligations
- Named roles and handoffs
- Numbered procedure with decision branch + exception
- Explicit risk, control, evidence mentions
- One ambiguous sentence → `ReviewFinding`

Create one **nonprocedural** synthetic snippet for no-BPMN path.

MockLLM maps fixture source IDs to fixed expected graph in `tests/fixtures/expected_graph.json`.

---

## Test Execution Strategy (constraint-aware)

User cannot run Python outside JupyterHub and forbids installing deps / external services.

During Cursor implementation:

1. Prefer invoking tests with available local tooling **only if** Python already present — document actual results honestly.
2. Always provide notebook cell:

```python
import pytest
pytest.main(["-q", "tests"])
```

3. Never claim Hub or browser verification that was not run; use `BROWSER_TEST_NOT_RUN` / `GUARDRAIL_NOT_CONNECTED`.

Acceptance for this Cursor delivery: working modules + notebook + synthetic e2e artifacts under `policy_runs/` (if runnable) + offline demo tree + tests green where executable.

---

## Phase Dependency Graph

```text
Task0 scaffold
   → Task1 model+mock LLM
      → Task2 ingestion
         → Task3 extraction+validation
            → Task4 governance+OKF ──┐
            → Task5 BPMN ────────────┼→ Task6 viewer
                                     └→ Task7 pipeline+notebook
                                          → Task8 archive
```

Prioritize earliest vertical slice: after Tasks 1–3, stub exporters can emit minimal OKF/BPMN/viewer so Task 6 structure is proven early, then deepen BPMN/OKF fidelity.

---

## Blocking Ambiguities (non-blocking defaults)

| Ambiguity | Default for implementation |
|---|---|
| GuardRail import / `build_messages` unknown | Abstract adapter + local `build_messages`; integration checklist in `docs/guardrail_integration.md` |
| Approved vendor JS bytes unavailable | Readiness fail for interactive; stub globals for unit structure tests; document drop-in path |
| Real policy unavailable | Synthetic only |
| Workstation browser unverifiable here | `BROWSER_TEST_NOT_RUN` |
| Transfer approval unknown | Defaults false; redacted demo mode for synthetic demos in tests |

---

## Spec Coverage Map

| Master prompt section | Plan task |
|---|---|
| §4 Architecture | Tasks 0, 7 |
| §5 Canonical model / relationships | Task 1, 3 |
| §6 Ingestion | Task 2 |
| §7 Extraction / BPMN rules / QA | Tasks 3, 5 |
| §8 GuardRail | Task 1 |
| §9 OKF | Task 4 |
| §10 BPMN export | Task 5 |
| §11 Offline viewer | Task 6 |
| §12 Folder structure | Task 0, 7 |
| §13 Notebook | Task 7 |
| §14 Public APIs | Tasks 2–8 |
| §15 Security / transfer | Tasks 6, 8 |
| §16 Phases 0–8 | Tasks 0–8 |
| §17 Tests | Per-task tests |
| §18–21 Archives / demo acceptance | Tasks 6–8 |
| §22 Env inventory | Task 0, notebook preflight |

---

## Execution Handoff

**Plan complete and saved to `IMPLEMENTATION_PLAN.md`.**

You asked to implement all phases **after the plan is approved**, sequentially, with synthetic policies, no extra dependencies, and no external services.

**Recommended execution:** Native (implement in this session task-by-task), because the pipeline shares one canonical model and interfaces must stay consistent across exporters.

Please review this plan. Does it capture what you want? Reply **approve** (and optionally confirm Native vs Subagent-driven) to start Phase 0 → 8 implementation.
