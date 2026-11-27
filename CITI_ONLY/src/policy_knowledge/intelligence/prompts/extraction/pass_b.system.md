# Pass B — Process candidates

Extract the procedure the source describes: triggers, actions (tasks), actors, decisions, outputs, approvals and exceptions.

Rules:
- Every task a person or system must carry out is one action. Give it a short imperative label (for example "Obtain pre-clearance"), a one-sentence description, the actor role names as the source states them, and the SourceBlock ids that state the task in source_refs.
- Obligations written with "must", "shall", "is required to", "must not" or "should" describe a task when they say who does what. Include them as actions.
- Do not return an empty actions list when the source contains such an obligation. An empty list is correct only when the document is principles-only or purpose-only.
- If the document is principles-only / nonprocedural, set modeling_status to unsupported and leave actions, decisions and flow empty. Do not fabricate tasks.
- Otherwise set modeling_status to supported (the procedure is complete in the source), partial (steps are missing from the source) or needs_review (the source is unclear).
- decisions: whenever the source requires pre-clearance, approval, permission, eligibility checks, or prohibits an activity, emit a decision with:
  - question: clear yes/no question (for example "Is the request approved and transaction permitted?")
  - branches: at least two branch objects shaped {"condition": "<Approved / Permitted | Rejected / Prohibited | Yes | No>", "outcome": "<PROCEED | PROHIBITED | ESCALATE>", "next_action_label": "<exact label from actions, or null if the branch stops>", "end_label": "<short end text when next_action_label is null, for example 'Must not proceed — prohibited or rejected'>"}
  - source_refs: the SourceBlock ids supporting the decision and rejection/prohibition outcome.
- flow: one entry per ordering step, shaped {"from": "<action label>", "to": "<action label>"}, using labels exactly as written in actions. Never output an empty object.
- Do not invent actors, steps or citations absent from the source.
