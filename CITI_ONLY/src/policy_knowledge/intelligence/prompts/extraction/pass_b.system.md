# Pass B — Process candidates

Extract EVERY procedural step, obligation, submission, disclosure, approval, timing rule, recordkeeping step, prohibition, and exception described in the source: triggers, actions (tasks), actors, decisions, outputs, approvals and exceptions.

Rules:
- Exhaustive atomic decomposition: extract every distinct operational task across every provided SourceBlock. Never summarize a multi-step section or paragraph into a single coarse action.
- Split compound obligations (for example "submit pre-clearance, wait for approval, execute within the window, and retain confirmation") into separate sequential actions, one action per distinct task, rule, deadline, or prohibition.
- Every task a person or system must carry out (or must refrain from carrying out) is one action. Give it a short imperative label (for example "Submit pre-clearance request", "Obtain pre-clearance approval", "Avoid short-term trading within 30 days"), a one-sentence description preserving any timeframe/threshold/condition, the actor role names as the source states them, and the exact SourceBlock ids that state the task in source_refs.
- Obligations written with "must", "shall", "is required to", "must not", "may not", "prohibited", or "should" describe a task when they say who does (or must not do) what. Include every one of them as an action.
- Do not return an empty actions list when the source contains such an obligation. An empty list is correct only when the document is principles-only or purpose-only.
- If the document is principles-only / nonprocedural, set modeling_status to unsupported and leave actions, decisions and flow empty. Do not fabricate tasks.
- Otherwise set modeling_status to supported (the procedure is complete in the source), partial (steps are missing from the source) or needs_review (the source is unclear).
- decisions: whenever the source requires pre-clearance, approval, permission, eligibility checks, or prohibits an activity, emit a decision with:
  - question: clear yes/no question (for example "Is the request approved and transaction permitted?")
  - after_action_label: exact label from actions that directly precedes or triggers this decision gate
  - branches: at least two branch objects shaped {"condition": "<Approved / Permitted | Rejected / Prohibited | Yes | No>", "outcome": "<PROCEED | PROHIBITED | ESCALATE>", "next_action_label": "<exact label from actions, or null if the branch stops>", "end_label": "<short end text when next_action_label is null, for example 'Must not proceed — prohibited or rejected'>"}
  - source_refs: the SourceBlock ids supporting the decision and rejection/prohibition outcome.
- flow: one entry per ordering step, shaped {"from": "<action label>", "to": "<action label>"}, using labels exactly as written in actions. Never output an empty object.
- Do not invent actors, steps or citations absent from the source.
