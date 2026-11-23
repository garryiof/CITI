# CITI Hub — Llama 4 / GuardRail (`guardrail_last`)

GuardRail **already exists** on CITI JupyterHub as module **`guardrail_last`**.
This CITI_ONLY package wires that module only — **no OpenAI**.

## Notebook Cell 6

```python
import guardrail_last as _HubGR

llm = create_guardrail_client(
    require_live=True,
    model=MODEL,
    narrative_model=NARRATIVE_MODEL,
    soeid=SOEID,
    backend=_HubGR,
)
```

Auto-discovery also probes `guardrail_last` first (see `guardrail_client.discover_guardrail_module`).

## Env

```text
POLICY_LLM_PROVIDER=llama4
POLICY_LLM_MODEL=<exact-hub-llama4-model-id>
SOEID=<your soeid>
```

Do **not** set `OPENAI_API_KEY`.

## Expected status

```text
GUARDRAIL_CONNECTED GuardRailClient provider= llama4 model= <your-id>
```

If status is `MOCK`, fix the `guardrail_last` import / SOEID / model id — do not claim live Llama.
