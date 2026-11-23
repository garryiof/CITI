# GuardRail integration checklist

**Status:** `GUARDRAIL_NOT_CONNECTED` — no org GuardRail helpers were found in this repo at scaffold time.

For switching among **mock / OpenAI (home) / GuardRail (Hub)**, see [`llm_provider_switch.md`](llm_provider_switch.md).

**Detailed CITI steps (disable OpenAI, bind Llama 4 with `functools.partial`):** [`citi_llama4_guardrail_partial.md`](citi_llama4_guardrail_partial.md).

## Bootstrap (live Hub path)

1. Set `POLICY_LLM_PROVIDER=llama4` (or `guardrail`) and `POLICY_LLM_MODEL` to the **exact** Hub Llama 4 model id.
2. Set `SOEID` / `POLICY_SOEID` via Hub secrets if `GuardRail.INITIALIZE` requires it.
3. Ensure `GuardRail` (or discovered module) exposes `CHAT_COMPLETIONS_CREATE` (and optionally `CHAT_COMPLETIONS_PARSE`).
4. Run the notebook LLM cell — expect `GUARDRAIL_CONNECTED` and printed `model=…`.
5. Keep `SOEID`, certificates, and endpoints out of tracked files.
6. If GuardRail is unavailable, the notebook falls back to `mock` — do **not** claim live Llama connectivity.


## Local helpers

- `create_llm_client(config)` — provider factory (`mock` | `openai` | `guardrail`).
- `build_messages(system, user)` — thin local formatter until an org helper is discovered.
- Unsupported model parameters must be omitted safely via config (`llm.extra_body` / `parse_extra_body`).
- Passes A–E and Pass F (`analyze_role_relevance`) all call `LLMAdapter.parse_structured` — when GuardRail CREATE/PARSE is wired, role intelligence uses the same path without a separate provider.
