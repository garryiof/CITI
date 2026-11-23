export type ReviewStatus = "PENDING" | "APPROVED";

export type UserRole = "VIEWER" | "POLICY_OWNER";

export type WorkflowIndexItem = {
  workflow_id: string;
  title: string;
  steps: number;
  confidence: number;
  validation_errors: number;
  json: string;
  bpmn: string;
};

export type SourceReference = {
  reference_id: string;
  section_id: string;
  section_title: string;
  paragraph: number;
  start_offset: number;
  end_offset: number;
  quoted_text: string;
  anchor?: string;
  source_html?: string;
};

export type Actor = {
  actor_id: string;
  name: string;
  bpmn_lane: string;
};

export type WorkflowStep = {
  step_id: string;
  sequence: number;
  title: string;
  description: string;
  action_phrase?: string;
  action_type: string;
  explicit_or_inferred: "EXPLICIT" | "INFERRED";
  wording_origin?: "POLICY_VERBATIM" | "INFERRED_CONNECTIVE";
  title_origin?: string;
  actor_id: string;
  confidence: number;
  inference_reason?: string;
  source_reference_ids: string[];
  bpmn_type: string;
  path_outcome?: "APPROVED" | "REJECTED" | "PROHIBITED";
  color?: { stroke: string; fill: string };
  /** True when this step is a recommended control, not a policy obligation. */
  recommended?: boolean;
  /** Human-readable code: P-{chapter}-{step}-{element} e.g. P-5.3-007-A004 */
  step_code?: string;
};

export type GatewayBranch = {
  label: string;
  condition: string;
  target_step_id?: string;
  target_event_id?: string;
};

export type Gateway = {
  gateway_id: string;
  question: string;
  gateway_type: string;
  branches: GatewayBranch[];
  /** Human-readable code e.g. P-5.2-004-G001 */
  gateway_code?: string;
};

export type WorkflowEvent = {
  event_id: string;
  title: string;
  event_type?: "startEvent" | "endEvent" | string;
  next_step_id?: string;
  source_reference_ids?: string[];
  path_outcome?: "APPROVED" | "REJECTED" | "PROHIBITED" | null;
  color?: { stroke: string; fill: string } | string | null;
  /** Human-readable code e.g. P-5.2-001-E001 */
  event_code?: string;
};

export type HighLevelPhase = {
  phase: number | string;
  title: string;
  description: string;
  workflow_ids: string[];
};

export type Workflow = {
  workflow_id: string;
  workflow_title: string;
  workflow_summary?: string;
  /** Plain-text explanation of the policy purpose (overview only). */
  purpose?: string;
  /** Five-phase compliance lifecycle (overview only). */
  high_level_plan?: HighLevelPhase[];
  /** Recommended next-step controls for compliance owners (overview only). */
  recommendations?: string[];
  review_status?: ReviewStatus | string;
  overall_confidence: number;
  actors: Actor[];
  steps: WorkflowStep[];
  gateways: Gateway[];
  /** Canonical list used by the converter and the merged overview. */
  events?: WorkflowEvent[];
  start_event?: WorkflowEvent;
  end_events?: WorkflowEvent[];
  source_references: SourceReference[];
};

export type SelectedDetail =
  | { kind: "step"; data: WorkflowStep }
  | { kind: "gateway"; data: Gateway }
  | { kind: "event"; data: WorkflowEvent }
  | { kind: "phase"; data: HighLevelPhase }
  | null;

/** One occurrence of a repeated diagram label (across section workflows). */
export type DuplicateHit = {
  workflow_id: string;
  workflow_title: string;
  step_id: string;
  title: string;
  action_type: string;
  explicit_or_inferred: string;
  description: string;
  actor_name: string;
  path_outcome?: string | null;
};

export type DuplicateGroup = {
  key: string;
  label: string;
  hits: DuplicateHit[];
};

export type StatRow = {
  metric: string;
  value: string | number;
  note?: string;
};

export type LabelStatRow = {
  label: string;
  count: number;
  scope: string;
  detail: string;
};

export type WorkflowAnalysis = {
  summary: StatRow[];
  duplicatedWithin: LabelStatRow[];
  labelFrequency: LabelStatRow[];
  byActionType: StatRow[];
  byStepType: StatRow[];
  byOutcome: StatRow[];
  byActor: StatRow[];
  byReviewStatus: StatRow[];
  recommendations: string[];
};
