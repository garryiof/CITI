# Cursor Master Prompt — Role-Based Policy Intelligence in `offline_p2b`
## PLAN MODE ONLY — READ-ONLY REPOSITORY ASSESSMENT, NO IMPLEMENTATION

You are analyzing an **existing, working policy-processing and offline demonstration application**. Your only task now is to inspect it and produce an actionable, evidence-based implementation plan. **Do not implement changes until I explicitly approve them in a later request.**

## A. Non-negotiable execution rules

- **Read-only planning.** You may inspect repository files, existing documentation, prompt text, tests, manifests, notebooks, and sample output artifacts.
- **Do not write, edit, create, rename, move, or delete any project file.** Do not auto-fix, format, refactor, install packages, generate build artifacts, run notebooks, run LLM calls, deploy, commit changes, or execute commands that alter files or application state. Do not run tests in this phase; plan them instead.
- Never use a terminal command if it could modify files, caches, logs, environments, or generated artifacts. Prefer editor/code search and read-only inspection.
- Do not click **Build**, make code edits, or transition to implementation. Return the plan for review and **STOP**.
- If repository content cannot be inspected, explicitly state what is missing. Do not pretend to know filenames, implementation details, or current behavior. Separate *observed facts* from *proposals* and *assumptions*.
- Maintain **100% of existing functionality and backward compatibility** as a required acceptance goal. Do not promise compatibility without a regression test plan.

## B. Business objective: One policy, three intelligence lenses

Introduce three audience lenses over **the same canonical policy artifacts**, not three separate policy copies:

1. **Business Owner** — "What must I do to comply with this policy?"
2. **Compliance Officer** — "How do I determine whether compliance requirements are satisfied?"
3. **Policy Owner** — "Is the policy complete, coherent, adequately governed, and maintainable?"

Principle: **Same Artifacts, Different Role Paths.** One policy clause or control may interest all three roles, but for different reasons. A viewer/audience role is not necessarily an operational role formally assigned by the policy. Do not invent ownership or duties.

| Shared artifact | Business Owner lens | Compliance Officer lens | Policy Owner lens |
|---|---|---|---|
| Policy | Which parts apply to my operations? | Which requirements must be assessed? | What does the policy cover and govern? |
| Risk | What could go wrong operationally? | What risks require monitoring? | Are important risks adequately covered? |
| Rules / obligations | What must I do or avoid? | How can I test conformance? | Are rules clear, consistent, maintained? |
| Controls | What must the business perform? | What should be verified? | Which controls does policy require? |
| Evidence | What must I retain or produce? | What can substantiate compliance? | What evidence must be defined? |
| Procedures / use cases | How does this affect my workflow? | Which scenarios merit testing? | What process dependencies are affected? |

Role-specific priorities and expected outputs:

**Business Owner:** applicability; mandatory and prohibited actions; deadlines; approvals; process steps; operational risk; controls to perform; record retention; exception/escalation. Explain **why** each item matters to running the business, **what action** is supported by the policy, and **what proof** is needed. Navigation: **Task → Rules → Actions → Proof → Completion**. Output: operational action checklist; do not treat completion as evidenced unless evidence exists.

**Compliance Officer:** obligations; risk taxonomy; independently testable rules; controls to verify; evidence sufficiency; exceptions/breaches; monitoring and test scenarios; coverage gaps. Explain **why** monitoring/verification matters, **how** a requirement could be tested, and **what evidence** would support a finding. Navigation: **Case → Risk → Rules → Checks → Decision**. Output: compliance testing and assessment view; distinguish suggested tests from established controls.

**Policy Owner:** purpose, scope, applicability; requirement consistency; policy and regulatory dependencies **only when grounded in provided sources**; risk and control coverage; roles/accountabilities; evidence design; ambiguity; contradictory clauses; policy gaps; change impact. Explain **why** each element affects governance, ownership, coherence, or maintenance. Navigation: **Policy → Coverage → Dependencies → Change Impact**. Output: governance/coverage/gap view; do not invent external regulatory citations.

## C. Mandatory LLM analysis design

Design reusable SYSTEM and USER prompts for analyzing **any policy**. The model must examine the complete supplied policy, available extracted canonical artifacts, applicable approved risk taxonomy, role mappings, and source metadata. It must not classify items solely through keywords.

For every provision / existing canonical artifact, specify how the LLM will:

1. Identify artifact type: provision, obligation, risk, rule, control, evidence, process/procedure, dependency, or other existing type.
2. Evaluate each of the three audience lenses **independently**.
3. Classify relevance as `PRIMARY`, `SECONDARY`, `NOT_RELEVANT`, or `UNCERTAIN` with a short rationale, including a rationale for non-relevance when useful.
4. Answer **why this role cares**, **what it should know**, and **what it should do, verify, or govern**.
5. Link associated risks, rules, controls, evidence, processes, and dependencies **only when supported**.
6. Cite an exact existing `artifact_id` and source section/paragraph/text span; preserve policy/version provenance.
7. Mark each statement as `EXPLICIT`, `INFERRED`, or `UNDETERMINED` and surface unsupported conclusions for review.
8. Identify ambiguities, contradictions, absent owners, uncertain controls, and missing evidence without silently resolving them.
9. Preserve stable canonical identifiers and distinguish **audience relevance** from **formally assigned policy responsibilities**.
10. Support overlapping relevance: one artifact can have three different role interpretations.

Recommend strategy for long policies (safe segmentation, stable source IDs, reconciliation, duplicate avoidance, complete coverage) if required by actual repo behavior. Provide a programmatic post-LLM validation design for source anchoring, schema fidelity, and consistency. Confidence scores must not be presented as calibrated probabilities without evaluation.

## D. Shared role-relevance output contract

Propose a structured, versioned JSON contract, provisionally named `role_relevance.json`, that **references** shared policy objects rather than duplicating them. Adapt naming and path to proven repository conventions. Suggested fields:

- `schema_version`, `policy_id`, `policy_version`, `generated_at`, `source_hash`, `prompt_id`, `prompt_version`, `model_id`
- `artifact_id`, `artifact_type`, `source_reference`, `source_quote_or_span`
- `role_id`, `relevance_level`, `reason_for_relevance`, `role_question`, `role_action_or_check`
- `associated_risk_ids`, `associated_control_ids`, `associated_evidence_ids`, `dependency_ids`
- `interpretation_type`, `confidence`, `review_status`, `ambiguities`

Define required/optional fields, null/unknown representations, stable ID rules, schema validation, error handling, and safe consumption by an offline JavaScript UI. Do not invent source content, risk ratings, owner assignments, deadline values, legal duties, or control effectiveness. Preserve canonical artifact IDs.

## E. LLM invocation: reuse approved Citi GuardRail integration

Inspect existing approved notebook and local code before proposing changes. Reuse its actual `GuardRail`, authentication, configuration, `build_messages`, response parsing, and generation behavior. The illustrative **reference pattern** is:

```python
from functools import partial

# These objects/config values must come from the existing approved environment.
# Do not invent a GuardRail import or external endpoint.
GuardRail.INITIALIZE(SOEID)

generate = partial(
    GuardRail.CHAT_COMPLETIONS_CREATE,
    model=MODEL,
    user=SOEID,
    extra_body=MODEL_EXTRA_BODY,
)

completion = generate(
    messages=build_messages(user_prompt, system_prompt),
    n=1,
    temperature=GENERATION_TEMPERATURE,
)
```

Use `GuardRail.CHAT_COMPLETIONS_PARSE` **only if supported in the discovered environment**; otherwise design a validated JSON response using `CHAT_COMPLETIONS_CREATE`. Preserve the approved model, parameters, initialization, retries, and authentication unless separately approved. Do **not** call the public OpenAI API, add external SDKs, invent APIs, or execute any model request in this planning phase.

Propose independent reusable SYSTEM and USER prompt templates, runtime input binding, output parsing, failure handling, and schema/source validation. Do not include confidential policy content in reusable prompt files.

## F. Mandatory external prompt library for the **entire solution**

Every existing and future **LLM instruction prompt** must be an **external, version-controlled file**, not hardcoded text in Python, JavaScript, Jupyter notebooks, or UI components. Dynamic policy content and runtime arguments remain inputs, **not static prompt files**.

Inspect and inventory **all actual LLM invocations and their existing prompt sources**. Propose a centralized library, adapting to existing repository conventions. An illustrative—not presumed—structure:

```text
prompts/
  policy_extraction/
    system.md
    user.md
  risk_analysis/
    system.md
    user.md
  control_mapping/
    system.md
    user.md
  role_relevance/
    system.md
    user.md
  compliance_analysis/
    system.md
    user.md
  validation/
    system.md
    user.md
  manifest.yaml
```

Do not create a directory for an operation that does not actually exist or is not needed. If operations use additional instructions (such as review, summarization, exception analysis, or narratives), inventory those too and plan equivalent externalization.

Required design:

1. **Single reusable prompt loader/renderer** with controlled templating, required-variable checking, missing-file handling, safe substitution, and no arbitrary code evaluation.
2. **Explicit prompt manifest/versioning**: prompt ID, version, template paths, required variables, optionally expected response schema and operation metadata.
3. **Audit/reproducibility**: record prompt ID/version/content hash, model, invocation configuration, policy/version, and output schema in generated artifacts without exposing credentials.
4. **Behavior-preserving migration**: first externalize existing prompt text **verbatim** and preserve message ordering, parameter values, generation mode, parsing, and call structure. Propose any prompt improvements separately, not bundled with migration.
5. **Security**: secrets stay in approved config/auth mechanisms; confidential data is injected only at invocation time; do not bundle sensitive inputs with reusable prompt templates.
6. **Tests**: compare rendered prompts against current strings; test missing variables, malformed manifest, encoding, schema mismatch, version mismatch, and compatibility.
7. **Offline demo**: no prompt loading and no LLM invocation needed on the workstation; all role outputs are precomputed.

## G. `offline_p2b` is the **main** executive demonstration screen

Inspect what `offline_p2b` actually is (file, entry point, module, page, or app). Do not assume a framework, route, component tree, or existing functionality. Preserve its visual design, startup procedure, current views, outputs, navigation, and user interactions.

Plan the minimum viable role-based extension **inside `offline_p2b`**:

1. Open selected policy and existing precomputed artifacts.
2. Show a clearly labeled lens selector: **Business Owner / Compliance Officer / Policy Owner**.
3. Display prioritized, relevant provisions and why they matter for the selected lens.
4. Show required actions/checks/governance questions and links to shared risks, rules, controls, evidence, and procedures.
5. Navigate to original policy source references using existing mechanisms where possible.
6. Switch lenses instantaneously using precomputed role relevance; no LLM call or network request.
7. If role metadata is absent/invalid, preserve the **current default experience exactly**; use a nonintrusive warning only if necessary.
8. Retain any existing BPMN functionality and links, if found. Do not introduce artificial workflow lanes or fake procedural order merely for audience lenses.
9. Do not change existing canonical artifacts on a lens switch; apply presentation/filtering/annotation only.

Produce a concrete screen-level UX proposal grounded in the repository's actual UI and data-loading approach. Executive-friendly language; avoid clutter and duplicate panels.

## H. Offline policy preparation, export, and archive

Preserve the established operating model:

- **JupyterHub preparation**: analyze **one policy before the demo**, create all its artifacts inside one isolated policy folder, and add role relevance output during preparation using the approved GuardRail interface.
- **Workstation demonstration**: transfer/extract the isolated policy archive and launch `offline_p2b` to show all lenses **fully offline**.
- **Archiving**: include the role relevance output and provenance/manifest in the existing policy archive; preserve existing directory layout, filenames, export contracts, and readers where possible.
- Respect the environment limitation that `python -m` commands cannot be run outside the approved JupyterHub workflow. Do not propose an execution sequence dependent on such commands on the workstation or outside JupyterHub.
- No network calls, credentials, GuardRail runtime, or newly installed packages may be necessary for the workstation demo.

Identify exact existing pipeline/export/archive touchpoints and propose where the new artifact should fit. Mark any unverified path or format as *proposed*.

## I. Backward compatibility and regression prevention — critical

**Do not break previous functionality.** Treat the enhancement as additive, optional, and reversible.

1. Preserve all existing policy ingestion, parsing, mapping, outputs, viewers, navigation, file contracts, APIs, notebook processes, and archive/export behavior.
2. Preserve current `offline_p2b` behavior **unchanged** when the lens selector is not used, or when role data is missing/invalid.
3. Existing policy archives **must still load unmodified**. New metadata must be optional for legacy readers.
4. Preserve existing GuardRail calls and LLM prompt text/results behavior during the externalization stage; plan separate approval for behavioral changes.
5. Identify interface and schema changes, migration risk, and any potential conflict with existing role labels or permission concepts.
6. Prefer feature flags, optional data files, adapter boundaries, stable schemas, and additive UI components rather than replacing working modules.
7. Plan baseline capture on representative working policies **before implementation** (but do not run it now); compare outputs and current UI behaviors afterward. Where model outputs vary, compare schemas, provenance, coverage, and controlled invariants, not exact prose alone.
8. Plan regression tests for existing pipeline, prompt rendering, GuardRail handling, source links, JSON consumption, old archives, archive generation, `offline_p2b` interactions, and offline startup.
9. Include explicit rollback steps to disable the new lens without disrupting existing behavior, and a trigger for halting if any critical regression appears.
10. State any unavoidable breaking change separately as **approval required**; never silently include it in implementation.

Required regression matrix:

| Component (actual path) | Current behavior | Proposed addition | Regression risk | Baseline/validation | Rollback |
|---|---|---|---|---|---|

**Acceptance gates:** old workflow still functions; legacy artifacts load; old UI/default behavior remains; new role switching works offline; every role conclusion has traceable evidence or is marked inferred/unknown; no unapproved invocation or dependency changes.

## J. Synthetic example and verification approach

Design (do not execute) a small **synthetic, nonconfidential policy** with a mandatory action, a five-business-day deadline, an approval, a risk, a control, retention evidence, and exception/escalation. Show a clear example matrix where the **same artifact ID** supports three different role explanations, including:

- an artifact primarily relevant to one role but not another;
- an ambiguous role assignment flagged for review;
- explicit vs inferred responsibilities;
- a traceable source paragraph and associated control/evidence IDs.

Propose measurable evaluation criteria: source coverage, role relevance precision/recall against human review, cross-role consistency, false ownership assignments, citation validation, JSON schema validity, and offline viewer regression. Do not claim measured accuracy without tests.

## K. Required plan response — tables first, concise and concrete

Use **actual repo paths and observed findings**, not guessed paths. Return in this order:

1. **Repository discovery summary**: `offline_p2b` entry point, UI data flow, policy processing, artifact schema, GuardRail call sites, current prompt locations, JupyterHub/export/archive steps; mark items not verified.
2. **Table A — Business Owner:** `Policy Artifact | Information of Interest | Why It Matters | Business Action | Output`.
3. **Table B — Compliance Officer:** `Policy Artifact | Information of Interest | Why It Matters | Verification Approach | Output`.
4. **Table C — Policy Owner:** `Policy Artifact | Information of Interest | Why It Matters | Governance Responsibility | Output`.
5. **Table D — Prompt inventory:** `Operation | Call Site (real path) | Current Prompt Location | External File Proposal | Migration Risk`.
6. **Proposed external prompt folder tree**, shared loader/manifest contract and versioning approach.
7. **Actual proposed SYSTEM prompt and USER prompt template** for role relevance, returned **in the plan only**, not written into project files.
8. **Proposed JSON schema** with a brief example of shared artifact ID used by all three lenses.
9. **Table E — `offline_p2b` integration:** `Existing Component (real path) | Proposed Enhancement | Input | Output | Complexity`.
10. **GuardRail and notebook integration design** with actual modules, outputs, offline folder/archive touchpoints, and a no-runtime-LLM guarantee.
11. **Table F — Phased implementation plan:** `Phase | Goal | Existing/New Files | Dependencies | Acceptance Criteria | Approval Gate`.
12. **Regression matrix** from section I, including a baseline and rollback plan.
13. **Synthetic example** and proposed business-user demo sequence: launch `offline_p2b`; demonstrate Business Owner actions, Compliance verification, then Policy Owner governance, all from the same policy.
14. **Exact list of existing files that would change** and **new files that would be proposed** (no actual files created).
15. **Assumptions, limitations, and open decisions**, with explicit priority and your recommended approach.

At the end, print: **"PLAN ONLY — NO FILES CHANGED. AWAITING EXPLICIT APPROVAL TO IMPLEMENT."**

## L. Final stop condition

**STOP AFTER THE PLAN.** Do not code, install, deploy, run tests, invoke GuardRail, save generated prompts to the repo, or click Build. Approval of the plan must come in a **separate, explicit user instruction** before any implementation.
