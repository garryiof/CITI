import { useEffect, useMemo, useRef, useState } from "react";
import BpmnModeler from "bpmn-js/lib/Modeler";
import {
  AlertTriangle,
  Check,
  ChevronRight,
  CircleHelp,
  Copy,
  ExternalLink,
  Focus,
  Info,
  LoaderCircle,
  PanelRightClose,
  PanelRightOpen,
  RotateCcw,
  Save,
  Search,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import type {
  DuplicateGroup,
  DuplicateHit,
  HighLevelPhase,
  LabelStatRow,
  ReviewStatus,
  SelectedDetail,
  SourceReference,
  StatRow,
  UserRole,
  Workflow,
  WorkflowAnalysis,
  WorkflowIndexItem,
} from "./types";

type CanvasService = {
  zoom: (value?: number | "fit-viewport") => number | void;
  addMarker: (elementId: string, marker: string) => void;
  removeMarker: (elementId: string, marker: string) => void;
  resized: () => void;
};

type EventBusService = {
  on: (event: string, callback: (event: { element?: { id?: string } }) => void) => void;
  off: (event: string, callback: (event: { element?: { id?: string } }) => void) => void;
};

const ROLE_STORAGE_KEY = "p2b-user-role";

/** Parse P-{chapter}-{step}-{element} into display segments. */
type CodeSegments = {
  policy: string;
  chapter: string;
  workflowStep: string;
  element: string;
  elementKind: string;
  elementKindLabel: string;
  raw: string;
};

const ELEMENT_KIND_LABELS: Record<string, string> = {
  A: "Action",
  G: "Gateway",
  E: "Event",
  R: "Reference",
};

const parsePolicyCode = (code: string): CodeSegments | null => {
  const match = code.trim().match(/^P-([^-]+)-(\d{3})-([AGER])(\d{3})$/i);
  if (!match) return null;
  const kind = match[3].toUpperCase();
  return {
    policy: "P",
    chapter: match[1],
    workflowStep: match[2],
    element: `${kind}${match[4]}`,
    elementKind: kind,
    elementKindLabel: ELEMENT_KIND_LABELS[kind] ?? kind,
    raw: code.trim(),
  };
};

/** Clickable black chip that explains P-{chapter}-{step}-{element} codification. */
const ElementCodeChip = ({
  code,
  fallbackId,
  policyHref,
}: {
  code?: string;
  fallbackId: string;
  policyHref?: string | null;
}) => {
  const [open, setOpen] = useState(false);
  const display = code || fallbackId;
  const segments = code ? parsePolicyCode(code) : null;

  return (
    <div className="code-chip-wrap">
      <button
        type="button"
        className={`element-id code-chip-btn${open ? " open" : ""}`}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        title="Explain this code"
      >
        {display}
      </button>
      {open && (
        <div className="code-explainer" role="region" aria-label="Code explanation">
          <div className="code-explainer-head">
            <strong>How this code is built</strong>
            <button
              type="button"
              className="code-explainer-close"
              onClick={() => setOpen(false)}
              aria-label="Close code explanation"
            >
              <X size={12} />
            </button>
          </div>
          <p className="code-explainer-pattern">
            Pattern: <code>P-{"{chapter}"}-{"{workflowStep}"}-{"{element}"}</code>
          </p>
          {segments ? (
            <table className="code-explainer-table">
              <tbody>
                <tr>
                  <th>P</th>
                  <td>Policy (fixed prefix — not a version number)</td>
                </tr>
                <tr>
                  <th>{segments.chapter}</th>
                  <td>Original chapter / subsection in the source policy</td>
                </tr>
                <tr>
                  <th>{segments.workflowStep}</th>
                  <td>Workflow step sequence in this diagram</td>
                </tr>
                <tr>
                  <th>{segments.element}</th>
                  <td>
                    {segments.elementKindLabel} element #
                    {segments.element.slice(1)} ({segments.elementKind} ={" "}
                    {segments.elementKindLabel.toLowerCase()})
                  </td>
                </tr>
              </tbody>
            </table>
          ) : (
            <p className="code-explainer-fallback">
              Machine id <code>{fallbackId}</code>
              {code ? ` — display code “${code}” could not be parsed.` : "."}
            </p>
          )}
          {policyHref && (
            <a
              className="code-explainer-policy"
              href={policyHref}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink size={12} aria-hidden="true" />
              Open original policy
            </a>
          )}
        </div>
      )}
    </div>
  );
};

const readStoredRole = (): UserRole => {
  const value = localStorage.getItem(ROLE_STORAGE_KEY);
  return value === "POLICY_OWNER" ? "POLICY_OWNER" : "VIEWER";
};

const normalizeStatus = (value: string | undefined): ReviewStatus =>
  value === "APPROVED" ? "APPROVED" : "PENDING";

const normalizeLabelKey = (value: string): string =>
  value.trim().toLowerCase().replace(/\s+/g, " ");

/** Build duplicate-label groups from a single workflow's steps. */
const buildDuplicateGroups = (workflow: Workflow): DuplicateGroup[] => {
  const buckets = new Map<string, DuplicateHit[]>();

  for (const step of workflow.steps) {
    const key = normalizeLabelKey(step.title);
    if (!key) continue;
    const hit: DuplicateHit = {
      workflow_id: workflow.workflow_id,
      workflow_title: workflow.workflow_title,
      step_id: step.step_id,
      title: step.title,
      action_type: step.action_type,
      explicit_or_inferred: step.explicit_or_inferred,
      description: step.description,
      actor_name:
        workflow.actors.find((actor) => actor.actor_id === step.actor_id)?.name ??
        step.actor_id,
      path_outcome: step.path_outcome ?? null,
    };
    const list = buckets.get(key) ?? [];
    list.push(hit);
    buckets.set(key, list);
  }

  return [...buckets.entries()]
    .filter(([, hits]) => hits.length > 1)
    .map(([key, hits]) => ({
      key,
      label: hits[0]?.title ?? key,
      hits,
    }))
    .sort((a, b) => b.hits.length - a.hits.length || a.label.localeCompare(b.label));
};

const countMapToRows = (
  counts: Map<string, number>,
  sortByValue = true,
): StatRow[] => {
  const entries = [...counts.entries()];
  entries.sort((a, b) =>
    sortByValue ? b[1] - a[1] || a[0].localeCompare(b[0]) : a[0].localeCompare(b[0]),
  );
  return entries.map(([metric, value]) => ({ metric, value }));
};

/** Analysis for a single workflow / diagram screen. */
const buildWorkflowAnalysis = (workflow: Workflow): WorkflowAnalysis => {
  const byActionType = new Map<string, number>();
  const byStepType = new Map<string, number>();
  const byOutcome = new Map<string, number>();
  const byActor = new Map<string, number>();
  const byLabel = new Map<string, { title: string; stepIds: string[] }>();

  for (const step of workflow.steps) {
    byActionType.set(
      step.action_type,
      (byActionType.get(step.action_type) ?? 0) + 1,
    );
    byStepType.set(
      step.explicit_or_inferred,
      (byStepType.get(step.explicit_or_inferred) ?? 0) + 1,
    );
    const outcome = step.path_outcome ?? "NEUTRAL";
    byOutcome.set(outcome, (byOutcome.get(outcome) ?? 0) + 1);
    const actor =
      workflow.actors.find((a) => a.actor_id === step.actor_id)?.name ??
      step.actor_id;
    byActor.set(actor, (byActor.get(actor) ?? 0) + 1);

    const key = normalizeLabelKey(step.title);
    if (!key) continue;
    const entry = byLabel.get(key) ?? { title: step.title, stepIds: [] };
    entry.stepIds.push(step.step_id);
    byLabel.set(key, entry);
  }

  const duplicatedWithin: LabelStatRow[] = buildDuplicateGroups(workflow).map(
    (group) => ({
      label: group.label,
      count: group.hits.length,
      scope: workflow.workflow_id,
      detail: group.hits.map((hit) => hit.step_id).join(", "),
    }),
  );

  const labelFrequency: LabelStatRow[] = [...byLabel.values()]
    .map((entry) => ({
      label: entry.title,
      count: entry.stepIds.length,
      scope: workflow.workflow_id,
      detail: entry.stepIds.join(", "),
    }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));

  const inferred = byStepType.get("INFERRED") ?? 0;
  const explicit = byStepType.get("EXPLICIT") ?? 0;
  const prohibited = byActionType.get("PROHIBITED_ACTION") ?? 0;
  const total = workflow.steps.length;
  const review = normalizeStatus(workflow.review_status);

  const summary: StatRow[] = [
    { metric: "Workflow ID", value: workflow.workflow_id },
    { metric: "Workflow name", value: workflow.workflow_title },
    { metric: "Total steps", value: total },
    {
      metric: "Explicit steps",
      value: explicit,
      note: "Policy-verbatim obligations",
    },
    {
      metric: "Inferred steps",
      value: inferred,
      note: "Connective steps added for readability",
    },
    {
      metric: "Inferred share",
      value: total === 0 ? "0%" : `${Math.round((inferred / total) * 100)}%`,
    },
    { metric: "Prohibited actions", value: prohibited },
    {
      metric: "Duplicate labels",
      value: duplicatedWithin.length,
      note: "Labels used more than once on this diagram",
    },
    {
      metric: "Unique labels",
      value: labelFrequency.length,
    },
    {
      metric: "Review status",
      value: review,
    },
    {
      metric: "Gateways",
      value: workflow.gateways.length,
    },
  ];

  const recommendations = [
    "Source grounding rate — % of steps with a linked policy paragraph / quote.",
    "Approval gate presence — whether this workflow has an Approved/Rejected decision.",
    "Deadline inventory — time-bound obligations in this workflow (e.g. 7 / 15 / 30 days).",
    "Control ownership — steps by actor vs expected RACI (Employee vs Legal & Compliance).",
    "Ambiguity / low-confidence queue — steps needing human confirmation before go-live.",
    "Exception paths — exception / escalation branches and who owns them.",
    "Review aging — days this workflow has remained PENDING since last regeneration.",
  ];

  return {
    summary,
    duplicatedWithin,
    labelFrequency,
    byActionType: countMapToRows(byActionType).map((row) => ({
      ...row,
      metric: String(row.metric).replaceAll("_", " "),
    })),
    byStepType: countMapToRows(byStepType),
    byOutcome: countMapToRows(byOutcome).map((row) => ({
      ...row,
      metric: String(row.metric).replaceAll("_", " "),
    })),
    byActor: countMapToRows(byActor),
    byReviewStatus: [{ metric: review, value: 1 }],
    recommendations,
  };
};

/* Read a color/font token from theme.css so the diagram renderer follows it. */
const themeVar = (name: string, fallback: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

export default function App() {
  const diagramHost = useRef<HTMLDivElement>(null);
  const viewer = useRef<BpmnModeler | null>(null);
  const [workflows, setWorkflows] = useState<WorkflowIndexItem[]>([]);
  const [activeId, setActiveId] = useState("PTP-PRECLEAR");
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [bpmnXml, setBpmnXml] = useState("");
  const [selected, setSelected] = useState<SelectedDetail>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dirty, setDirty] = useState(false);
  const [detailOpen, setDetailOpen] = useState(true);
  const [legendOpen, setLegendOpen] = useState(false);
  const [duplicatesOpen, setDuplicatesOpen] = useState(false);
  const [analyticsOpen, setAnalyticsOpen] = useState(false);
  const [selectedDuplicateKey, setSelectedDuplicateKey] = useState<string | null>(null);
  const [role, setRole] = useState<UserRole>(() => readStoredRole());
  const [statusSaving, setStatusSaving] = useState(false);
  const [overviewOpen, setOverviewOpen] = useState(false);
  const [saveNotice, setSaveNotice] = useState("");
  const [fileSaving, setFileSaving] = useState(false);

  useEffect(() => {
    // Let the grid settle, then tell bpmn-js its viewport size changed.
    const timer = window.setTimeout(() => {
      if (!viewer.current) return;
      const canvas = viewer.current.get("canvas") as CanvasService;
      canvas.resized();
    }, 50);
    return () => window.clearTimeout(timer);
  }, [detailOpen]);

  useEffect(() => {
    fetch("/index.json")
      .then((response) => {
        if (!response.ok) throw new Error("Could not load the workflow index.");
        return response.json() as Promise<WorkflowIndexItem[]>;
      })
      .then((items) => {
        setWorkflows(items);
        if (!items.some((item) => item.workflow_id === activeId) && items[0]) {
          setActiveId(items[0].workflow_id);
        }
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "Could not load workflows."),
      );
  }, []);

  useEffect(() => {
    const item = workflows.find((candidate) => candidate.workflow_id === activeId);
    if (!item) return;

    setLoading(true);
    setError("");
    setSelected(null);

    Promise.all([
      fetch(`/${item.json}`).then((response) => {
        if (!response.ok) throw new Error(`Could not load ${item.json}.`);
        return response.json() as Promise<Workflow>;
      }),
      fetch(`/${item.bpmn}`).then((response) => {
        if (!response.ok) throw new Error(`Could not load ${item.bpmn}.`);
        return response.text();
      }),
    ])
      .then(([workflowData, xml]) => {
        setWorkflow(workflowData);
        setBpmnXml(xml);
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "Could not load workflow."),
      )
      .finally(() => setLoading(false));
  }, [activeId, workflows]);

  useEffect(() => {
    if (!diagramHost.current || !bpmnXml || !workflow) return;

    viewer.current?.destroy();
    const instance = new BpmnModeler({
      container: diagramHost.current,
      bpmnRenderer: {
        defaultStrokeColor: themeVar("--color-bpmn-stroke", "#33423d"),
        defaultFillColor: themeVar("--color-bpmn-fill", "#fffef9"),
        defaultLabelColor: themeVar("--color-ink", "#17211f"),
      },
    });
    viewer.current = instance;
    setDirty(false);

    const handleClick = (event: { element?: { id?: string } }) => {
      const id = event.element?.id;
      if (!id) return;
      const step = workflow.steps.find((candidate) => candidate.step_id === id);
      if (step) {
        setSelected({ kind: "step", data: step });
        return;
      }
      const gateway = workflow.gateways.find(
        (candidate) => candidate.gateway_id === id,
      );
      if (gateway) {
        setSelected({ kind: "gateway", data: gateway });
        return;
      }
      const workflowEvent =
        workflow.events?.find((candidate) => candidate.event_id === id) ??
        (workflow.start_event?.event_id === id ? workflow.start_event : undefined) ??
        workflow.end_events?.find((candidate) => candidate.event_id === id);
      setSelected(workflowEvent ? { kind: "event", data: workflowEvent } : null);
    };

    const handleChanged = () => setDirty(true);

    instance
      .importXML(bpmnXml)
      .then(() => {
        const canvas = instance.get("canvas") as CanvasService;
        canvas.zoom("fit-viewport");
        workflow.steps
          .filter((step) => step.explicit_or_inferred === "INFERRED")
          .forEach((step) => canvas.addMarker(step.step_id, "inferred-node"));
        workflow.steps
          .filter((step) => step.action_type === "RECOMMENDED_ACTION" || step.recommended)
          .forEach((step) => canvas.addMarker(step.step_id, "recommended-node"));
        const eventBus = instance.get("eventBus") as EventBusService;
        eventBus.on("element.click", handleClick);
        eventBus.on("commandStack.changed", handleChanged);
      })
      .catch((reason: unknown) =>
        setError(
          reason instanceof Error ? reason.message : "The BPMN diagram could not render.",
        ),
      );

    return () => {
      try {
        const eventBus = instance.get("eventBus") as EventBusService;
        eventBus.off("element.click", handleClick);
        eventBus.off("commandStack.changed", handleChanged);
      } catch {
        // Viewer may already be destroyed during fast refresh.
      }
      instance.destroy();
      if (viewer.current === instance) viewer.current = null;
    };
  }, [bpmnXml, workflow]);

  const visibleWorkflows = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return workflows;
    return workflows.filter(
      (item) =>
        item.title.toLowerCase().includes(normalized) ||
        item.workflow_id.toLowerCase().includes(normalized),
    );
  }, [query, workflows]);

  const duplicateGroups = useMemo(
    () => (workflow ? buildDuplicateGroups(workflow) : []),
    [workflow],
  );

  const selectedDuplicateGroup = useMemo(
    () => duplicateGroups.find((group) => group.key === selectedDuplicateKey) ?? null,
    [duplicateGroups, selectedDuplicateKey],
  );

  // Keep the selected duplicate row valid when switching diagrams.
  useEffect(() => {
    if (!duplicateGroups.some((group) => group.key === selectedDuplicateKey)) {
      setSelectedDuplicateKey(duplicateGroups[0]?.key ?? null);
    }
  }, [duplicateGroups, selectedDuplicateKey]);

  const analytics = useMemo(
    () => (workflow ? buildWorkflowAnalysis(workflow) : null),
    [workflow],
  );

  const openDuplicatesPanel = () => {
    setLegendOpen(false);
    setAnalyticsOpen(false);
    setDuplicatesOpen(true);
    setSelectedDuplicateKey(duplicateGroups[0]?.key ?? null);
  };

  const openAnalyticsPanel = () => {
    setLegendOpen(false);
    setDuplicatesOpen(false);
    setAnalyticsOpen(true);
  };

  const jumpToDuplicate = (hit: DuplicateHit) => {
    if (!workflow) return;
    const step = workflow.steps.find((candidate) => candidate.step_id === hit.step_id);
    if (!step) return;
    setSelected({ kind: "step", data: step });
    setDetailOpen(true);
    setDuplicatesOpen(false);
  };

  const activeIndex = workflows.find((item) => item.workflow_id === activeId);
  const isOverview = workflow?.workflow_id === "PTP-POLICY" && !!workflow.high_level_plan;
  const explicitCount =
    workflow?.steps.filter((step) => step.explicit_or_inferred === "EXPLICIT")
      .length ?? 0;
  const inferredCount = (workflow?.steps.length ?? 0) - explicitCount;

  const reviewStatus: ReviewStatus = workflow
    ? normalizeStatus(workflow.review_status)
    : "PENDING";
  const canApprove = role === "POLICY_OWNER";

  const setUserRole = (next: UserRole) => {
    setRole(next);
    localStorage.setItem(ROLE_STORAGE_KEY, next);
  };

  const setReviewStatus = async (next: ReviewStatus) => {
    if (!workflow || !canApprove || statusSaving) return;
    const previous = normalizeStatus(workflow.review_status);
    if (previous === next) return;

    // Optimistic UI update, then persist to outputs/<id>.json via the local API.
    setWorkflow((current) =>
      current ? { ...current, review_status: next } : current,
    );
    setStatusSaving(true);
    try {
      const response = await fetch("/api/review-status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workflow_id: workflow.workflow_id,
          review_status: next,
        }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as {
          error?: string;
        } | null;
        throw new Error(payload?.error ?? "Could not update review status.");
      }
    } catch (reason: unknown) {
      setWorkflow((current) =>
        current ? { ...current, review_status: previous } : current,
      );
      setError(
        reason instanceof Error ? reason.message : "Could not update review status.",
      );
    } finally {
      setStatusSaving(false);
    }
  };

  const referenceFor = (referenceId: string): SourceReference | undefined =>
    workflow?.source_references.find((ref) => ref.reference_id === referenceId);

  const zoom = (direction: 1 | -1) => {
    if (!viewer.current) return;
    const canvas = viewer.current.get("canvas") as CanvasService;
    const current = canvas.zoom() as number;
    canvas.zoom(Math.max(0.2, Math.min(4, current + direction * 0.15)));
  };

  const showSaved = (message: string) => {
    setSaveNotice(message);
    window.setTimeout(() => setSaveNotice(""), 2200);
  };

  const saveToOutputs = async (kind: "bpmn" | "json", content: string) => {
    const response = await fetch("/api/save-workflow", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        workflow_id: activeId,
        kind,
        content,
      }),
    });
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as {
        error?: string;
      } | null;
      throw new Error(payload?.error ?? `Could not save ${kind.toUpperCase()} file.`);
    }
    const result = (await response.json()) as { path?: string };
    return result.path ?? `outputs/${activeId}.${kind}`;
  };

  /** Save both diagram (.bpmn) and structured data (.json) into outputs/. */
  const saveLayout = async () => {
    if (!viewer.current || !workflow || fileSaving) return;
    setFileSaving(true);
    setError("");
    try {
      const { xml } = await viewer.current.saveXML({ format: true });
      if (!xml) throw new Error("Could not export the diagram.");
      const jsonContent = `${JSON.stringify(workflow, null, 2)}\n`;
      const [bpmnPath, jsonPath] = await Promise.all([
        saveToOutputs("bpmn", xml),
        saveToOutputs("json", jsonContent),
      ]);
      setBpmnXml(xml);
      setDirty(false);
      showSaved(`Saved ${bpmnPath} and ${jsonPath}`);
    } catch (reason: unknown) {
      setError(
        reason instanceof Error ? reason.message : "Could not save layout files.",
      );
    } finally {
      setFileSaving(false);
    }
  };

  const resetLayout = () => {
    // Re-importing the original XML discards all layout changes.
    if (!viewer.current || !workflow) return;
    viewer.current
      .importXML(bpmnXml)
      .then(() => {
        const canvas = viewer.current!.get("canvas") as CanvasService;
        canvas.zoom("fit-viewport");
        workflow.steps
          .filter((step) => step.explicit_or_inferred === "INFERRED")
          .forEach((step) => canvas.addMarker(step.step_id, "inferred-node"));
        workflow.steps
          .filter((step) => step.action_type === "RECOMMENDED_ACTION" || step.recommended)
          .forEach((step) => canvas.addMarker(step.step_id, "recommended-node"));
        setDirty(false);
        setSelected(null);
      })
      .catch(() => setError("Could not reset the diagram layout."));
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <div>
            <p className="eyebrow">Policy intelligence / worfklow review</p>
            <h1>BlackRock Personal Trading Policy</h1>
          </div>
        </div>
        <div className="header-status">
          <label className="role-switch">
            <span>Role</span>
            <select
              value={role}
              onChange={(event) => setUserRole(event.target.value as UserRole)}
              aria-label="Active user role"
            >
              <option value="VIEWER">Viewer</option>
              <option value="POLICY_OWNER">Policy owner</option>
            </select>
          </label>
          <span className="separator" />
          <span className="status-dot" />
          <span>Local workspace</span>
          <span className="separator" />
          <span>{workflows.length} workflows</span>
        </div>
      </header>

      <div className={`workspace ${detailOpen ? "" : "detail-collapsed"}`}>
        <aside className="workflow-rail">
          <div className="rail-heading">
            <div>
              <p className="section-kicker">Process repository</p>
              <h2>Workflows</h2>
            </div>
            <span className="count-badge">{workflows.length}</span>
          </div>

          <label className="search-box">
            <Search size={15} aria-hidden="true" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter workflows"
              aria-label="Filter workflows"
            />
          </label>

          <nav className="workflow-list" aria-label="Policy workflows">
            {visibleWorkflows.map((item, index) => (
              <button
                className={`workflow-item ${item.workflow_id === activeId ? "active" : ""}`}
                key={item.workflow_id}
                onClick={() => setActiveId(item.workflow_id)}
              >
                <span className="workflow-number">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="workflow-copy">
                  <strong>{item.title}</strong>
                  <small>
                    {item.steps} actions{/*·{Math.round(item.confidence * 100)}%*/}
                  </small>
                </span>
                <ChevronRight size={15} aria-hidden="true" />
              </button>
            ))}
          </nav>
        </aside>

        <section className="diagram-panel">
          <div className="diagram-heading">
            <div className="diagram-title">
              <div className="id-row">
                <span>{workflow?.workflow_id ?? "—"}</span>
                {canApprove && workflow ? (
                  <label className="review-status-control">
                    <span className="visually-hidden">Review status</span>
                    <select
                      className={`review-pill editable status-${reviewStatus.toLowerCase()}`}
                      value={reviewStatus}
                      disabled={statusSaving}
                      onChange={(event) =>
                        void setReviewStatus(event.target.value as ReviewStatus)
                      }
                      aria-label="Set review status"
                    >
                      <option value="PENDING">PENDING</option>
                      <option value="APPROVED">APPROVED</option>
                    </select>
                  </label>
                ) : (
                  <span
                    className={`review-pill status-${reviewStatus.toLowerCase()}`}
                  >
                    {workflow ? reviewStatus : "Loading"}
                  </span>
                )}
              </div>
              <h2>{workflow?.workflow_title ?? "Loading workflow…"}</h2>
              <p>{workflow?.workflow_summary}</p>
            </div>

            <div className="diagram-actions">
              <div className="zoom-group">
                <button
                  className={analyticsOpen ? "active" : ""}
                  onClick={() => {
                    if (analyticsOpen) {
                      setAnalyticsOpen(false);
                      return;
                    }
                    openAnalyticsPanel();
                  }}
                  title="Workflow statistics and recommended compliance metrics"
                  aria-label="Open workflow analysis"
                >
                  <CircleHelp size={17} />
                </button>
                <button
                  className={duplicatesOpen ? "active" : ""}
                  onClick={() => {
                    if (duplicatesOpen) {
                      setDuplicatesOpen(false);
                      return;
                    }
                    openDuplicatesPanel();
                  }}
                  title="Search duplicated step labels on this diagram"
                  aria-label="Search duplicated step labels on this diagram"
                >
                  <Copy size={17} />
                </button>
                <button
                  className={legendOpen ? "active" : ""}
                  onClick={() => {
                    setDuplicatesOpen(false);
                    setAnalyticsOpen(false);
                    setLegendOpen((open) => !open);
                  }}
                  title="Explain the diagram legend"
                  aria-label="Explain the diagram legend"
                >
                  <Info size={17} />
                </button>
                <button onClick={() => zoom(-1)} title="Zoom out" aria-label="Zoom out">
                  <ZoomOut size={17} />
                </button>
                <button onClick={() => zoom(1)} title="Zoom in" aria-label="Zoom in">
                  <ZoomIn size={17} />
                </button>
                <button
                  onClick={() =>
                    (viewer.current?.get("canvas") as CanvasService | undefined)?.zoom(
                      "fit-viewport",
                    )
                  }
                  title="Fit diagram"
                  aria-label="Fit diagram"
                >
                  <Focus size={17} />
                </button>
              </div>
              <button
                className="export-button"
                onClick={resetLayout}
                disabled={!dirty}
                title="Reset layout to the generated arrangement"
              >
                <RotateCcw size={16} />
                Reset
              </button>
              <button
                className="export-button"
                onClick={() => void saveLayout()}
                disabled={!bpmnXml || !workflow || fileSaving}
                title="Save diagram (.bpmn) and workflow data (.json) to outputs/"
              >
                <Save size={16} />
                {fileSaving ? "Saving…" : "Save layout"}
              </button>
            </div>
            {saveNotice && <p className="save-notice">{saveNotice}</p>}
          </div>

          {isOverview && workflow && (
            <>
              {/* Compact always-visible bar: toggle + phase pill strip */}
              <div className="overview-bar">
                <button
                  className={`overview-toggle${overviewOpen ? " open" : ""}`}
                  onClick={() => setOverviewOpen((o) => !o)}
                  aria-expanded={overviewOpen}
                  title={overviewOpen ? "Collapse policy overview" : "Expand policy overview"}
                >
                  <ChevronRight size={13} aria-hidden="true" />
                  Overview
                </button>
                <div className="overview-bar-phases">
                  {workflow.high_level_plan?.map((phase: HighLevelPhase) => (
                    <button
                      key={phase.phase}
                      className={`overview-phase-pill${
                        selected?.kind === "phase" && selected.data.phase === phase.phase
                          ? " active"
                          : ""
                      }`}
                      onClick={() => {
                        setSelected({ kind: "phase", data: phase });
                        setDetailOpen(true);
                      }}
                      title={phase.description}
                    >
                      {phase.phase}. {phase.title}
                    </button>
                  ))}
                </div>
              </div>

              {/* Collapsible drawer */}
              {overviewOpen && (
                <div className="policy-overview">
                  {/* Purpose */}
                  {workflow.purpose && (
                    <div className="overview-purpose">
                      <span className="overview-purpose-kicker">Policy purpose</span>
                      <p>{workflow.purpose}</p>
                    </div>
                  )}

                  {/* Full phase cards */}
                  {workflow.high_level_plan && workflow.high_level_plan.length > 0 && (
                    <div className="overview-phases">
                      <span className="overview-phases-heading">Compliance lifecycle — 5 phases</span>
                      <div className="overview-phase-list">
                        {workflow.high_level_plan.map((phase: HighLevelPhase) => (
                          <div
                            className={`phase-card${
                              selected?.kind === "phase" && selected.data.phase === phase.phase
                                ? " active"
                                : ""
                            }`}
                            key={phase.phase}
                            onClick={() => {
                              setSelected({ kind: "phase", data: phase });
                              setDetailOpen(true);
                            }}
                            role="button"
                            tabIndex={0}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                setSelected({ kind: "phase", data: phase });
                                setDetailOpen(true);
                              }
                            }}
                            title={`Select phase ${phase.phase} to view details`}
                          >
                            <span className="phase-card-num">Phase {phase.phase}</span>
                            <p className="phase-card-title">{phase.title}</p>
                            <p className="phase-card-desc">{phase.description}</p>
                            <div className="phase-card-ids">
                              {phase.workflow_ids.map((wid) => (
                                <button
                                  key={wid}
                                  className="phase-id-chip"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setActiveId(wid);
                                  }}
                                  title={`Open ${wid} workflow`}
                                >
                                  {wid}
                                </button>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Recommendations */}
                  {workflow.recommendations && workflow.recommendations.length > 0 && (
                    <div className="overview-recommendations">
                      <div className="overview-rec-card">
                        <p className="overview-rec-heading">Recommended next steps</p>
                        <ol className="overview-rec-list">
                          {workflow.recommendations.map((rec) => (
                            <li key={rec}>{rec}</li>
                          ))}
                        </ol>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          <div className="diagram-stage">
            {loading && (
              <div className="stage-state">
                <LoaderCircle className="spin" size={23} />
                <span>Rendering process model</span>
              </div>
            )}
            {error && (
              <div className="stage-state error">
                <AlertTriangle size={22} />
                <span>{error}</span>
              </div>
            )}
            <div ref={diagramHost} className="bpmn-canvas" />
            {legendOpen && (
              <div className="legend-panel" role="dialog" aria-label="Diagram legend">
                <div className="legend-panel-head">
                  <h3>Diagram legend</h3>
                  <button
                    onClick={() => setLegendOpen(false)}
                    title="Close legend"
                    aria-label="Close legend"
                  >
                    <X size={14} />
                  </button>
                </div>
                <p className="legend-panel-intro">
                  How to read the process model extracted from the policy.
                </p>

                <section>
                  <h4>Extraction markers</h4>
                  <ul>
                    <li>
                      <i className="chip chip-explicit" />
                      <div>
                        <strong>Policy explicit</strong>
                        <span>
                          The action is stated verbatim in the policy and is linked to
                          its exact source paragraph.
                        </span>
                      </div>
                    </li>
                    <li>
                      <i className="chip chip-inferred" />
                      <div>
                        <strong>Inferred connector</strong>
                        <span>
                          A connective step added to make the flow readable. It is not a
                          policy obligation.
                        </span>
                      </div>
                    </li>
                    <li>
                      <i className="chip chip-approved" />
                      <div>
                        <strong>Approved path</strong>
                        <span>
                          Steps and relations that follow the “Approved” outcome of a
                          decision — the activity may proceed.
                        </span>
                      </div>
                    </li>
                    <li>
                      <i className="chip chip-rejected" />
                      <div>
                        <strong>Rejected path</strong>
                        <span>
                          The flow that follows a “Rejected” outcome — the activity must
                          not proceed.
                        </span>
                      </div>
                    </li>
                    <li>
                      <i className="chip chip-prohibited" />
                      <div>
                        <strong>Prohibited action</strong>
                        <span>
                          A policy prohibition modeled as a negative outcome (orange). The
                          activity must not be performed; the path ends at “Must not
                          proceed — prohibited by policy.”
                        </span>
                      </div>
                    </li>
                  
                    <li>
                      <i className="chip chip-recommended" />
                      <div>
                        <strong>Recommended control</strong>
                        <span>
                          A suggested automation control (teal dashed). Not a policy
                          obligation — surfaced to improve evidence completeness and
                          reduce manual compliance effort.
                        </span>
                      </div>
                    </li>
                  </ul>
                </section>

                <section>
                  <h4>BPMN elements</h4>
                  <ul>
                    <li>
                      <i className="glyph glyph-task" />
                      <div>
                        <strong>Task</strong>
                        <span>
                          A single action performed by the actor named in the element,
                          such as submitting a request or reviewing a trade.
                        </span>
                      </div>
                    </li>
                    <li>
                      <i className="glyph glyph-gateway" />
                      <div>
                        <strong>Gateway</strong>
                        <span>
                          A decision point phrased as a question. Each outgoing branch is
                          labeled with its outcome (e.g. Approved / Rejected).
                        </span>
                      </div>
                    </li>
                    <li>
                      <i className="glyph glyph-start" />
                      <div>
                        <strong>Start event</strong>
                        <span>The trigger that begins the workflow (thin circle).</span>
                      </div>
                    </li>
                    <li>
                      <i className="glyph glyph-end" />
                      <div>
                        <strong>End event</strong>
                        <span>
                          A possible outcome where the workflow finishes (thick circle).
                        </span>
                      </div>
                    </li>
                    <li>
                      <i className="glyph glyph-flow" />
                      <div>
                        <strong>Sequence flow</strong>
                        <span>
                          The order in which steps occur, read from left to right.
                        </span>
                      </div>
                    </li>
                  </ul>
                </section>
              </div>
            )}

            {duplicatesOpen && (
              <div
                className="duplicates-panel"
                role="dialog"
                aria-label="Duplicated step labels"
              >
                <div className="legend-panel-head">
                  <h3>Duplicated step labels</h3>
                  <button
                    onClick={() => setDuplicatesOpen(false)}
                    title="Close duplicates"
                    aria-label="Close duplicates"
                  >
                    <X size={14} />
                  </button>
                </div>

                {duplicateGroups.length === 0 ? (
                  <p className="duplicates-empty">
                    No duplicated steps found for the workflow{" "}
                    {workflow?.workflow_title ?? activeId}
                  </p>
                ) : (
                  <>
                    <p className="legend-panel-intro">
                      Steps on this diagram that share the same label. Select a row to
                      compare them side by side.
                    </p>

                    <div className="duplicates-table-wrap">
                      <table className="duplicates-table">
                        <thead>
                          <tr>
                            <th>Shared label</th>
                            <th>Count</th>
                            <th>Step IDs</th>
                          </tr>
                        </thead>
                        <tbody>
                          {duplicateGroups.map((group) => (
                            <tr
                              key={group.key}
                              className={
                                selectedDuplicateKey === group.key ? "selected" : ""
                              }
                              onClick={() => setSelectedDuplicateKey(group.key)}
                            >
                              <td>{group.label}</td>
                              <td>{group.hits.length}</td>
                              <td>
                                <span className="dup-diagrams">
                                  {group.hits.map((hit) => hit.step_id).join(", ")}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {selectedDuplicateGroup && (
                      <section className="duplicates-compare">
                        <h4>
                          Side-by-side compare
                          <span>
                            {selectedDuplicateGroup.hits.length} occurrences
                          </span>
                        </h4>
                        <div className="compare-scroll">
                          <table className="compare-table">
                            <thead>
                              <tr>
                                <th className="compare-attr">Attribute</th>
                                {selectedDuplicateGroup.hits.map((hit) => (
                                  <th key={hit.step_id}>
                                    <span className="compare-col-id">{hit.step_id}</span>
                                    <button
                                      type="button"
                                      className="compare-jump"
                                      onClick={() => jumpToDuplicate(hit)}
                                      title={`Select ${hit.step_id} on this diagram`}
                                    >
                                      Select
                                      <ChevronRight size={12} />
                                    </button>
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {(
                                [
                                  ["Step ID", (h: DuplicateHit) => h.step_id],
                                  ["Label", (h: DuplicateHit) => h.title],
                                  [
                                    "Classification",
                                    (h: DuplicateHit) =>
                                      h.action_type.replaceAll("_", " "),
                                  ],
                                  [
                                    "Step type",
                                    (h: DuplicateHit) => h.explicit_or_inferred,
                                  ],
                                  ["Actor", (h: DuplicateHit) => h.actor_name],
                                  [
                                    "Outcome",
                                    (h: DuplicateHit) =>
                                      h.path_outcome?.replaceAll("_", " ") ?? "—",
                                  ],
                                  [
                                    "Policy wording",
                                    (h: DuplicateHit) => h.description || "—",
                                  ],
                                ] as const
                              ).map(([attr, getter]) => (
                                <tr key={attr}>
                                  <th className="compare-attr">{attr}</th>
                                  {selectedDuplicateGroup.hits.map((hit) => (
                                    <td key={`${attr}-${hit.step_id}`}>{getter(hit)}</td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </section>
                    )}
                  </>
                )}
              </div>
            )}

            {analyticsOpen && analytics && (
              <div
                className="duplicates-panel analytics-panel"
                role="dialog"
                aria-label="Workflow analysis"
              >
                <div className="legend-panel-head">
                  <h3>Workflow analysis</h3>
                  <button
                    onClick={() => setAnalyticsOpen(false)}
                    title="Close analysis"
                    aria-label="Close analysis"
                  >
                    <X size={14} />
                  </button>
                </div>
                <p className="legend-panel-intro">
                  Structured statistics for{" "}
                  <strong>{workflow?.workflow_title ?? activeId}</strong> — duplicated
                  labels, label frequency, and compliance distribution metrics on this
                  diagram.
                </p>

                <div className="analytics-body">
                    <section className="analytics-section">
                      <h4>1. Executive summary</h4>
                      <div className="duplicates-table-wrap analytics-table-wrap">
                        <table className="duplicates-table">
                          <thead>
                            <tr>
                              <th>Metric</th>
                              <th>Value</th>
                              <th>Note</th>
                            </tr>
                          </thead>
                          <tbody>
                            {analytics.summary.map((row) => (
                              <tr key={row.metric}>
                                <td>{row.metric}</td>
                                <td>{row.value}</td>
                                <td>
                                  <span className="dup-diagrams">{row.note ?? "—"}</span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </section>

                    <section className="analytics-section">
                      <h4>2. Duplicated labels</h4>
                      <p className="analytics-blurb">
                        Same step label appears more than once on this workflow —
                        often generic titles that need sharper wording.
                      </p>
                      <div className="duplicates-table-wrap analytics-table-wrap">
                        <table className="duplicates-table">
                          <thead>
                            <tr>
                              <th>Label</th>
                              <th>Count</th>
                              <th>Step IDs</th>
                            </tr>
                          </thead>
                          <tbody>
                            {analytics.duplicatedWithin.length === 0 ? (
                              <tr>
                                <td colSpan={3}>
                                  No duplicated steps found for the workflow{" "}
                                  {workflow?.workflow_title ?? activeId}
                                </td>
                              </tr>
                            ) : (
                              analytics.duplicatedWithin.map((row) => (
                                <tr key={`${row.scope}-${row.label}`}>
                                  <td>{row.label}</td>
                                  <td>{row.count}</td>
                                  <td>
                                    <span className="dup-diagrams">{row.detail}</span>
                                  </td>
                                </tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </div>
                    </section>

                    <section className="analytics-section">
                      <h4>3. Label frequency</h4>
                      <p className="analytics-blurb">
                        How often each business-readable label appears on this workflow.
                      </p>
                      <div className="duplicates-table-wrap analytics-table-wrap">
                        <table className="duplicates-table">
                          <thead>
                            <tr>
                              <th>Label</th>
                              <th>Count</th>
                              <th>Step IDs</th>
                            </tr>
                          </thead>
                          <tbody>
                            {analytics.labelFrequency.map((row) => (
                              <tr key={row.label}>
                                <td>{row.label}</td>
                                <td>{row.count}</td>
                                <td>
                                  <span className="dup-diagrams">{row.detail}</span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </section>

                    <div className="analytics-grid">
                      <section className="analytics-section">
                        <h4>4. By classification</h4>
                        <div className="duplicates-table-wrap analytics-table-wrap">
                          <table className="duplicates-table">
                            <thead>
                              <tr>
                                <th>Action type</th>
                                <th>Steps</th>
                              </tr>
                            </thead>
                            <tbody>
                              {analytics.byActionType.map((row) => (
                                <tr key={row.metric}>
                                  <td>{row.metric}</td>
                                  <td>{row.value}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </section>

                      <section className="analytics-section">
                        <h4>5. By step type</h4>
                        <div className="duplicates-table-wrap analytics-table-wrap">
                          <table className="duplicates-table">
                            <thead>
                              <tr>
                                <th>Step type</th>
                                <th>Steps</th>
                              </tr>
                            </thead>
                            <tbody>
                              {analytics.byStepType.map((row) => (
                                <tr key={row.metric}>
                                  <td>{row.metric}</td>
                                  <td>{row.value}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </section>

                      <section className="analytics-section">
                        <h4>6. By path outcome</h4>
                        <div className="duplicates-table-wrap analytics-table-wrap">
                          <table className="duplicates-table">
                            <thead>
                              <tr>
                                <th>Outcome</th>
                                <th>Steps</th>
                              </tr>
                            </thead>
                            <tbody>
                              {analytics.byOutcome.map((row) => (
                                <tr key={row.metric}>
                                  <td>{row.metric}</td>
                                  <td>{row.value}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </section>

                      <section className="analytics-section">
                        <h4>7. By actor</h4>
                        <div className="duplicates-table-wrap analytics-table-wrap">
                          <table className="duplicates-table">
                            <thead>
                              <tr>
                                <th>Actor</th>
                                <th>Steps</th>
                              </tr>
                            </thead>
                            <tbody>
                              {analytics.byActor.map((row) => (
                                <tr key={row.metric}>
                                  <td>{row.metric}</td>
                                  <td>{row.value}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </section>

                      <section className="analytics-section">
                        <h4>8. Review status</h4>
                        <div className="duplicates-table-wrap analytics-table-wrap">
                          <table className="duplicates-table">
                            <thead>
                              <tr>
                                <th>Status</th>
                                <th>Count</th>
                              </tr>
                            </thead>
                            <tbody>
                              {analytics.byReviewStatus.map((row) => (
                                <tr key={row.metric}>
                                  <td>{row.metric}</td>
                                  <td>{row.value}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </section>
                    </div>

                    <section className="analytics-section">
                      <h4>9. Recommended additional statistics</h4>
                      <p className="analytics-blurb">
                        Useful next metrics for business owners and compliance officers —
                        not computed yet, recommended for a future control dashboard.
                      </p>
                      <ol className="analytics-recommendations">
                        {analytics.recommendations.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ol>
                    </section>
                </div>
              </div>
            )}
          </div>

          {dirty && (
            <div className="stage-bar">
              <div className="layout-badge">
                Layout edited — Save layout to keep it
              </div>
            </div>
          )}

          <footer className="diagram-footer">
            <div>
              <span className="footer-label">Model integrity</span>
              <strong><Check size={14} /> {activeIndex?.validation_errors ?? 0} validation errors</strong>
            </div>
            <div>
              <span className="footer-label">Actions</span>
              <strong>{explicitCount} explicit / {inferredCount} inferred</strong>
            </div>
          </footer>
        </section>

        {!detailOpen && (
          <aside className="detail-rail">
            <button
              className="panel-toggle"
              onClick={() => setDetailOpen(true)}
              title="Show element detail"
              aria-label="Show element detail"
            >
              <PanelRightOpen size={16} />
            </button>
            <span className="rail-label">Element detail</span>
          </aside>
        )}

        {detailOpen && (
        <aside className="detail-panel">
          <div className="detail-heading">
            <div>
              <p className="section-kicker">Traceability</p>
              <h2>Element detail</h2>
            </div>
            <button
              className="panel-toggle"
              onClick={() => setDetailOpen(false)}
              title="Hide element detail"
              aria-label="Hide element detail"
            >
              <PanelRightClose size={16} />
            </button>
          </div>

          {!selected && (
            <div className="empty-detail">
              <div className="empty-glyph"><Focus size={22} /></div>
              {isOverview ? (
                <>
                  <h3>Select an element</h3>
                  <p>
                    Click a phase pill at the top to read the compliance phase
                    description, or click any step or event in the diagram below.
                  </p>
                </>
              ) : (
                <>
                  <h3>Select a diagram element</h3>
                  <p>
                    Choose a start point, task, decision, or end point to inspect its
                    details.
                  </p>
                </>
              )}
            </div>
          )}

          {selected?.kind === "step" && (
            <div className="detail-content">
              <div className="detail-title-block">
                <div className="detail-origin-row">
                  <ElementCodeChip
                    code={selected.data.step_code}
                    fallbackId={selected.data.step_id}
                    policyHref={(() => {
                      const firstRef = referenceFor(
                        selected.data.source_reference_ids[0] ?? "",
                      );
                      return firstRef?.anchor
                        ? `/${firstRef.source_html ?? "policy_source.html"}#${firstRef.anchor}`
                        : null;
                    })()}
                  />
                  {(selected.data.action_type === "PROHIBITED_ACTION" ||
                    selected.data.path_outcome === "PROHIBITED") && (
                    <span className="wording-origin prohibited">
                      Prohibited — negative outcome
                    </span>
                  )}
                </div>
                <span className="detail-wording-label">Business-readable label</span>
                {(() => {
                  const firstRef = referenceFor(
                    selected.data.source_reference_ids[0] ?? "",
                  );
                  if (firstRef?.anchor) {
                    return (
                      <h3>
                        <a
                          className="policy-jump"
                          href={`/${firstRef.source_html ?? "policy_source.html"}#${firstRef.anchor}`}
                          target="_blank"
                          rel="noreferrer"
                          title="Open the original policy with this paragraph highlighted"
                        >
                          {selected.data.title}
                          <ExternalLink size={13} aria-hidden="true" />
                        </a>
                      </h3>
                    );
                  }
                  return <h3>{selected.data.title}</h3>;
                })()}
                <span className="detail-wording-label">
                  {selected.data.wording_origin === "POLICY_VERBATIM"
                    ? "Complete policy wording"
                    : "Inferred workflow explanation"}
                </span>
                <p className="complete-wording">{selected.data.description}</p>
                {selected.data.action_phrase &&
                  selected.data.action_phrase !== selected.data.description && (
                    <div className="atomic-phrase">
                      <span>Atomic action phrase</span>
                      <p>{selected.data.action_phrase}</p>
                    </div>
                  )}
              </div>

              {(selected.data.action_type === "PROHIBITED_ACTION" ||
                selected.data.path_outcome === "PROHIBITED") && (
                <section className="prohibition-note">
                  <span>Prohibited action — negative outcome</span>
                  <p>
                    This element models a policy prohibition shown in orange. The
                    activity must not be performed; it is a negative outcome, not an
                    approval or rejection decision.
                  </p>
                </section>
              )}

              <dl className="attribute-grid">
                <div>
                  <dt>Classification</dt>
                  <dd
                    className={
                      selected.data.action_type === "PROHIBITED_ACTION"
                        ? "prohibited"
                        : undefined
                    }
                  >
                    {selected.data.action_type.replaceAll("_", " ")}
                  </dd>
                </div>
                <div>
                  <dt>Outcome</dt>
                  <dd
                    className={
                      selected.data.path_outcome === "PROHIBITED"
                        ? "prohibited"
                        : selected.data.path_outcome === "APPROVED"
                          ? "explicit"
                          : selected.data.path_outcome === "REJECTED"
                            ? "inferred"
                            : undefined
                    }
                  >
                    {selected.data.path_outcome === "PROHIBITED"
                      ? "Prohibited (must not proceed)"
                      : selected.data.path_outcome?.replaceAll("_", " ") ?? "Neutral"}
                  </dd>
                </div>
                <div>
                  <dt>Step type</dt>
                  <dd className={selected.data.explicit_or_inferred.toLowerCase()}>
                    {selected.data.explicit_or_inferred}
                  </dd>
                </div>
                <div>
                  <dt>Actor</dt>
                  <dd>
                    {workflow?.actors.find(
                      (actor) => actor.actor_id === selected.data.actor_id,
                    )?.name ?? selected.data.actor_id}
                  </dd>
                </div>
              </dl>

              <section className="source-section">
                <div className="source-title">
                  <span>Policy evidence</span>
                  <span>{selected.data.source_reference_ids.length} reference</span>
                </div>
                {selected.data.source_reference_ids.map((referenceId) => {
                  const reference = referenceFor(referenceId);
                  if (!reference) return null;
                  return (
                    <article className="source-card" key={reference.reference_id}>
                      <div className="source-meta">
                        <span>§ {reference.section_id}</span>
                        <span>¶ {reference.paragraph}</span>
                        <span>{reference.reference_id}</span>
                      </div>
                      <h4>{reference.section_title}</h4>
                      <blockquote>“{reference.quoted_text}”</blockquote>
                      {reference.anchor && (
                        <a
                          className="view-in-policy"
                          href={`/${reference.source_html ?? "policy_source.html"}#${reference.anchor}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          <ExternalLink size={12} aria-hidden="true" />
                          View in original policy
                        </a>
                      )}
                    </article>
                  );
                })}
              </section>
            </div>
          )}

          {selected?.kind === "gateway" && (
            <div className="detail-content">
              <div className="detail-title-block">
                <div className="detail-origin-row">
                  <ElementCodeChip
                    code={selected.data.gateway_code}
                    fallbackId={selected.data.gateway_id}
                  />
                </div>
                <h3>{selected.data.question}</h3>
                <p>An exclusive policy decision with labeled outcomes.</p>
              </div>
              <section className="branch-section">
                <span>Decision branches</span>
                {selected.data.branches.map((branch) => (
                  <div className="branch-row" key={`${branch.label}-${branch.condition}`}>
                    <strong>{branch.label}</strong>
                    <code>{branch.condition}</code>
                  </div>
                ))}
              </section>
            </div>
          )}

          {selected?.kind === "event" && (
            <div className="detail-content">
              <div className="detail-title-block">
                <div className="detail-origin-row">
                  <ElementCodeChip
                    code={selected.data.event_code}
                    fallbackId={selected.data.event_id}
                    policyHref={(() => {
                      if (selected.data.event_type !== "startEvent") return null;
                      const firstRef = referenceFor(
                        selected.data.source_reference_ids?.[0] ?? "",
                      );
                      return firstRef?.anchor
                        ? `/${firstRef.source_html ?? "policy_source.html"}#${firstRef.anchor}`
                        : null;
                    })()}
                  />
                  {selected.data.path_outcome === "PROHIBITED" ? (
                    <span className="wording-origin prohibited">
                      Prohibited — negative outcome
                    </span>
                  ) : (
                    <span
                      className={`wording-origin ${
                        selected.data.event_type === "startEvent"
                          ? "verbatim"
                          : selected.data.path_outcome === "REJECTED"
                            ? "inferred"
                            : "verbatim"
                      }`}
                    >
                      {selected.data.event_type === "startEvent"
                        ? "Start point"
                        : "End point"}
                    </span>
                  )}
                </div>
                <span className="detail-wording-label">
                  {selected.data.path_outcome === "PROHIBITED"
                    ? "Prohibited outcome"
                    : selected.data.event_type === "startEvent"
                      ? "Process trigger"
                      : "Process outcome"}
                </span>
                {(() => {
                  const firstRef =
                    selected.data.event_type === "startEvent"
                      ? referenceFor(selected.data.source_reference_ids?.[0] ?? "")
                      : undefined;
                  if (firstRef?.anchor) {
                    return (
                      <h3>
                        <a
                          className="policy-jump"
                          href={`/${firstRef.source_html ?? "policy_source.html"}#${firstRef.anchor}`}
                          target="_blank"
                          rel="noreferrer"
                          title="Open the original policy with this paragraph highlighted"
                        >
                          {selected.data.title}
                          <ExternalLink size={13} aria-hidden="true" />
                        </a>
                      </h3>
                    );
                  }
                  return <h3>{selected.data.title}</h3>;
                })()}
                <p className="complete-wording">
                  {selected.data.path_outcome === "PROHIBITED"
                    ? "This end point closes a prohibition path. The activity must not proceed under the policy."
                    : selected.data.event_type === "startEvent"
                      ? "This circle marks where the workflow begins when the policy trigger applies."
                      : "This circle marks where the workflow ends for this path."}
                </p>
              </div>

              {selected.data.path_outcome === "PROHIBITED" && (
                <section className="prohibition-note">
                  <span>Prohibited action — negative outcome</span>
                  <p>
                    Orange end event for a policy prohibition. Distinct from a
                    rejected approval decision: the policy forbids the activity outright.
                  </p>
                </section>
              )}

              <dl className="attribute-grid">
                <div>
                  <dt>Element</dt>
                  <dd>
                    {selected.data.event_type === "startEvent"
                      ? "Start event"
                      : "End event"}
                  </dd>
                </div>
                {selected.data.event_type === "startEvent" &&
                  selected.data.next_step_id && (
                    <div>
                      <dt>Next step</dt>
                      <dd>
                        {workflow?.steps.find(
                          (step) => step.step_id === selected.data.next_step_id,
                        )?.title ?? selected.data.next_step_id}
                      </dd>
                    </div>
                  )}
                {selected.data.path_outcome && (
                    <div>
                      <dt>Path outcome</dt>
                      <dd
                        className={
                          selected.data.path_outcome === "APPROVED"
                            ? "explicit"
                            : selected.data.path_outcome === "PROHIBITED"
                              ? "prohibited"
                              : "inferred"
                        }
                      >
                        {selected.data.path_outcome === "PROHIBITED"
                          ? "Prohibited (must not proceed)"
                          : selected.data.path_outcome}
                      </dd>
                    </div>
                  )}
              </dl>

              {selected.data.event_type === "startEvent" &&
                (selected.data.source_reference_ids?.length ?? 0) > 0 && (
                  <section className="source-section">
                    <div className="source-title">
                      <span>Policy evidence</span>
                      <span>
                        {selected.data.source_reference_ids!.length} reference
                      </span>
                    </div>
                    {selected.data.source_reference_ids!.map((referenceId) => {
                      const reference = referenceFor(referenceId);
                      if (!reference) return null;
                      return (
                        <article className="source-card" key={reference.reference_id}>
                          <div className="source-meta">
                            <span>§ {reference.section_id}</span>
                            <span>¶ {reference.paragraph}</span>
                            <span>{reference.reference_id}</span>
                          </div>
                          <h4>{reference.section_title}</h4>
                          <blockquote>“{reference.quoted_text}”</blockquote>
                          {reference.anchor && (
                            <a
                              className="view-in-policy"
                              href={`/${reference.source_html ?? "policy_source.html"}#${reference.anchor}`}
                              target="_blank"
                              rel="noreferrer"
                            >
                              <ExternalLink size={12} aria-hidden="true" />
                              View in original policy
                            </a>
                          )}
                        </article>
                      );
                    })}
                  </section>
                )}
            </div>
          )}

          {selected?.kind === "phase" && (
            <div className="detail-content">
              <div className="detail-title-block">
                <div className="phase-detail-header">
                  <span className="phase-detail-num">Phase {selected.data.phase} — Compliance lifecycle</span>
                  <h3 className="phase-detail-title">{selected.data.title}</h3>
                  <p className="phase-detail-desc">{selected.data.description}</p>
                </div>

                <p className="phase-workflows-heading">Workflows in this phase</p>
                <div className="phase-workflow-list">
                  {selected.data.workflow_ids.map((wid) => {
                    const item = workflows.find((w) => w.workflow_id === wid);
                    return (
                      <button
                        key={wid}
                        className="phase-workflow-btn"
                        onClick={() => setActiveId(wid)}
                        title={`Open ${wid}`}
                      >
                        <span>{item?.title ?? wid}</span>
                        <span className="phase-workflow-id">{wid}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </aside>
        )}
      </div>
    </main>
  );
}
