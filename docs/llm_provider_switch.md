# LLM provider switch (mock / OpenAI / GuardRail)

**Full home guide (policy folder + API key):** [`home_setup.md`](home_setup.md)

Use `llm.provider` (YAML), `POLICY_LLM_PROVIDER` (env / `.env`), or the notebook `LLM_PROVIDER` cell to select the adapter. All providers implement the same `LLMAdapter` protocol.

| Provider | When | Requirements |
|---|---|---|
| `mock` | Offline / tests / Hub without GuardRail | None — uses `SyntheticMockLLM` |
| `openai` | **Home full-pipeline check** | `OPENAI_API_KEY`; local `openai` package; optional `POLICY_LLM_MODEL` (default `gpt-4o-mini`) |
| `guardrail` | CITI JupyterHub live path | Org GuardRail wiring — see `guardrail_integration.md` |

## Home run (OpenAI)

1. Notebook **section 0** once → restart kernel.
2. Copy policy into `policies/` → set `POLICY_PATH` in Config (see `policies/README.md`).
3. `Copy-Item .env.example .env` → set `OPENAI_API_KEY` and `POLICY_LLM_PROVIDER=openai`.
4. Run All from Bootstrap. Expect `OPENAI_CONNECTED`.

Factory: `policy_knowledge.intelligence.llm_factory.create_llm_client`.

## Hub run (GuardRail)

Keep `llm.provider: guardrail`. Do not set `OPENAI_API_KEY` on Hub. If GuardRail is unavailable, notebook falls back to mock (`GUARDRAIL_NOT_CONNECTED`).

## Honesty rules

- Manifest records `llm_provider` / `llm_status` (`MOCK` | `OPENAI_CONNECTED` | `GUARDRAIL_CONNECTED`).
- Never claim GuardRail connectivity when using OpenAI or mock.
- Never write API keys into tracked files or run snapshots.
