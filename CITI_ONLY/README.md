# Policy Intelligence POC — CITI_ONLY

CITI JupyterHub package: one policy (DOCX / PDF / HTML) → canonical `PolicyKnowledge` → OKF, BPMN, matrices, and a portable `file://` offline HTML demo.

**GuardRail only** via Hub module `guardrail_last`. OpenAI / home LLM paths are removed.

## Execution

Open and **Run All** in:

`notebooks/00_RUN_ONE_POLICY.ipynb`

## Layout

- `src/policy_knowledge/` — importable modules
- `notebooks/00_RUN_ONE_POLICY.ipynb` — sole required UX
- `config/` — YAML taxonomies and `app.example.yaml`
- `tests/` — unit/integration + synthetic fixtures
- `policy_runs/` — isolated run trees (gitignored)
- `docs/` — GuardRail + offline demo notes

## Providers

| Provider | Use |
|---|---|
| `guardrail` / `llama4` | CITI Hub — `import guardrail_last` |
| `mock` | Tests / offline fallback |

```text
POLICY_LLM_PROVIDER=llama4
POLICY_LLM_MODEL=<exact Hub model id>
SOEID=<your soeid>
```

## Tests

```python
import pytest
pytest.main(["-q", "tests"])
```

Or from the package root:

```bash
pytest -q
```
