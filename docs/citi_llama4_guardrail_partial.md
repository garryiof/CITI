# CITI Hub — Llama 4 / GuardRail (comment switch only)

GuardRail **already exists** on CITI JupyterHub. This project is wired so you only **comment / uncomment a few lines** in the notebook. You do **not** install OpenAI on Hub and you do **not** call the public OpenAI API.

Related: [`llm_provider_switch.md`](llm_provider_switch.md) · [`guardrail_integration.md`](guardrail_integration.md)

---

## What is already in place

| Piece | Location | Status |
|---|---|---|
| Provider factory (`llama4` → GuardRail) | `src/policy_knowledge/intelligence/llm_factory.py` | Ready |
| GuardRail adapter + `partial`-compatible CREATE/PARSE | `src/policy_knowledge/intelligence/guardrail_client.py` | Ready |
| Default Hub config | `config/app.example.yaml` → `provider: guardrail`, `model: Llama-4-Scout` | Ready |
| Env template | `.env.example` → `POLICY_LLM_PROVIDER=llama4` | Ready |
| Notebook switch cell | `notebooks/00_RUN_ONE_POLICY.ipynb` **Cell 6** | Ready — comment blocks |

Pipeline cells already pass `llm=` into `run_policy_demo`. No other files need editing for a normal Hub run.

---

## CITI Hub — do this only

### 1. Cell 6 — keep block **A** active, keep block **B** commented

Open `notebooks/00_RUN_ONE_POLICY.ipynb` → **Cell 6**.

**Leave uncommented (CITI):**

```python
LLM_PROVIDER = "llama4"
MODEL = os.environ.get("POLICY_LLM_MODEL", "Llama-4-Scout")
...
```

**Keep commented (OpenAI / home):**

```python
# LLM_PROVIDER = "openai"
# MODEL = os.environ.get("POLICY_LLM_MODEL", "gpt-4o-mini")
...
```

### 2. Uncomment **one** GuardRail import (only if auto-discover fails)

Still in Cell 6. Default is `_HubGR = None` (factory auto-discovers). If status is not `GUARDRAIL_CONNECTED`, uncomment **exactly one** line **below** `_HubGR = None`:

```python
_HubGR = None
# import GuardRail as _HubGR
# import guardrail as _HubGR
# from guardrail import GuardRail as _HubGR
```

Example after edit:

```python
_HubGR = None
import GuardRail as _HubGR
# import guardrail as _HubGR
# from guardrail import GuardRail as _HubGR
```

### 3. (Optional) Uncomment Hub `partial` bindings

Only if your Hub workflow requires explicit `partial` setup (same Cell 6; uses `_HubGR`):

```python
_HubGR.INITIALIZE(SOEID)
generate = partial(_HubGR.CHAT_COMPLETIONS_CREATE, model=MODEL, user=SOEID, extra_body=MODEL_EXTRA_BODY)
...
```

Usually **not required**: `create_guardrail_client(..., backend=_HubGR)` already calls `INITIALIZE` + `CHAT_COMPLETIONS_CREATE` with `model=MODEL`.

### 4. Set Hub env / secrets (no OpenAI key)

```text
POLICY_LLM_PROVIDER=llama4
POLICY_LLM_MODEL=<exact-hub-llama4-model-id>
SOEID=<your-soeid>
```

Do **not** set `OPENAI_API_KEY` on Hub.

If you use a project `.env`, mirror `.env.example` (Llama 4 lines active; OpenAI lines commented).

### 5. Run Cell 6 — expect

```text
GUARDRAIL_CONNECTED GuardRailClient provider= llama4 model= <your-id>
```

Then **Run All** through section 3b.

---

## Home machine — opposite comments

In Cell 6:

1. **Comment** the entire CITI block **A** (`LLM_PROVIDER = "llama4"` …).
2. **Uncomment** block **B** (`LLM_PROVIDER = "openai"` …).
3. Set `OPENAI_API_KEY` in `.env`.

---

## Quick comment map

| Goal | Cell 6 |
|---|---|
| CITI Llama 4 | Block **A** ON · Block **B** OFF · optionally 1× `import GuardRail` |
| Disable OpenAI on Hub | Block **B** stays `#` commented · no `OPENAI_API_KEY` |
| Home OpenAI | Block **A** OFF · Block **B** ON |

| Goal | `.env` / Hub secrets |
|---|---|
| CITI | `POLICY_LLM_PROVIDER=llama4` + `POLICY_LLM_MODEL` + `SOEID` |
| Home | `#` llama lines · uncomment `openai` + `OPENAI_API_KEY` |

---

## Reference — Hub `partial` pattern (already supported)

When GuardRail is imported, this is the approved bind style (same as Hub smoke notebooks):

```python
from functools import partial

GuardRail.INITIALIZE(SOEID)

generate = partial(
    GuardRail.CHAT_COMPLETIONS_CREATE,
    model=MODEL,          # Llama 4 Hub id
    user=SOEID,
    extra_body=MODEL_EXTRA_BODY or {},
)

generate_narrative_llm = partial(
    GuardRail.CHAT_COMPLETIONS_CREATE,
    model=NARRATIVE_MODEL,
    user=SOEID,
    extra_body=MODEL_EXTRA_BODY or {},
)

parse = partial(
    GuardRail.CHAT_COMPLETIONS_PARSE,
    model=MODEL,
    user=SOEID,
    extra_body=PARSE_EXTRA_BODY or {},
)
```

This repo’s `GuardRailClient` performs the equivalent create/parse calls when you pass `backend=GuardRail` — so most runs only need the **import uncomment** + provider block **A**.

---

## Troubleshooting (short)

| Print / error | Action |
|---|---|
| `OPENAI_CONNECTED` | You uncommented block **B** — re-comment it on Hub |
| `GUARDRAIL_NOT_CONNECTED: module not found` | Uncomment the correct Hub `import GuardRail` line |
| `CHAT_COMPLETIONS_CREATE not found` | Wrong module imported — try the other import line |
| Falls back to `MOCK` | Fix import / `SOEID` / model id; do not claim live Llama until `GUARDRAIL_CONNECTED` |

---

## Honesty

- No public OpenAI calls on CITI Hub.
- Do not claim Llama 4 live if status is `MOCK`.
- Offline pack (`offline_p2b`) stays file:// with no LLM at demo time.
