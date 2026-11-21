# LLM provider switch — short design (approved)

**Intent:** Home full-pipeline check via OpenAI; Hub via CITI GuardRail; tests via mock.

**Approach picked:** Config + factory (`llm.provider` / `POLICY_LLM_PROVIDER` → `create_llm_client`). Rejected notebook-only and API-key auto-detect.

**Goals:** One switch; same `LLMAdapter` contract; honest run metadata; secrets via env only.

**Non-goals:** Requiring OpenAI on Hub; inventing GuardRail CREATE/PARSE; changing exporters.

**Design:** `OpenAIAdapter` (optional `openai` package) + `create_llm_client` for `mock`|`openai`|`guardrail`; notebook/docs updated; default safe `mock`.
