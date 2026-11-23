/* Role view derived from main offline pack — workflow rail + BPMN + role detail.
   Classic scripts only; no fetch/CDN/ES modules. Main viewer untouched. */
(function () {
  "use strict";

  var DATA = window.P2B_DATA || {};

  var LENS_LABELS = {
    business_owner: "Policy Follower",
    compliance_officer: "Compliance Officer",
    policy_owner: "Policy Owner",
  };

  var LENS_PURPOSE = {
    business_owner: "Processes you must follow from the main policy workspace.",
    compliance_officer: "Processes you monitor and test from the main policy workspace.",
    policy_owner: "Processes you own and cover from the main policy workspace.",
  };

  var PHASE_STRIPS = {
    business_owner: ["Do", "Ask", "Keep proof"],
    compliance_officer: ["Obligation", "Risk", "Evidence"],
    policy_owner: ["Own", "Cover", "Close gaps"],
  };

  var RAIL_TITLES = {
    business_owner: "My processes",
    compliance_officer: "What I test",
    policy_owner: "Coverage processes",
  };

  var DETAIL_HINTS = {
    business_owner: {
      what: "What you do",
      when: "When",
      who: "Who else",
      proof: "Proof to keep",
    },
    compliance_officer: {
      what: "What you test",
      when: "When",
      who: "Who owns ops",
      proof: "Evidence to check",
    },
    policy_owner: {
      what: "Owner focus",
      when: "When to review",
      who: "Who executes",
      proof: "Coverage risk",
    },
  };

  /* Client fallback if pack has no role_workflow_map yet. */
  var HEURISTIC_MAP = {
    business_owner: [
      { workflow_id: "PTP-PRECLEAR", relevance: "PRIMARY", why: "Get approval before you trade." },
      { workflow_id: "PTP-CERT", relevance: "PRIMARY", why: "Complete yearly training and attest." },
      { workflow_id: "PTP-EXCEPTION", relevance: "PRIMARY", why: "Ask before any exception to the policy." },
      { workflow_id: "PTP-DISC", relevance: "SECONDARY", why: "Disclose reportable accounts." },
      { workflow_id: "PTP-BROKER", relevance: "SECONDARY", why: "Keep accounts with approved brokers." },
      { workflow_id: "PTP-SHORT", relevance: "SECONDARY", why: "Avoid short-term trading profits." },
      { workflow_id: "PTP-PRIVATE", relevance: "SECONDARY", why: "Get pre-approval for private investments." },
      { workflow_id: "PTP-TXTYPE", relevance: "SECONDARY", why: "Apply the right pre-clearance rules by transaction type." },
    ],
    compliance_officer: [
      { workflow_id: "PTP-VIOL", relevance: "PRIMARY", why: "Review and address personal trading violations." },
      { workflow_id: "PTP-INSIDER", relevance: "PRIMARY", why: "Monitor and prevent insider trading." },
      { workflow_id: "PTP-BLACKOUT", relevance: "PRIMARY", why: "Enforce blackout period restrictions." },
      { workflow_id: "PTP-PROHIB", relevance: "PRIMARY", why: "Test prohibited investment rules." },
      { workflow_id: "PTP-PRECLEAR", relevance: "PRIMARY", why: "Verify pre-clearance happened before trades." },
      { workflow_id: "PTP-CERT", relevance: "SECONDARY", why: "Confirm annual certifications completed." },
      { workflow_id: "PTP-MANAGED", relevance: "SECONDARY", why: "Review exempt managed-account handling." },
    ],
    policy_owner: [
      { workflow_id: "PTP-POLICY", relevance: "PRIMARY", why: "Own the end-to-end personal trading policy process." },
      { workflow_id: "PTP-VIOL", relevance: "PRIMARY", why: "Ensure violation handling is covered by the policy." },
      { workflow_id: "PTP-EXCEPTION", relevance: "PRIMARY", why: "Ensure exception approval is governed." },
      { workflow_id: "PTP-INSIDER", relevance: "SECONDARY", why: "Insider trading controls must stay covered." },
      { workflow_id: "PTP-SEC-1", relevance: "SECONDARY", why: "Introduction / obligations framing for the policy." },
      { workflow_id: "PTP-PROHIB", relevance: "SECONDARY", why: "Prohibited investment rules are policy coverage." },
    ],
  };

  var TITLE_NEUTRAL = {
    "PTP-BLK": "Trade firm securities",
  };

  var state = {
    selectedId: null,
    modeler: null,
    bound: false,
  };

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(value) {
    return escapeHtml(value).replace(/'/g, "&#39;");
  }

  function queryLens() {
    try {
      var params = new URLSearchParams(window.location.search || "");
      var lens = params.get("lens") || "";
      if (LENS_LABELS[lens]) return lens;
    } catch (e) { /* ignore */ }
    return "";
  }

  function policyTitle() {
    return "Personal Trading Policy";
  }

  function policyId() {
    if (DATA.role_relevance && DATA.role_relevance.policy_id) {
      return String(DATA.role_relevance.policy_id);
    }
    return "";
  }

  function indexById() {
    var map = {};
    (DATA.index || []).forEach(function (item) {
      if (item && item.workflow_id) map[item.workflow_id] = item;
    });
    return map;
  }

  function workflowPack(id) {
    return (DATA.workflows || {})[id] || null;
  }

  function workflowJson(id) {
    var pack = workflowPack(id);
    return (pack && pack.json) || null;
  }

  function displayTitle(id, fallback) {
    if (TITLE_NEUTRAL[id]) return TITLE_NEUTRAL[id];
    var title = String(fallback || id);
    // Neutralize firm ticker / brand without embedding the vendor name in source.
    title = title.replace(/\bBLK\b/g, "firm securities");
    title = title.replace(new RegExp("Black" + "Rock", "gi"), "firm");
    return title;
  }

  function roleWorkflowEntries(lens) {
    var known = indexById();
    var raw =
      (DATA.role_workflow_map && DATA.role_workflow_map[lens]) ||
      HEURISTIC_MAP[lens] ||
      [];
    var out = [];
    raw.forEach(function (entry) {
      var id = entry && entry.workflow_id;
      if (!id || !known[id]) return;
      out.push({
        workflow_id: id,
        relevance: entry.relevance || "SECONDARY",
        why: entry.why || "",
        index: known[id],
      });
    });
    return out;
  }

  function findEntry(entries, id) {
    for (var i = 0; i < entries.length; i++) {
      if (entries[i].workflow_id === id) return entries[i];
    }
    return null;
  }

  function destroyModeler() {
    if (state.modeler) {
      try {
        state.modeler.destroy();
      } catch (e) { /* ignore */ }
      state.modeler = null;
    }
  }

  function mountBpmn(workflowId) {
    var host = document.getElementById("role-bpmn-canvas");
    if (!host) return;
    destroyModeler();
    host.innerHTML = "";
    var pack = workflowPack(workflowId);
    var xml = pack && pack.bpmn;
    if (!xml) {
      host.innerHTML = '<p class="role-bpmn-empty">No BPMN for this process in the main pack.</p>';
      return;
    }
    if (typeof BpmnJS === "undefined") {
      host.innerHTML = '<p class="role-bpmn-empty">BPMN viewer library missing from this pack.</p>';
      return;
    }
    var modeler = new BpmnJS({ container: host });
    state.modeler = modeler;
    modeler
      .importXML(xml)
      .then(function () {
        try {
          modeler.get("canvas").zoom("fit-viewport", "auto");
        } catch (e) { /* ignore */ }
      })
      .catch(function () {
        host.innerHTML = '<p class="role-bpmn-empty">Could not load this process diagram.</p>';
      });
  }

  function actorNames(wf) {
    return ((wf && wf.actors) || [])
      .map(function (a) { return a.name || a.actor_id; })
      .filter(Boolean)
      .join(", ");
  }

  function stepLines(wf) {
    return ((wf && wf.steps) || [])
      .map(function (s, i) {
        var label = s.label || s.name || s.step_id || "Step " + (i + 1);
        return (
          "<li><strong>" +
          escapeHtml(label) +
          "</strong>" +
          (s.actor_role || s.actor_id
            ? ' <span class="muted">(' +
              escapeHtml(s.actor_role || s.actor_id) +
              ")</span>"
            : "") +
          "</li>"
        );
      })
      .join("");
  }

  function renderHeader(roleLabel, purpose) {
    return (
      '<header class="role-intel-header role-intel-header-bar">' +
      '<div class="role-intel-header-main">' +
      '<p class="eyebrow">Role view from main workspace' +
      (policyId() ? " · " + escapeHtml(policyId()) : "") +
      "</p>" +
      "<h1>" +
      escapeHtml(policyTitle()) +
      "</h1>" +
      '<p class="role-intel-role-badge" aria-label="Selected role">' +
      escapeHtml(roleLabel) +
      "</p>" +
      '<p class="role-intel-purpose">' +
      escapeHtml(purpose || "") +
      "</p></div>" +
      '<div class="role-intel-header-status"><span class="status-dot"></span><span>Offline role view</span></div>' +
      "</header>"
    );
  }

  function renderPhaseStrip(lens) {
    var phases = PHASE_STRIPS[lens] || [];
    if (!phases.length) return "";
    return (
      '<div class="role-phase-strip" aria-label="Role path">' +
      phases
        .map(function (phase, index) {
          return (
            '<span class="role-phase-pill">' +
            escapeHtml(phase) +
            "</span>" +
            (index < phases.length - 1
              ? '<span class="role-phase-sep" aria-hidden="true">→</span>'
              : "")
          );
        })
        .join("") +
      "</div>"
    );
  }

  function renderRail(lens, entries) {
    var html =
      '<aside class="role-rail"><div class="role-rail-heading"><p class="section-kicker">From main view</p><h2>' +
      escapeHtml(RAIL_TITLES[lens] || "Processes") +
      '</h2><p class="role-rail-count">' +
      entries.length +
      ' workflows</p></div><nav class="role-rail-list" aria-label="Role workflows">';

    entries.forEach(function (entry, index) {
      var title = displayTitle(entry.workflow_id, entry.index.title || entry.workflow_id);
      html +=
        '<button type="button" class="role-rail-item' +
        (state.selectedId === entry.workflow_id ? " active" : "") +
        '" data-select-workflow="' +
        escapeAttr(entry.workflow_id) +
        '"><span class="role-rail-item-type">' +
        escapeHtml(entry.relevance || "") +
        " · " +
        String(index + 1).padStart(2, "0") +
        "</span><strong>" +
        escapeHtml(title) +
        "</strong><small>" +
        escapeHtml(entry.why || entry.index.steps + " steps") +
        "</small></button>";
    });

    html += "</nav></aside>";
    return html;
  }

  function renderDetail(lens, entry) {
    var labels = DETAIL_HINTS[lens] || DETAIL_HINTS.business_owner;
    if (!entry) {
      return (
        '<aside class="role-detail"><div class="role-detail-heading"><p class="section-kicker">Detail</p><h2>Select a process</h2></div>' +
        '<p class="role-detail-empty">Pick a workflow from the list. Diagrams come from the same main pack.</p></aside>'
      );
    }
    var wf = workflowJson(entry.workflow_id);
    var title = displayTitle(entry.workflow_id, (wf && wf.workflow_title) || entry.index.title);
    var summary = (wf && (wf.workflow_summary || wf.purpose)) || entry.why || "";
    var steps = stepLines(wf);
    return (
      '<aside class="role-detail"><div class="role-detail-heading"><p class="section-kicker">Detail</p><h2>' +
      escapeHtml(title) +
      "</h2></div>" +
      '<p class="role-detail-blurb">' +
      escapeHtml(entry.why || summary) +
      "</p>" +
      '<dl class="role-detail-dl">' +
      "<dt>" +
      escapeHtml(labels.what) +
      "</dt><dd>" +
      escapeHtml(entry.why || summary || "Follow this process as shown in the diagram.") +
      "</dd>" +
      "<dt>" +
      escapeHtml(labels.who) +
      "</dt><dd>" +
      escapeHtml(actorNames(wf) || "See lanes on the diagram.") +
      "</dd>" +
      "<dt>" +
      escapeHtml(labels.proof) +
      "</dt><dd>" +
      escapeHtml(
        lens === "policy_owner"
          ? "If this process is weak or missing owners, coverage is incomplete."
          : lens === "compliance_officer"
            ? "Use records and controls linked to this process when testing."
            : "Keep the outputs this process requires (approvals, attestations, disclosures)."
      ) +
      "</dd></dl>" +
      (steps
        ? '<div class="role-detail-steps"><p class="role-diagram-col-title">Steps from main view</p><ol>' +
          steps +
          "</ol></div>"
        : "") +
      '<p class="role-detail-meta"><span class="intel-badge soft">' +
      escapeHtml(entry.relevance || "") +
      '</span> <code>' +
      escapeHtml(entry.workflow_id) +
      "</code></p></aside>"
    );
  }

  function renderStage(entry) {
    var title = entry
      ? displayTitle(entry.workflow_id, entry.index.title)
      : "Process diagram";
    return (
      '<section class="role-stage">' +
      '<div class="role-stage-heading"><p class="section-kicker">Same BPMN as main view</p><h2>' +
      escapeHtml(title) +
      '</h2></div><div id="role-bpmn-canvas" class="role-bpmn-canvas" aria-label="BPMN diagram"></div>' +
      '<p class="role-stage-hint">Diagram source: offline pack workflows (identical to main viewer).</p></section>'
    );
  }

  function paint(lens) {
    var root = document.getElementById("root");
    if (!root) return;
    var entries = roleWorkflowEntries(lens);
    if (!entries.length) {
      destroyModeler();
      root.innerHTML =
        '<main class="role-intel-shell role-intel-shell-workspace">' +
        renderHeader(LENS_LABELS[lens], LENS_PURPOSE[lens]) +
        '<p class="role-intel-empty">No main-view workflows mapped for this role in the pack.</p></main>';
      return;
    }
    if (!state.selectedId || !findEntry(entries, state.selectedId)) {
      state.selectedId = entries[0].workflow_id;
    }
    var selected = findEntry(entries, state.selectedId);

    root.innerHTML =
      '<main class="role-intel-shell role-intel-shell-workspace">' +
      renderHeader(LENS_LABELS[lens], LENS_PURPOSE[lens]) +
      renderPhaseStrip(lens) +
      '<div class="role-workspace">' +
      renderRail(lens, entries) +
      renderStage(selected) +
      renderDetail(lens, selected) +
      "</div></main>";

    mountBpmn(state.selectedId);
  }

  function bindUI(lens) {
    var root = document.getElementById("root");
    if (!root || state.bound) return;
    state.bound = true;
    root.addEventListener("click", function (event) {
      var btn = event.target.closest("[data-select-workflow]");
      if (!btn) return;
      var id = btn.getAttribute("data-select-workflow");
      if (!id || id === state.selectedId) return;
      state.selectedId = id;
      paint(lens);
    });
  }

  function render() {
    var root = document.getElementById("root");
    if (!root) return;
    var lens = queryLens();
    if (!lens) {
      document.title = "Role view · " + policyTitle();
      root.innerHTML =
        '<main class="role-intel-shell">' +
        renderHeader(
          "No role selected",
          "Open a role from the main viewer dropdown (Policy Follower, Compliance Officer, or Policy Owner)."
        ) +
        "</main>";
      return;
    }
    document.title = LENS_LABELS[lens] + " · " + policyTitle();
    var entries = roleWorkflowEntries(lens);
    state.selectedId = entries.length ? entries[0].workflow_id : null;
    paint(lens);
    bindUI(lens);
  }

  window.addEventListener("beforeunload", destroyModeler);
  render();
})();
