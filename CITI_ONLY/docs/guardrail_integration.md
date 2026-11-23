# GuardRail integration (CITI_ONLY)

**Hub module:** `guardrail_last`

1. Set `POLICY_LLM_PROVIDER=llama4` (or `guardrail`) and `POLICY_LLM_MODEL` to the exact Hub Llama 4 model id.
2. Set `SOEID` / `POLICY_SOEID` if `GuardRail.INITIALIZE` requires it.
3. Notebook Cell 6: `import guardrail_last as _HubGR` then `create_guardrail_client(..., backend=_HubGR)`.
4. Expect `GUARDRAIL_CONNECTED`.
5. If GuardRail is unavailable, the notebook falls back to `mock` — do **not** claim live Llama connectivity.

OpenAI is not part of this package.
