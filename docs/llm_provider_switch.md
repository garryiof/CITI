# LLM provider switch (mock / Llama 4 GuardRail / OpenAI)

**Full home guide:** [`home_setup.md`](home_setup.md) · **Hub GuardRail:** [`guardrail_integration.md`](guardrail_integration.md) · **CITI Llama 4 + `partial`:** [`citi_llama4_guardrail_partial.md`](citi_llama4_guardrail_partial.md)

Use `llm.provider` (YAML), `POLICY_LLM_PROVIDER` (env / `.env`), or the notebook `LLM_PROVIDER` cell.

| Provider | When | Requirements |
|---|---|---|
| `mock` | Offline / tests | None — `SyntheticMockLLM` |
| `llama4` / `guardrail` | **CITI JupyterHub** | GuardRail import + `CHAT_COMPLETIONS_CREATE`; `POLICY_LLM_MODEL` (exact Hub id); `SOEID` if required |
| `openai` | Home full-pipeline check only | `OPENAI_API_KEY`; local `openai` package |

`llama4`, `llama-4`, and `llama` are aliases for `guardrail`. Runtime model is **not** OpenAI — it is whatever Hub-approved id you set (default label `Llama-4-Scout`).

## CITI Hub (Llama 4)

```text
POLICY_LLM_PROVIDER=llama4
POLICY_LLM_MODEL=<exact Hub model id>
SOEID=<your soeid>
```

In the notebook, Run All. Expect `GUARDRAIL_CONNECTED` and `model=…`. If GuardRail is missing, the cell falls back to mock and prints a hint — do **not** claim live Llama connectivity.

## Home (OpenAI, optional)

```text
POLICY_LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
POLICY_LLM_MODEL=gpt-4o-mini
```

## Honesty rules

- Manifest records `llm_provider` / `llm_status` (`MOCK` | `OPENAI_CONNECTED` | `GUARDRAIL_CONNECTED`).
- Never claim GuardRail/Llama connectivity when using OpenAI or mock.
- Never write API keys or SOEID into tracked files.
