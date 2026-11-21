# Policy Intelligence POC

JupyterHub-only proof of concept: one policy (DOCX / PDF / HTML) → canonical `PolicyKnowledge` → OKF v0.2, BPMN 2.0+DI, governance matrices, and a portable `file://` offline HTML demo with FULL/DEMO ZIP archives.

## Execution (only path)

Open and **Run All** in:

`notebooks/00_RUN_ONE_POLICY.ipynb`

No CLI, `python -m`, shell magics, `%pip`, or local HTTP server.

## Workspace inspection (Phase 0)

| Item | Finding |
|---|---|
| GuardRail helpers in repo | **Not found** — use `LLMAdapter` + provider switch (`mock` / `openai` / `guardrail`); see `docs/llm_provider_switch.md` |
| `build_messages` org helper | **Not found** — local thin helper until org helper is discovered |
| Vendor bpmn-js / Cytoscape | **Not found** — placeholders under `src/policy_knowledge/viewer/vendor/`; interactive demo not ready until approved bytes are supplied |
| Real policy document | **Not supplied** — develop against `tests/fixtures/synthetic_policy.*` |

Synthetic-first path is intentional. Live GuardRail and approved vendor JS are integration checkpoints, not blockers for the mock vertical slice.

## Layout

- `src/policy_knowledge/` — importable modules
- `notebooks/00_RUN_ONE_POLICY.ipynb` — sole required UX
- `config/` — YAML taxonomies and `app.example.yaml`
- `tests/` — unit/integration + synthetic fixtures
- `policy_runs/` — isolated run trees (gitignored)
- `docs/` — architecture, contracts, transfer/security guides

## Config

```python
from pathlib import Path
from policy_knowledge.config import load_config

config = load_config(Path("config/app.example.yaml"))
```

## Tests (notebook-compatible)

```python
import pytest
pytest.main(["-q", "tests"])
```

## LLM providers

| Provider | Use |
|---|---|
| `mock` | Default synthetic / tests |
| `openai` | Home full check — `OPENAI_API_KEY` + local `openai` package |
| `guardrail` | CITI Hub after org wiring |

Set via `config/app.example.yaml` (`llm.provider`), env / `.env` `POLICY_LLM_PROVIDER`, or the notebook cell.

**Home:** put files in `policies/`, copy `.env.example` → `.env` with `OPENAI_API_KEY`, then follow `docs/home_setup.md`.

## Status flags (honest)

- `MOCK` / `OPENAI_CONNECTED` / `GUARDRAIL_CONNECTED` via `llm_status`
- `GUARDRAIL_NOT_CONNECTED` unless the GuardRail adapter is actually live
- `BROWSER_TEST_NOT_RUN` until workstation `file://` verification
