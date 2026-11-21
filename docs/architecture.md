# Architecture

Canonical `PolicyKnowledge` is the single source of truth. Ingestion produces provenance-preserving `SourceBlock`s; a GuardRail-backed (or mock) multi-pass extractor fills typed entities and edges; deterministic exporters derive OKF, BPMN, matrices, and precomputed viewer `data.js`.

**Pass F (role relevance):** After Passes A–E, the same `LLMAdapter` scores existing artifacts for three intelligence perspectives (`business_owner`, `compliance_officer`, `policy_owner`) into `outputs/canonical/role_relevance.json`. The offline Policy Knowledge demo embeds that file in `POLICY_DEMO_DATA` so role switching never calls an LLM on the workstation.

**External prompts:** All SYSTEM/USER templates live under `src/policy_knowledge/intelligence/prompts/` and are loaded via `prompt_loader.py` (`manifest.json` versions + `{{var}}` substitution).

All artifacts land under `policy_runs/<POLICY_ID>/<RUN_ID>/`. Archiving is the final notebook-callable step.

See master prompt §4 and `IMPLEMENTATION_PLAN.md`.
