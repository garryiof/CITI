# GuardRail integration checklist

**Status:** `GUARDRAIL_NOT_CONNECTED` — no org GuardRail helpers were found in this repo at scaffold time.

For switching among **mock / OpenAI (home) / GuardRail (Hub)**, see [`llm_provider_switch.md`](llm_provider_switch.md).

## Bootstrap (live Hub path)

1. Set `llm.provider: guardrail` (or `POLICY_LLM_PROVIDER=guardrail`).
2. Discover the approved import path for `GuardRail` in the Hub environment (do not invent package names).
3. Call the organization-approved initialize pattern (e.g. `GuardRail.INITIALIZE(SOEID)` if that is the local contract).
4. Wire CREATE/PARSE (or equivalent) callables into `GuardRailClient`.
5. Keep `SOEID`, certificates, and endpoints out of tracked files — use env / Hub secrets.
6. If GuardRail is unavailable, use `create_llm_client` with `mock` and do **not** claim live connectivity.

## Local helpers

- `create_llm_client(config)` — provider factory (`mock` | `openai` | `guardrail`).
- `build_messages(system, user)` — thin local formatter until an org helper is discovered.
- Unsupported model parameters must be omitted safely via config (`llm.extra_body` / `parse_extra_body`).
- Passes A–E and Pass F (`analyze_role_relevance`) all call `LLMAdapter.parse_structured` — when GuardRail CREATE/PARSE is wired, role intelligence uses the same path without a separate provider.
