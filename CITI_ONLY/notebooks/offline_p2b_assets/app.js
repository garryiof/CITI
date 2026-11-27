/* Offline policies2BPMN-style viewer — classic scripts only; no fetch/CDN/ES modules. */
(function () {
  "use strict";

  var DATA = window.P2B_DATA || {};
  var ROLE_KEY = "p2b-user-role";
  var LENS_KEY = "p2b-intelligence-lens";
  /* Hide Viewer / Policy owner switch until review workflow is ready to demo. */
  var SHOW_REVIEW_ACCESS = false;
  /* main_view first — stays on main; role keys open dedicated role tabs. */
  var LENS_LABELS = {
    main_view: "All roles (main view)",
    business_owner: "Policy Follower",
    compliance_officer: "Compliance Officer",
    policy_owner: "Policy Owner",
  };

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function isRoleLens(lens) {
    return (
      lens === "business_owner" ||
      lens === "compliance_officer" ||
      lens === "policy_owner"
    );
  }

  function hasRoleRelevance() {
    var rr = DATA.role_relevance;
    return !!(rr && rr.perspectives && typeof rr.perspectives === "object");
  }

  function policyId() {
    if (DATA.role_relevance && DATA.role_relevance.policy_id) {
      return String(DATA.role_relevance.policy_id);
    }
    if (state.workflow && state.workflow.policy && state.workflow.policy.policy_id) {
      return String(state.workflow.policy.policy_id);
    }
    var wfs = DATA.workflows || {};
    var keys = Object.keys(wfs);
    for (var i = 0; i < keys.length; i++) {
      var wf = wfs[keys[i]] && wfs[keys[i]].json;
      if (wf && wf.policy && wf.policy.policy_id) return String(wf.policy.policy_id);
    }
    return "";
  }

  function readLens() {
    /* Always open main view on All roles — do not restore last role from storage. */
    return "main_view";
  }

  function writeLens(lens) {
    try {
      localStorage.setItem(LENS_KEY, lens);
    } catch (e) { /* ignore */ }
  }

  function catalogEntry(id) {
    var catalog = DATA.canonical_catalog || {};
    return catalog[id] || null;
  }

  function entityLabel(id) {
    var entry = catalogEntry(id);
    if (entry && entry.label) return entry.label;
    return id;
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function normalizeStatus(value) {
    return value === "APPROVED" ? "APPROVED" : "PENDING";
  }

  function readRole() {
    if (!SHOW_REVIEW_ACCESS) return "VIEWER";
    try {
      return localStorage.getItem(ROLE_KEY) === "POLICY_OWNER" ? "POLICY_OWNER" : "VIEWER";
    } catch (e) {
      return "VIEWER";
    }
  }

  function reviewKey(id) {
    return "p2b-review-" + id;
  }

  function layoutKey(id) {
    return "p2b-layout-" + id;
  }

  function getStoredReview(id, fallback) {
    try {
      var v = localStorage.getItem(reviewKey(id));
      return v ? normalizeStatus(v) : normalizeStatus(fallback);
    } catch (e) {
      return normalizeStatus(fallback);
    }
  }

  function setStoredReview(id, status) {
    try {
      localStorage.setItem(reviewKey(id), status);
    } catch (e) { /* ignore */ }
  }

  function getStoredLayout(id) {
    try {
      return localStorage.getItem(layoutKey(id));
    } catch (e) {
      return null;
    }
  }

  function setStoredLayout(id, xml) {
    try {
      localStorage.setItem(layoutKey(id), xml);
    } catch (e) { /* ignore */ }
  }

  function downloadText(filename, content, mime) {
    var blob = new Blob([content], { type: mime || "text/plain;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function normalizeLabelKey(value) {
    return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
  }

  function buildDuplicateGroups(workflow) {
    var buckets = {};
    (workflow.steps || []).forEach(function (step) {
      var key = normalizeLabelKey(step.title);
      if (!key) return;
      if (!buckets[key]) buckets[key] = [];
      buckets[key].push(step);
    });
    return Object.keys(buckets)
      .filter(function (k) { return buckets[k].length > 1; })
      .map(function (k) {
        return { key: k, label: buckets[k][0].title, hits: buckets[k] };
      })
      .sort(function (a, b) {
        return b.hits.length - a.hits.length || a.label.localeCompare(b.label);
      });
  }

  function countBy(items, getter) {
    var map = {};
    items.forEach(function (item) {
      var key = getter(item) || "—";
      map[key] = (map[key] || 0) + 1;
    });
    return Object.keys(map)
      .map(function (k) { return { metric: k, value: map[k] }; })
      .sort(function (a, b) {
        return b.value - a.value || String(a.metric).localeCompare(String(b.metric));
      });
  }

  function buildAnalysis(workflow) {
    var steps = workflow.steps || [];
    var dups = buildDuplicateGroups(workflow);
    var byLabel = {};
    steps.forEach(function (step) {
      var key = normalizeLabelKey(step.title);
      if (!key) return;
      if (!byLabel[key]) byLabel[key] = { label: step.title, ids: [] };
      byLabel[key].ids.push(step.step_id);
    });
    var labelFrequency = Object.keys(byLabel)
      .map(function (k) {
        return {
          label: byLabel[k].label,
          count: byLabel[k].ids.length,
          detail: byLabel[k].ids.join(", "),
        };
      })
      .sort(function (a, b) {
        return b.count - a.count || a.label.localeCompare(b.label);
      });
    var inferred = steps.filter(function (s) { return s.explicit_or_inferred === "INFERRED"; }).length;
    var explicit = steps.filter(function (s) { return s.explicit_or_inferred === "EXPLICIT"; }).length;
    var prohibited = steps.filter(function (s) { return s.action_type === "PROHIBITED_ACTION"; }).length;
    var review = getStoredReview(workflow.workflow_id, workflow.review_status);
    return {
      summary: [
        { metric: "Workflow ID", value: workflow.workflow_id },
        { metric: "Workflow name", value: workflow.workflow_title },
        { metric: "Total steps", value: steps.length },
        { metric: "Explicit steps", value: explicit, note: "Policy-verbatim obligations" },
        { metric: "Inferred steps", value: inferred, note: "Connective steps added for readability" },
        {
          metric: "Inferred share",
          value: steps.length === 0 ? "0%" : Math.round((inferred / steps.length) * 100) + "%",
        },
        { metric: "Prohibited actions", value: prohibited },
        { metric: "Duplicate labels", value: dups.length, note: "Labels used more than once on this diagram" },
        { metric: "Unique labels", value: labelFrequency.length },
        { metric: "Review status", value: review },
        { metric: "Gateways", value: (workflow.gateways || []).length },
      ],
      duplicatedWithin: dups.map(function (g) {
        return {
          label: g.label,
          count: g.hits.length,
          detail: g.hits.map(function (h) { return h.step_id; }).join(", "),
        };
      }),
      labelFrequency: labelFrequency,
      byActionType: countBy(steps, function (s) {
        return String(s.action_type || "").replaceAll("_", " ");
      }),
      byStepType: countBy(steps, function (s) { return s.explicit_or_inferred; }),
      byOutcome: countBy(steps, function (s) {
        return String(s.path_outcome || "NEUTRAL").replaceAll("_", " ");
      }),
      byActor: countBy(steps, function (s) {
        var actor = (workflow.actors || []).find(function (a) { return a.actor_id === s.actor_id; });
        return actor ? actor.name : s.actor_id;
      }),
      byReviewStatus: [{ metric: review, value: 1 }],
      recommendations: [
        "Source grounding rate — % of steps with a linked policy paragraph / quote.",
        "Approval gate presence — whether this workflow has an Approved/Rejected decision.",
        "Deadline inventory — time-bound obligations in this workflow (e.g. 7 / 15 / 30 days).",
        "Control ownership — steps by actor vs expected RACI (Employee vs Legal & Compliance).",
        "Ambiguity / low-confidence queue — steps needing human confirmation before go-live.",
        "Exception paths — exception / escalation branches and who owns them.",
        "Review aging — days this workflow has remained PENDING since last regeneration.",
      ],
    };
  }

  var ELEMENT_KIND_LABELS = { A: "Action", G: "Gateway", E: "Event", R: "Reference" };

  function parsePolicyCode(code) {
    var match = String(code || "").trim().match(/^P-([^-]+)-(\d{3})-([AGER])(\d{3})$/i);
    if (!match) return null;
    var kind = match[3].toUpperCase();
    return {
      chapter: match[1],
      workflowStep: match[2],
      element: kind + match[4],
      elementKind: kind,
      elementKindLabel: ELEMENT_KIND_LABELS[kind] || kind,
    };
  }

  // ---- App state ----
  var state = {
    index: DATA.index || [],
    activeId: null,
    workflow: null,
    bpmnXml: "",
    originalXml: "",
    selected: null,
    query: "",
    dirty: false,
    detailOpen: true,
    legendOpen: false,
    duplicatesOpen: false,
    analyticsOpen: false,
    selectedDuplicateKey: null,
    role: readRole(),
    lens: readLens(),
    intelOpen: false,
    overviewOpen: false,
    roleTabBlocked: false,
    saveNotice: "",
    error: "",
    loading: false,
    modeler: null,
  };

  if (state.index.length) {
    var preferred = state.index.find(function (i) { return i.workflow_id === "PTP-PRECLEAR"; });
    state.activeId = preferred ? preferred.workflow_id : state.index[0].workflow_id;
  }

  function loadWorkflow(id) {
    var pack = (DATA.workflows || {})[id];
    if (!pack) {
      state.error = "Workflow data missing for " + id;
      state.workflow = null;
      state.bpmnXml = "";
      return;
    }
    state.error = "";
    state.workflow = JSON.parse(JSON.stringify(pack.json));
    state.workflow.review_status = getStoredReview(id, state.workflow.review_status);
    state.originalXml = pack.bpmn || "";
    state.bpmnXml = getStoredLayout(id) || state.originalXml;
    state.selected = null;
    state.dirty = false;
    state.selectedDuplicateKey = null;
  }

  function visibleIndex() {
    var q = state.query.trim().toLowerCase();
    if (!q) return state.index;
    return state.index.filter(function (item) {
      return item.title.toLowerCase().includes(q) || item.workflow_id.toLowerCase().includes(q);
    });
  }

  function referenceFor(referenceId) {
    if (!state.workflow) return null;
    return (state.workflow.source_references || []).find(function (r) {
      return r.reference_id === referenceId;
    });
  }

  function policyHref(reference) {
    if (!reference || !reference.anchor) return null;
    return "policy_source.html#" + reference.anchor;
  }

  function destroyModeler() {
    if (state.modeler) {
      try { state.modeler.destroy(); } catch (e) { /* ignore */ }
      state.modeler = null;
    }
  }

  function renderDiagram() {
    var host = $(".bpmn-canvas");
    if (!host || !state.bpmnXml || !state.workflow) return;
    destroyModeler();
    if (typeof BpmnJS === "undefined") {
      state.error = "BPMN modeler library missing.";
      render();
      return;
    }
    state.loading = true;
    var modeler = new BpmnJS({ container: host });
    state.modeler = modeler;
    modeler
      .importXML(state.bpmnXml)
      .then(function () {
        var canvas = modeler.get("canvas");
        canvas.zoom("fit-viewport");
        (state.workflow.steps || []).forEach(function (step) {
          if (step.explicit_or_inferred === "INFERRED") {
            try { canvas.addMarker(step.step_id, "inferred-node"); } catch (e) { /* ignore */ }
          }
          if (step.action_type === "RECOMMENDED_ACTION" || step.recommended) {
            try { canvas.addMarker(step.step_id, "recommended-node"); } catch (e) { /* ignore */ }
          }
        });
        var eventBus = modeler.get("eventBus");
        eventBus.on("element.click", function (event) {
          var id = event.element && event.element.id;
          if (!id || !state.workflow) return;
          var step = (state.workflow.steps || []).find(function (s) { return s.step_id === id; });
          if (step) {
            state.selected = { kind: "step", data: step };
            state.detailOpen = true;
            patchDetail();
            return;
          }
          var gateway = (state.workflow.gateways || []).find(function (g) { return g.gateway_id === id; });
          if (gateway) {
            state.selected = { kind: "gateway", data: gateway };
            state.detailOpen = true;
            patchDetail();
            return;
          }
          var events = state.workflow.events || [];
          var start = state.workflow.start_event;
          var ends = state.workflow.end_events || [];
          var found =
            events.find(function (e) { return e.event_id === id; }) ||
            (start && start.event_id === id ? start : null) ||
            ends.find(function (e) { return e.event_id === id; });
          state.selected = found ? { kind: "event", data: found } : null;
          if (found) state.detailOpen = true;
          patchDetail();
        });
        eventBus.on("commandStack.changed", function () {
          state.dirty = true;
          var bar = $(".stage-bar");
          if (bar) bar.hidden = false;
          var resetBtn = $("[data-action='reset']");
          if (resetBtn) resetBtn.disabled = false;
        });
        state.loading = false;
        state.error = "";
        var loadingEl = $(".stage-state.loading");
        if (loadingEl) loadingEl.hidden = true;
      })
      .catch(function (err) {
        state.loading = false;
        state.error = (err && err.message) || "The BPMN diagram could not render.";
        var errEl = $(".stage-state.error");
        if (errEl) {
          errEl.hidden = false;
          errEl.textContent = state.error;
        }
      });
  }

  /** Update right-hand detail pane without destroying the BPMN canvas. */
  function patchDetail() {
    var workspace = $(".workspace");
    if (!workspace) return;
    var old = workspace.querySelector(".detail-panel, .detail-rail");
    var tmp = document.createElement("div");
    tmp.innerHTML = renderDetail();
    var next = tmp.firstChild;
    if (!next) return;
    if (old) old.replaceWith(next);
    else workspace.appendChild(next);
    if (state.detailOpen) workspace.classList.remove("detail-collapsed");
    else workspace.classList.add("detail-collapsed");
    if (state.modeler) {
      try {
        state.modeler.get("canvas").resized();
      } catch (e) { /* ignore */ }
    }
  }

  /** Swap legend/duplicates/analytics overlays; leave .bpmn-canvas alone. */
  function patchOverlays() {
    var stage = $(".diagram-stage");
    if (!stage) return;
    stage
      .querySelectorAll(".legend-panel, .duplicates-panel, .analytics-panel")
      .forEach(function (node) {
        node.remove();
      });
    var tmp = document.createElement("div");
    tmp.innerHTML = renderOverlays();
    while (tmp.firstChild) stage.appendChild(tmp.firstChild);
    document.querySelectorAll('.zoom-group [data-action="toggle-analytics"]').forEach(function (btn) {
      btn.classList.toggle("active", state.analyticsOpen);
    });
    document.querySelectorAll('.zoom-group [data-action="toggle-duplicates"]').forEach(function (btn) {
      btn.classList.toggle("active", state.duplicatesOpen);
    });
    document.querySelectorAll('.zoom-group [data-action="toggle-legend"]').forEach(function (btn) {
      btn.classList.toggle("active", state.legendOpen);
    });
  }

  function zoom(delta) {
    if (!state.modeler) return;
    var canvas = state.modeler.get("canvas");
    var current = canvas.zoom();
    canvas.zoom(Math.max(0.2, Math.min(4, current + delta * 0.15)));
  }

  function fitViewport() {
    if (!state.modeler) return;
    state.modeler.get("canvas").zoom("fit-viewport");
  }

  function resetLayout() {
    if (!state.workflow) return;
    state.bpmnXml = state.originalXml;
    state.dirty = false;
    try { localStorage.removeItem(layoutKey(state.activeId)); } catch (e) { /* ignore */ }
    render();
    renderDiagram();
  }

  function saveLayout() {
    if (!state.modeler || !state.workflow) return;
    state.modeler.saveXML({ format: true }).then(function (result) {
      var xml = result.xml;
      if (!xml) throw new Error("Could not export the diagram.");
      state.bpmnXml = xml;
      setStoredLayout(state.activeId, xml);
      var jsonContent = JSON.stringify(state.workflow, null, 2) + "\n";
      downloadText(state.activeId + ".bpmn", xml, "application/xml");
      downloadText(state.activeId + ".json", jsonContent, "application/json");
      state.dirty = false;
      state.saveNotice = "Saved to browser storage and downloaded " + state.activeId + ".bpmn/.json";
      var bar = $(".stage-bar");
      if (bar) bar.hidden = true;
      var resetBtn = $("[data-action='reset']");
      if (resetBtn) resetBtn.disabled = true;
      var heading = $(".diagram-heading");
      if (heading) {
        var existing = heading.querySelector(".save-notice");
        if (existing) existing.remove();
        var notice = document.createElement("p");
        notice.className = "save-notice";
        notice.textContent = state.saveNotice;
        heading.appendChild(notice);
      }
      window.setTimeout(function () {
        state.saveNotice = "";
        var n = $(".save-notice");
        if (n) n.remove();
      }, 2200);
    }).catch(function (err) {
      state.error = (err && err.message) || "Could not save layout.";
      var errEl = $(".stage-state.error");
      if (errEl) {
        errEl.hidden = false;
        errEl.textContent = state.error;
      }
    });
  }

  function setRole(role) {
    state.role = role;
    try { localStorage.setItem(ROLE_KEY, role); } catch (e) { /* ignore */ }
    // Review-access changes the review control — remount chrome but keep diagram via soft path.
    softRefreshChrome();
  }

  function roleIntelligenceUrl(lens) {
    var file = "role_intelligence.html?lens=" + encodeURIComponent(lens);
    try {
      // Resolve against the main viewer location so file:// window.open stays in-pack.
      return new URL(file, window.location.href).href;
    } catch (e) {
      return file;
    }
  }

  function openRoleIntelligenceTab(lens) {
    if (!hasRoleRelevance() || !isRoleLens(lens)) return;
    var url = roleIntelligenceUrl(lens);
    var win = null;
    try {
      // Named target reuses one tab per role instead of spawning duplicates.
      win = window.open(url, "p2b-role-" + lens);
    } catch (e) {
      win = null;
    }
    if (!win) {
      state.roleTabBlocked = true;
      softRefreshChrome();
    } else {
      state.roleTabBlocked = false;
    }
  }

  function setLens(lens) {
    if (!LENS_LABELS[lens]) return;
    state.lens = lens;
    writeLens(lens);
    if (isRoleLens(lens)) {
      openRoleIntelligenceTab(lens);
    } else {
      state.roleTabBlocked = false;
    }
    if (state.intelOpen) {
      patchOverlays();
    } else {
      softRefreshChrome();
    }
  }

  function setReviewStatus(next) {
    if (!state.workflow || state.role !== "POLICY_OWNER") return;
    state.workflow.review_status = next;
    setStoredReview(state.activeId, next);
    softRefreshChrome();
  }

  /**
   * Rebuild shell around the live canvas host so the modeler instance survives.
   * Used for role/review/overview chrome updates that are not a workflow switch.
   */
  function softRefreshChrome() {
    var host = $(".bpmn-canvas");
    var modeler = state.modeler;
    // Detach the live canvas node so render()'s innerHTML wipe does not destroy it.
    if (host && host.parentNode) host.parentNode.removeChild(host);
    state.modeler = null;
    render();
    var stage = $(".diagram-stage");
    var placeholder = stage && stage.querySelector(".bpmn-canvas");
    if (stage && host) {
      if (placeholder) placeholder.replaceWith(host);
      else stage.insertBefore(host, stage.firstChild);
    }
    state.modeler = modeler;
    if (state.modeler) {
      try {
        state.modeler.get("canvas").resized();
      } catch (e) { /* ignore */ }
    }
  }

  function svgIcon(path) {
    return (
      '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      path +
      "</svg>"
    );
  }

  function renderCodeChip(code, fallbackId, href) {
    var display = code || fallbackId;
    var segments = parsePolicyCode(code);
    var html =
      '<div class="code-chip-wrap">' +
      '<button type="button" class="element-id code-chip-btn" data-action="toggle-code">' +
      escapeHtml(display) +
      "</button>" +
      '<div class="code-explainer" hidden>' +
      '<div class="code-explainer-head"><strong>How this code is built</strong>' +
      '<button type="button" class="code-explainer-close" data-action="close-code" aria-label="Close">×</button></div>' +
      '<p class="code-explainer-pattern">Pattern: <code>P-{chapter}-{workflowStep}-{element}</code></p>';
    if (segments) {
      html +=
        '<table class="code-explainer-table"><tbody>' +
        "<tr><th>P</th><td>Policy (fixed prefix — not a version number)</td></tr>" +
        "<tr><th>" + escapeHtml(segments.chapter) + "</th><td>Original chapter / subsection in the source policy</td></tr>" +
        "<tr><th>" + escapeHtml(segments.workflowStep) + "</th><td>Workflow step sequence in this diagram</td></tr>" +
        "<tr><th>" + escapeHtml(segments.element) + "</th><td>" +
        escapeHtml(segments.elementKindLabel) + " element</td></tr>" +
        "</tbody></table>";
    } else {
      html +=
        '<p class="code-explainer-fallback">Machine id <code>' +
        escapeHtml(fallbackId) +
        "</code>.</p>";
    }
    if (href) {
      html +=
        '<a class="code-explainer-policy" href="' +
        escapeAttr(href) +
        '" target="_blank" rel="noreferrer">Open original policy</a>';
    }
    html += "</div></div>";
    return html;
  }

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

  function renderDetail() {
    if (!state.detailOpen) {
      return (
        '<aside class="detail-rail">' +
        '<button class="panel-toggle" data-action="open-detail" title="Show element detail" aria-label="Show element detail">»</button>' +
        '<span class="rail-label">Element detail</span></aside>'
      );
    }
    var body = "";
    var selected = state.selected;
    var isOverview =
      state.workflow &&
      state.workflow.workflow_id === "PTP-POLICY" &&
      state.workflow.high_level_plan;

    if (!selected) {
      body =
        '<div class="empty-detail"><div class="empty-glyph">◎</div>' +
        (isOverview
          ? "<h3>Select an element</h3><p>Click a phase pill at the top, or any step or event in the diagram.</p>"
          : "<h3>Select a diagram element</h3><p>Choose a start point, task, decision, or end point to inspect its details.</p>") +
        "</div>";
    } else if (selected.kind === "step") {
      var step = selected.data;
      var firstRef = referenceFor((step.source_reference_ids || [])[0] || "");
      var href = policyHref(firstRef);
      body =
        '<div class="detail-content"><div class="detail-title-block">' +
        '<div class="detail-origin-row">' +
        renderCodeChip(step.step_code, step.step_id, href) +
        (step.action_type === "PROHIBITED_ACTION" || step.path_outcome === "PROHIBITED"
          ? '<span class="wording-origin prohibited">Prohibited — negative outcome</span>'
          : "") +
        "</div>" +
        '<span class="detail-wording-label">Business-readable label</span>' +
        (href
          ? "<h3><a class=\"policy-jump\" href=\"" +
            escapeAttr(href) +
            '" target="_blank" rel="noreferrer">' +
            escapeHtml(step.title) +
            "</a></h3>"
          : "<h3>" + escapeHtml(step.title) + "</h3>") +
        '<span class="detail-wording-label">' +
        (step.wording_origin === "POLICY_VERBATIM"
          ? "Complete policy wording"
          : "Inferred workflow explanation") +
        "</span>" +
        '<p class="complete-wording">' +
        escapeHtml(step.description) +
        "</p></div>" +
        '<dl class="attribute-grid">' +
        "<div><dt>Classification</dt><dd>" +
        escapeHtml(String(step.action_type || "").replaceAll("_", " ")) +
        "</dd></div>" +
        "<div><dt>Outcome</dt><dd>" +
        escapeHtml(
          step.path_outcome === "PROHIBITED"
            ? "Prohibited (must not proceed)"
            : String(step.path_outcome || "Neutral").replaceAll("_", " ")
        ) +
        "</dd></div>" +
        "<div><dt>Step type</dt><dd class=\"" +
        String(step.explicit_or_inferred || "").toLowerCase() +
        '">' +
        escapeHtml(step.explicit_or_inferred) +
        "</dd></div>" +
        "<div><dt>Actor</dt><dd>" +
        escapeHtml(
          ((state.workflow.actors || []).find(function (a) {
            return a.actor_id === step.actor_id;
          }) || {}).name || step.actor_id
        ) +
        "</dd></div></dl>" +
        '<section class="source-section"><div class="source-title"><span>Policy evidence</span><span>' +
        (step.source_reference_ids || []).length +
        " reference</span></div>" +
        (step.source_reference_ids || [])
          .map(function (rid) {
            var reference = referenceFor(rid);
            if (!reference) return "";
            var ph = policyHref(reference);
            return (
              '<article class="source-card"><div class="source-meta"><span>§ ' +
              escapeHtml(reference.section_id) +
              "</span><span>¶ " +
              escapeHtml(reference.paragraph) +
              "</span><span>" +
              escapeHtml(reference.reference_id) +
              "</span></div><h4>" +
              escapeHtml(reference.section_title) +
              "</h4><blockquote>“" +
              escapeHtml(reference.quoted_text) +
              "”</blockquote>" +
              (ph
                ? '<a class="view-in-policy" href="' +
                  escapeAttr(ph) +
                  '" target="_blank" rel="noreferrer">View in original policy</a>'
                : "") +
              "</article>"
            );
          })
          .join("") +
        "</section></div>";
    } else if (selected.kind === "gateway") {
      var gw = selected.data;
      body =
        '<div class="detail-content"><div class="detail-title-block">' +
        renderCodeChip(gw.gateway_code, gw.gateway_id, null) +
        "<h3>" +
        escapeHtml(gw.question) +
        "</h3><p>An exclusive policy decision with labeled outcomes.</p></div>" +
        '<section class="branch-section"><span>Decision branches</span>' +
        (gw.branches || [])
          .map(function (branch) {
            return (
              '<div class="branch-row"><strong>' +
              escapeHtml(branch.label) +
              "</strong><code>" +
              escapeHtml(branch.condition) +
              "</code></div>"
            );
          })
          .join("") +
        "</section></div>";
    } else if (selected.kind === "event") {
      var ev = selected.data;
      body =
        '<div class="detail-content"><div class="detail-title-block">' +
        renderCodeChip(ev.event_code, ev.event_id, null) +
        "<h3>" +
        escapeHtml(ev.title) +
        "</h3></div>" +
        '<dl class="attribute-grid"><div><dt>Element</dt><dd>' +
        (ev.event_type === "startEvent" ? "Start event" : "End event") +
        "</dd></div></dl></div>";
    } else if (selected.kind === "phase") {
      var phase = selected.data;
      body =
        '<div class="detail-content"><div class="detail-title-block">' +
        '<span class="phase-detail-num">Phase ' +
        escapeHtml(phase.phase) +
        " — Compliance lifecycle</span>" +
        '<h3 class="phase-detail-title">' +
        escapeHtml(phase.title) +
        "</h3>" +
        '<p class="phase-detail-desc">' +
        escapeHtml(phase.description) +
        "</p>" +
        '<p class="phase-workflows-heading">Workflows in this phase</p>' +
        '<div class="phase-workflow-list">' +
        (phase.workflow_ids || [])
          .map(function (wid) {
            var item = state.index.find(function (w) { return w.workflow_id === wid; });
            return (
              '<button type="button" class="phase-workflow-btn" data-action="select-workflow" data-id="' +
              escapeAttr(wid) +
              '"><span>' +
              escapeHtml((item && item.title) || wid) +
              '</span><span class="phase-workflow-id">' +
              escapeHtml(wid) +
              "</span></button>"
            );
          })
          .join("") +
        "</div></div></div>";
    }

    return (
      '<aside class="detail-panel"><div class="detail-heading"><div>' +
      '<p class="section-kicker">Traceability</p><h2>Element detail</h2></div>' +
      '<button class="panel-toggle" data-action="close-detail" title="Hide element detail" aria-label="Hide">«</button>' +
      "</div>" +
      body +
      "</aside>"
    );
  }

  function renderOverlays() {
    var html = "";
    if (state.legendOpen) {
      html +=
        '<div class="legend-panel" role="dialog" aria-label="Diagram legend">' +
        '<div class="legend-panel-head"><h3>Diagram legend</h3>' +
        '<button data-action="close-legend" aria-label="Close">×</button></div>' +
        '<p class="legend-panel-intro">How to read the process model extracted from the policy.</p>' +
        "<section><h4>Extraction markers</h4><ul>" +
        "<li><i class=\"chip chip-explicit\"></i><div><strong>Policy explicit</strong><span>Stated verbatim and linked to source.</span></div></li>" +
        "<li><i class=\"chip chip-inferred\"></i><div><strong>Inferred connector</strong><span>Connective step for readability — not an obligation.</span></div></li>" +
        "<li><i class=\"chip chip-prohibited\"></i><div><strong>Prohibited action</strong><span>Policy prohibition (negative outcome).</span></div></li>" +
        "<li><i class=\"chip chip-recommended\"></i><div><strong>Recommended control</strong><span>Suggested automation — not a policy obligation.</span></div></li>" +
        "</ul></section></div>";
    }
    if (state.duplicatesOpen && state.workflow) {
      var groups = buildDuplicateGroups(state.workflow);
      html +=
        '<div class="duplicates-panel" role="dialog" aria-label="Duplicated step labels">' +
        '<div class="legend-panel-head"><h3>Duplicated step labels</h3>' +
        '<button data-action="close-duplicates" aria-label="Close">×</button></div>';
      if (!groups.length) {
        html +=
          '<p class="duplicates-empty">No duplicated steps found for the workflow ' +
          escapeHtml(state.workflow.workflow_title) +
          "</p>";
      } else {
        if (!state.selectedDuplicateKey) state.selectedDuplicateKey = groups[0].key;
        var selectedGroup =
          groups.find(function (g) { return g.key === state.selectedDuplicateKey; }) ||
          groups[0];
        html +=
          '<p class="legend-panel-intro">Steps on this diagram that share the same label. Select a row to compare them side by side.</p>' +
          '<div class="duplicates-table-wrap"><table class="duplicates-table"><thead><tr><th>Shared label</th><th>Count</th><th>Step IDs</th></tr></thead><tbody>' +
          groups
            .map(function (g) {
              return (
                '<tr class="' +
                (state.selectedDuplicateKey === g.key ? "selected" : "") +
                '" data-action="select-dup" data-key="' +
                escapeAttr(g.key) +
                '"><td>' +
                escapeHtml(g.label) +
                "</td><td>" +
                g.hits.length +
                "</td><td>" +
                escapeHtml(g.hits.map(function (h) { return h.step_id; }).join(", ")) +
                "</td></tr>"
              );
            })
            .join("") +
          "</tbody></table></div>";
        if (selectedGroup) {
          var actorName = function (step) {
            var actor = (state.workflow.actors || []).find(function (a) {
              return a.actor_id === step.actor_id;
            });
            return actor ? actor.name : step.actor_id;
          };
          html +=
            '<section class="duplicates-compare"><h4>Side-by-side compare<span>' +
            selectedGroup.hits.length +
            " occurrences</span></h4>" +
            '<div class="compare-scroll"><table class="compare-table"><thead><tr><th class="compare-attr">Attribute</th>' +
            selectedGroup.hits
              .map(function (hit) {
                return (
                  "<th><span class=\"compare-col-id\">" +
                  escapeHtml(hit.step_id) +
                  '</span><button type="button" class="compare-jump" data-action="jump-dup" data-step="' +
                  escapeAttr(hit.step_id) +
                  '">Select</button></th>'
                );
              })
              .join("") +
            "</tr></thead><tbody>" +
            [
              ["Step ID", function (h) { return h.step_id; }],
              ["Label", function (h) { return h.title; }],
              ["Classification", function (h) { return String(h.action_type || "").replaceAll("_", " "); }],
              ["Step type", function (h) { return h.explicit_or_inferred; }],
              ["Actor", function (h) { return actorName(h); }],
              ["Outcome", function (h) { return h.path_outcome ? String(h.path_outcome).replaceAll("_", " ") : "—"; }],
              ["Policy wording", function (h) { return h.description || "—"; }],
            ]
              .map(function (row) {
                return (
                  '<tr><th class="compare-attr">' +
                  escapeHtml(row[0]) +
                  "</th>" +
                  selectedGroup.hits
                    .map(function (hit) {
                      return "<td>" + escapeHtml(row[1](hit)) + "</td>";
                    })
                    .join("") +
                  "</tr>"
                );
              })
              .join("") +
            "</tbody></table></div></section>";
        }
      }
      html += "</div>";
    }
    if (state.analyticsOpen && state.workflow) {
      var analytics = buildAnalysis(state.workflow);
      function rows(list, cols) {
        return list
          .map(function (row) {
            return (
              "<tr>" +
              cols
                .map(function (c) {
                  return "<td>" + escapeHtml(row[c] == null ? "—" : row[c]) + "</td>";
                })
                .join("") +
              "</tr>"
            );
          })
          .join("");
      }
      html +=
        '<div class="duplicates-panel analytics-panel" role="dialog" aria-label="Workflow analysis">' +
        '<div class="legend-panel-head"><h3>Workflow analysis</h3>' +
        '<button data-action="close-analytics" aria-label="Close">×</button></div>' +
        '<p class="legend-panel-intro">Structured statistics for <strong>' +
        escapeHtml(state.workflow.workflow_title) +
        "</strong>.</p>" +
        '<div class="analytics-body"><section class="analytics-section"><h4>1. Executive summary</h4>' +
        '<div class="duplicates-table-wrap"><table class="duplicates-table"><thead><tr><th>Metric</th><th>Value</th><th>Note</th></tr></thead><tbody>' +
        rows(analytics.summary, ["metric", "value", "note"]) +
        "</tbody></table></div></section>" +
        '<section class="analytics-section"><h4>2. Duplicated labels</h4>' +
        '<div class="duplicates-table-wrap"><table class="duplicates-table"><thead><tr><th>Label</th><th>Count</th><th>Step IDs</th></tr></thead><tbody>' +
        (analytics.duplicatedWithin.length
          ? rows(analytics.duplicatedWithin, ["label", "count", "detail"])
          : "<tr><td colspan=\"3\">None</td></tr>") +
        "</tbody></table></div></section>" +
        '<section class="analytics-section"><h4>3. Label frequency</h4>' +
        '<div class="duplicates-table-wrap"><table class="duplicates-table"><thead><tr><th>Label</th><th>Count</th><th>Step IDs</th></tr></thead><tbody>' +
        rows(analytics.labelFrequency, ["label", "count", "detail"]) +
        "</tbody></table></div></section>" +
        '<div class="analytics-grid">' +
        '<section class="analytics-section"><h4>4. By classification</h4><div class="duplicates-table-wrap"><table class="duplicates-table"><thead><tr><th>Action type</th><th>Steps</th></tr></thead><tbody>' +
        rows(analytics.byActionType, ["metric", "value"]) +
        "</tbody></table></div></section>" +
        '<section class="analytics-section"><h4>5. By step type</h4><div class="duplicates-table-wrap"><table class="duplicates-table"><thead><tr><th>Step type</th><th>Steps</th></tr></thead><tbody>' +
        rows(analytics.byStepType, ["metric", "value"]) +
        "</tbody></table></div></section>" +
        '<section class="analytics-section"><h4>6. By path outcome</h4><div class="duplicates-table-wrap"><table class="duplicates-table"><thead><tr><th>Outcome</th><th>Steps</th></tr></thead><tbody>' +
        rows(analytics.byOutcome, ["metric", "value"]) +
        "</tbody></table></div></section>" +
        '<section class="analytics-section"><h4>7. By actor</h4><div class="duplicates-table-wrap"><table class="duplicates-table"><thead><tr><th>Actor</th><th>Steps</th></tr></thead><tbody>' +
        rows(analytics.byActor, ["metric", "value"]) +
        "</tbody></table></div></section>" +
        "</div>" +
        '<section class="analytics-section"><h4>9. Recommended additional statistics</h4><ol class="analytics-recommendations">' +
        analytics.recommendations.map(function (r) { return "<li>" + escapeHtml(r) + "</li>"; }).join("") +
        "</ol></section></div></div>";
    }
    if (state.intelOpen && hasRoleRelevance()) {
      html += renderIntelligenceOverlay();
    }
    return html;
  }

  function intelAssocChips(ids, label) {
    if (!ids || !ids.length) {
      return '<p class="intel-assoc"><span>' + escapeHtml(label) + ":</span> <em class=\"muted\">none</em></p>";
    }
    return (
      '<p class="intel-assoc"><span>' +
      escapeHtml(label) +
      ":</span> " +
      ids
        .map(function (id) {
          return (
            '<span class="intel-chip" title="' +
            escapeAttr(id) +
            '">' +
            escapeHtml(entityLabel(id)) +
            " <code>" +
            escapeHtml(id) +
            "</code></span>"
          );
        })
        .join(" ") +
      "</p>"
    );
  }

  function renderIntelligenceOverlay() {
    var rr = DATA.role_relevance;
    var lens = state.lens;
    var html =
      '<div class="duplicates-panel intel-panel" role="dialog" aria-label="Role intelligence">' +
      '<div class="legend-panel-head"><h3>Role intelligence</h3>' +
      '<button data-action="close-intel" aria-label="Close">×</button></div>';

    if (lens === "main_view" || !isRoleLens(lens)) {
      var roleKeys = ["business_owner", "compliance_officer", "policy_owner"];
      html +=
        '<p class="legend-panel-intro">Shared <strong>main view</strong> — same canonical artifacts for every role. Pick a role in Intelligence lens to open that role’s dedicated tab (diagram + structured sections). No LLM call.</p>' +
        '<div class="intel-nav-hint">Policy Follower: Task → Rules → Actions → Proof · ' +
        "Compliance: Case → Risk → Rules → Checks · Policy Owner: Policy → Coverage → Gaps</div>" +
        '<div class="intel-list">';
      roleKeys.forEach(function (key) {
        var persp = (rr.perspectives && rr.perspectives[key]) || { assessments: [] };
        var count = (persp.assessments || []).length;
        html +=
          '<article class="intel-item relevance-primary"><div class="intel-head"><div class="intel-title"><strong>' +
          escapeHtml(LENS_LABELS[key]) +
          '</strong><code>' +
          escapeHtml(key) +
          "</code></div>" +
          '<span class="intel-badge">' +
          count +
          " items</span></div>" +
          '<p class="intel-why">Open this role from the Intelligence lens dropdown to view its structured page.</p></article>';
      });
      html += "</div></div>";
      return html;
    }

    var perspective = (rr.perspectives && rr.perspectives[lens]) || { assessments: [] };
    var assessments = (perspective.assessments || []).slice().sort(function (a, b) {
      var order = { PRIMARY: 0, SECONDARY: 1, UNCERTAIN: 2, NOT_RELEVANT: 3 };
      return (order[a.relevance] || 9) - (order[b.relevance] || 9);
    });
    html +=
      '<p class="legend-panel-intro">Precomputed lens for <strong>' +
      escapeHtml(LENS_LABELS[lens] || lens) +
      "</strong>. Same canonical artifacts; switching lenses does not call an LLM.</p>" +
      '<div class="intel-nav-hint">Policy Follower: Task → Rules → Actions → Proof · ' +
      "Compliance: Case → Risk → Rules → Checks · Policy Owner: Policy → Coverage → Gaps</div>";
    if (!assessments.length) {
      html += '<p class="duplicates-empty">No assessments for this lens.</p></div>';
      return html;
    }
    html += '<div class="intel-list">';
    assessments.forEach(function (item) {
      var tags = (item.lens_tags || [])
        .map(function (t) {
          return '<span class="intel-tag">' + escapeHtml(String(t).replaceAll("_", " ")) + "</span>";
        })
        .join("");
      html +=
        '<article class="intel-item relevance-' +
        escapeAttr(String(item.relevance || "").toLowerCase()) +
        '"><div class="intel-head"><div class="intel-title">' +
        "<strong>" +
        escapeHtml(entityLabel(item.artifact_id)) +
        '</strong><code>' +
        escapeHtml(item.artifact_id) +
        "</code></div>" +
        '<span class="intel-badge">' +
        escapeHtml(item.relevance || "") +
        "</span>" +
        '<span class="intel-badge soft">' +
        escapeHtml(item.interpretation_basis || "") +
        "</span>" +
        '<span class="intel-badge soft">' +
        escapeHtml(item.artifact_type || "") +
        "</span></div>" +
        (tags ? '<div class="intel-tags">' + tags + "</div>" : "") +
        '<p class="intel-why">' +
        escapeHtml(item.why_relevant || "") +
        "</p>" +
        intelAssocChips(item.associated_action_ids, "Actions") +
        intelAssocChips(item.associated_risk_ids, "Risks") +
        intelAssocChips(item.associated_control_ids, "Controls") +
        intelAssocChips(item.associated_evidence_ids, "Evidence") +
        intelAssocChips(item.source_refs, "Sources") +
        "</article>";
    });
    html += "</div></div>";
    return html;
  }

  function renderOverviewBar() {
    if (
      !state.workflow ||
      state.workflow.workflow_id !== "PTP-POLICY" ||
      !state.workflow.high_level_plan
    ) {
      return "";
    }
    var phases = state.workflow.high_level_plan;
    var html =
      '<div class="overview-bar">' +
      '<button class="overview-toggle' +
      (state.overviewOpen ? " open" : "") +
      '" data-action="toggle-overview">Overview</button>' +
      '<div class="overview-bar-phases">' +
      phases
        .map(function (phase) {
          var active =
            state.selected &&
            state.selected.kind === "phase" &&
            state.selected.data.phase === phase.phase;
          return (
            '<button class="overview-phase-pill' +
            (active ? " active" : "") +
            '" data-action="select-phase" data-phase="' +
            escapeAttr(String(phase.phase)) +
            '">' +
            escapeHtml(phase.phase) +
            ". " +
            escapeHtml(phase.title) +
            "</button>"
          );
        })
        .join("") +
      "</div></div>";
    if (state.overviewOpen) {
      html +=
        '<div class="policy-overview">' +
        (state.workflow.purpose
          ? '<div class="overview-purpose"><span class="overview-purpose-kicker">Policy purpose</span><p>' +
            escapeHtml(state.workflow.purpose) +
            "</p></div>"
          : "") +
        '<div class="overview-phases"><span class="overview-phases-heading">Compliance lifecycle — 5 phases</span>' +
        '<div class="overview-phase-list">' +
        phases
          .map(function (phase) {
            return (
              '<div class="phase-card" data-action="select-phase" data-phase="' +
              escapeAttr(String(phase.phase)) +
              '"><span class="phase-card-num">Phase ' +
              escapeHtml(phase.phase) +
              '</span><p class="phase-card-title">' +
              escapeHtml(phase.title) +
              '</p><p class="phase-card-desc">' +
              escapeHtml(phase.description) +
              "</p></div>"
            );
          })
          .join("") +
        "</div></div></div>";
    }
    return html;
  }

  function render() {
    var root = $("#root");
    if (!root) return;
    var wf = state.workflow;
    var review = wf ? getStoredReview(wf.workflow_id, wf.review_status) : "PENDING";
    var canApprove = SHOW_REVIEW_ACCESS && state.role === "POLICY_OWNER";
    var explicitCount = wf
      ? (wf.steps || []).filter(function (s) { return s.explicit_or_inferred === "EXPLICIT"; }).length
      : 0;
    var inferredCount = wf ? (wf.steps || []).length - explicitCount : 0;
    var activeIndex = state.index.find(function (i) { return i.workflow_id === state.activeId; });

    var pid = policyId();
    document.title = pid ? pid + " · Policy Process Review" : "Policy Process Review (Offline)";

    root.innerHTML =
      '<main class="app-shell">' +
      '<header class="topbar"><div class="brand"><div class="brand-mark" aria-hidden="true"><span></span><span></span><span></span></div><div>' +
      '<p class="eyebrow">Policy intelligence / workflow review' +
      (pid ? " · " + escapeHtml(pid) : "") +
      "</p>" +
      "<h1>Personal Trading Policy</h1></div></div>" +
      '<div class="header-status">' +
      (SHOW_REVIEW_ACCESS
        ? '<label class="role-switch"><span>Review access</span>' +
          '<select data-action="set-role" aria-label="Review access role">' +
          '<option value="VIEWER"' +
          (state.role === "VIEWER" ? " selected" : "") +
          ">Viewer</option>" +
          '<option value="POLICY_OWNER"' +
          (state.role === "POLICY_OWNER" ? " selected" : "") +
          ">Policy owner</option></select></label>"
        : "") +
      (hasRoleRelevance()
        ? '<label class="role-switch lens-switch"><span>Intelligence lens</span>' +
          '<select data-action="set-lens" aria-label="Intelligence lens">' +
          Object.keys(LENS_LABELS)
            .map(function (key) {
              return (
                '<option value="' +
                escapeAttr(key) +
                '"' +
                (state.lens === key ? " selected" : "") +
                ">" +
                escapeHtml(LENS_LABELS[key]) +
                "</option>"
              );
            })
            .join("") +
          "</select></label>" +
          (state.roleTabBlocked
            ? '<span class="role-tab-blocked" title="Browser blocked the role tab">Allow pop-ups to open role view</span>'
            : "")
        : "") +
      '<span class="separator"></span><span class="status-dot"></span><span>Offline workspace</span>' +
      '<span class="separator"></span><span>' +
      state.index.length +
      " workflows</span></div></header>" +
      '<div class="workspace' +
      (state.detailOpen ? "" : " detail-collapsed") +
      '">' +
      '<aside class="workflow-rail"><div class="rail-heading"><div><p class="section-kicker">Process repository</p><h2>Workflows</h2></div>' +
      '<span class="count-badge">' +
      state.index.length +
      "</span></div>" +
      '<label class="search-box"><span aria-hidden="true">⌕</span>' +
      '<input data-action="filter" value="' +
      escapeAttr(state.query) +
      '" placeholder="Filter workflows" aria-label="Filter workflows" /></label>' +
      '<nav class="workflow-list" aria-label="Policy workflows">' +
      visibleIndex()
        .map(function (item, index) {
          return (
            '<button class="workflow-item' +
            (item.workflow_id === state.activeId ? " active" : "") +
            '" data-action="select-workflow" data-id="' +
            escapeAttr(item.workflow_id) +
            '"><span class="workflow-number">' +
            String(index + 1).padStart(2, "0") +
            '</span><span class="workflow-copy"><strong>' +
            escapeHtml(item.title) +
            "</strong><small>" +
            escapeHtml(item.steps) +
            " actions</small></span></button>"
          );
        })
        .join("") +
      "</nav></aside>" +
      '<section class="diagram-panel"><div class="diagram-heading"><div class="diagram-title">' +
      '<div class="id-row"><span>' +
      escapeHtml((wf && wf.workflow_id) || "—") +
      "</span>" +
      (canApprove && wf
        ? '<label class="review-status-control"><select class="review-pill editable status-' +
          review.toLowerCase() +
          '" data-action="set-review" aria-label="Set review status">' +
          '<option value="PENDING"' +
          (review === "PENDING" ? " selected" : "") +
          ">PENDING</option>" +
          '<option value="APPROVED"' +
          (review === "APPROVED" ? " selected" : "") +
          ">APPROVED</option></select></label>"
        : '<span class="review-pill status-' +
          review.toLowerCase() +
          '">' +
          (wf ? review : "Loading") +
          "</span>") +
      "</div><h2>" +
      escapeHtml((wf && wf.workflow_title) || "Loading workflow…") +
      "</h2><p>" +
      escapeHtml((wf && wf.workflow_summary) || "") +
      "</p></div>" +
      '<div class="diagram-actions"><div class="zoom-group">' +
      (hasRoleRelevance()
        ? '<button class="' +
          (state.intelOpen ? "active" : "") +
          '" data-action="toggle-intel" title="Role intelligence" aria-label="Role intelligence">◎</button>'
        : "") +
      '<button class="' +
      (state.analyticsOpen ? "active" : "") +
      '" data-action="toggle-analytics" title="Workflow analysis" aria-label="Workflow analysis">?</button>' +
      '<button class="' +
      (state.duplicatesOpen ? "active" : "") +
      '" data-action="toggle-duplicates" title="Duplicated labels" aria-label="Duplicated labels">⧉</button>' +
      '<button class="' +
      (state.legendOpen ? "active" : "") +
      '" data-action="toggle-legend" title="Legend" aria-label="Legend">ℹ</button>' +
      '<button data-action="zoom-out" title="Zoom out" aria-label="Zoom out">−</button>' +
      '<button data-action="zoom-in" title="Zoom in" aria-label="Zoom in">+</button>' +
      '<button data-action="fit" title="Fit diagram" aria-label="Fit diagram">⛶</button>' +
      "</div>" +
      '<button class="export-button" data-action="reset" ' +
      (state.dirty ? "" : "disabled ") +
      'title="Reset layout">Reset</button>' +
      '<button class="export-button" data-action="save" title="Save layout to downloads + localStorage">Save layout</button>' +
      "</div>" +
      (state.saveNotice ? '<p class="save-notice">' + escapeHtml(state.saveNotice) + "</p>" : "") +
      "</div>" +
      renderOverviewBar() +
      '<div class="diagram-stage">' +
      (state.loading
        ? '<div class="stage-state loading"><span>Rendering process model</span></div>'
        : "") +
      (state.error
        ? '<div class="stage-state error"><span>' + escapeHtml(state.error) + "</span></div>"
        : "") +
      '<div class="bpmn-canvas"></div>' +
      renderOverlays() +
      "</div>" +
      '<div class="stage-bar" ' +
      (state.dirty ? "" : "hidden") +
      '><div class="layout-badge">Layout edited — Save layout to keep it</div></div>' +
      '<footer class="diagram-footer"><div><span class="footer-label">Model integrity</span><strong>' +
      ((activeIndex && activeIndex.validation_errors) || 0) +
      " validation errors</strong></div>" +
      '<div><span class="footer-label">Actions</span><strong>' +
      explicitCount +
      " explicit / " +
      inferredCount +
      " inferred</strong></div></footer></section>" +
      renderDetail() +
      "</div></main>";
  }

  function bindEvents(root) {
    if (!root || root.getAttribute("data-bound") === "1") return;
    root.setAttribute("data-bound", "1");
    root.addEventListener("click", function (event) {
      var target = event.target.closest("[data-action]");
      if (!target) return;
      var action = target.getAttribute("data-action");
      if (action === "select-workflow") {
        state.activeId = target.getAttribute("data-id");
        loadWorkflow(state.activeId);
        render();
        renderDiagram();
      } else if (action === "open-detail") {
        state.detailOpen = true;
        patchDetail();
      } else if (action === "close-detail") {
        state.detailOpen = false;
        patchDetail();
      } else if (action === "toggle-legend") {
        state.legendOpen = !state.legendOpen;
        state.duplicatesOpen = false;
        state.analyticsOpen = false;
        state.intelOpen = false;
        patchOverlays();
      } else if (action === "close-legend") {
        state.legendOpen = false;
        patchOverlays();
      } else if (action === "toggle-duplicates") {
        state.duplicatesOpen = !state.duplicatesOpen;
        state.legendOpen = false;
        state.analyticsOpen = false;
        state.intelOpen = false;
        patchOverlays();
      } else if (action === "close-duplicates") {
        state.duplicatesOpen = false;
        patchOverlays();
      } else if (action === "toggle-analytics") {
        state.analyticsOpen = !state.analyticsOpen;
        state.legendOpen = false;
        state.duplicatesOpen = false;
        state.intelOpen = false;
        patchOverlays();
      } else if (action === "close-analytics") {
        state.analyticsOpen = false;
        patchOverlays();
      } else if (action === "toggle-intel") {
        if (!hasRoleRelevance()) return;
        state.intelOpen = !state.intelOpen;
        state.legendOpen = false;
        state.duplicatesOpen = false;
        state.analyticsOpen = false;
        patchOverlays();
      } else if (action === "close-intel") {
        state.intelOpen = false;
        patchOverlays();
      } else if (action === "select-dup") {
        state.selectedDuplicateKey = target.getAttribute("data-key");
        patchOverlays();
      } else if (action === "jump-dup") {
        var stepId = target.getAttribute("data-step");
        var step = (state.workflow.steps || []).find(function (s) {
          return s.step_id === stepId;
        });
        if (step) {
          state.selected = { kind: "step", data: step };
          state.detailOpen = true;
          state.duplicatesOpen = false;
          patchOverlays();
          patchDetail();
        }
      } else if (action === "zoom-in") {
        zoom(1);
      } else if (action === "zoom-out") {
        zoom(-1);
      } else if (action === "fit") {
        fitViewport();
      } else if (action === "reset") {
        resetLayout();
      } else if (action === "save") {
        saveLayout();
      } else if (action === "toggle-overview") {
        state.overviewOpen = !state.overviewOpen;
        softRefreshChrome();
      } else if (action === "select-phase") {
        var phaseId = target.getAttribute("data-phase");
        var phase = (state.workflow.high_level_plan || []).find(function (p) {
          return String(p.phase) === String(phaseId);
        });
        if (phase) {
          state.selected = { kind: "phase", data: phase };
          state.detailOpen = true;
          patchDetail();
        }
      } else if (action === "toggle-code") {
        var wrap = target.closest(".code-chip-wrap");
        var panel = wrap && wrap.querySelector(".code-explainer");
        if (panel) panel.hidden = !panel.hidden;
      } else if (action === "close-code") {
        var explainer = target.closest(".code-explainer");
        if (explainer) explainer.hidden = true;
      }
    });

    root.addEventListener("change", function (event) {
      var target = event.target;
      var action = target.getAttribute("data-action");
      if (action === "set-role") setRole(target.value);
      if (action === "set-lens") setLens(target.value);
      if (action === "set-review") setReviewStatus(target.value);
    });

    root.addEventListener("input", function (event) {
      var target = event.target;
      if (target.getAttribute("data-action") === "filter") {
        state.query = target.value;
        var nav = $(".workflow-list");
        if (!nav) return;
        // Re-render list only without destroying the diagram.
        var keepCanvas = $(".bpmn-canvas");
        var modeler = state.modeler;
        state.modeler = null; // prevent destroy during partial update
        var html = visibleIndex()
          .map(function (item, index) {
            return (
              '<button class="workflow-item' +
              (item.workflow_id === state.activeId ? " active" : "") +
              '" data-action="select-workflow" data-id="' +
              escapeAttr(item.workflow_id) +
              '"><span class="workflow-number">' +
              String(index + 1).padStart(2, "0") +
              '</span><span class="workflow-copy"><strong>' +
              escapeHtml(item.title) +
              "</strong><small>" +
              escapeHtml(item.steps) +
              " actions</small></span></button>"
            );
          })
          .join("");
        nav.innerHTML = html;
        state.modeler = modeler;
        void keepCanvas;
      }
    });
  }

  function boot() {
    if (!state.index.length) {
      document.body.innerHTML =
        "<p style=\"font-family:sans-serif;padding:2rem\">No P2B_DATA index found. Run the notebook offline pack builder.</p>";
      return;
    }
    bindEvents($("#root"));
    loadWorkflow(state.activeId);
    render();
    renderDiagram();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
