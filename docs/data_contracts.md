# Data contracts

Typed Pydantic models live in `src/policy_knowledge/model/schemas.py`. Relation types are fixed vocabulary (see `config/relationship_types.yaml`). Stable IDs are deterministic hashes — no random UUIDs as sole identifiers.

OKF, BPMN, matrices, and viewer data are **derived views** of `PolicyKnowledge`, never independently regenerated facts.
