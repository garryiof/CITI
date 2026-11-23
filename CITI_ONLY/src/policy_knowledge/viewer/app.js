/* Offline policy demo — classic scripts only; no fetch/CDN/ES modules. */
(function () {
  var data = window.POLICY_DEMO_DATA || {};
  var selectedId = null;
  var ROLE_KEY = "pk-intelligence-role";
  var ROLE_LABELS = {
    business_owner: "Business Owner",
    compliance_officer: "Compliance Officer",
    policy_owner: "Policy Owner"
  };

  function $(id) { return document.getElementById(id); }

  function setText(el, text) {
    if (el) el.textContent = text == null ? "" : String(text);
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function readRole() {
    try {
      var stored = window.localStorage.getItem(ROLE_KEY);
      if (stored && ROLE_LABELS[stored]) return stored;
    } catch (err) { /* ignore */ }
    return "business_owner";
  }

  function writeRole(role) {
    try { window.localStorage.setItem(ROLE_KEY, role); } catch (err) { /* ignore */ }
  }

  function currentRole() {
    var select = $("role-select");
    return (select && select.value) || readRole();
  }

  function entityLabel(id) {
    var keys = ["requirements", "roles", "actions", "risks", "controls", "evidence", "sources"];
    var i, j, items, item;
    for (i = 0; i < keys.length; i++) {
      items = data[keys[i]] || [];
      for (j = 0; j < items.length; j++) {
        item = items[j];
        if (item.id === id) {
          return item.name || item.label || item.text || item.id;
        }
      }
    }
    var findings = data.findings || [];
    for (j = 0; j < findings.length; j++) {
      if (findings[j].id === id) return findings[j].description || id;
    }
    return id;
  }

  function renderOverview() {
    var panel = $("tab-overview");
    var p = data.policy || {};
    var rr = data.role_relevance;
    var role = currentRole();
    var count = 0;
    if (rr && rr.perspectives && rr.perspectives[role]) {
      count = (rr.perspectives[role].assessments || []).length;
    }
    panel.innerHTML =
      "<p><strong>Policy ID:</strong> " + escapeHtml(p.id || "") + "</p>" +
      "<p><strong>Version:</strong> " + escapeHtml(p.version || "not_specified") + "</p>" +
      "<p><strong>Requirements:</strong> " + ((data.requirements || []).length) + "</p>" +
      "<p><strong>Actions:</strong> " + ((data.actions || []).length) + "</p>" +
      "<p><strong>Role lens:</strong> " + escapeHtml(ROLE_LABELS[role] || role) +
      " (" + count + " assessments)</p>" +
      "<p class=\"muted\">Snapshot generated at processing time. Not a live policy source. Role switching uses precomputed artifacts only.</p>";
  }

  function renderList(panelId, items, labelFn) {
    var panel = $(panelId);
    if (!items || !items.length) {
      panel.innerHTML = "<p class=\"muted\">None</p>";
      return;
    }
    var html = "<ul class=\"cardless-list\">";
    items.forEach(function (item) {
      html += "<li><button type=\"button\" data-id=\"" + escapeHtml(item.id) + "\">" +
        escapeHtml(labelFn(item)) + "</button></li>";
    });
    html += "</ul>";
    panel.innerHTML = html;
    panel.querySelectorAll("button[data-id]").forEach(function (btn) {
      btn.addEventListener("click", function () { selectEntity(btn.getAttribute("data-id")); });
    });
  }

  function idChips(ids, kind) {
    if (!ids || !ids.length) return "<span class=\"muted\">none</span>";
    return ids.map(function (id) {
      return "<button type=\"button\" class=\"chip\" data-id=\"" + escapeHtml(id) +
        "\" data-kind=\"" + escapeHtml(kind || "entity") + "\">" +
        escapeHtml(entityLabel(id)) + " <code>" + escapeHtml(id) + "</code></button>";
    }).join(" ");
  }

  function renderIntelligence() {
    var panel = $("tab-intelligence");
    var rr = data.role_relevance;
    var role = currentRole();
    if (!rr || !rr.perspectives) {
      panel.innerHTML = "<p class=\"muted\">No role_relevance artifact in this demo package.</p>";
      return;
    }
    var perspective = rr.perspectives[role] || { assessments: [] };
    var assessments = (perspective.assessments || []).slice().sort(function (a, b) {
      var order = { PRIMARY: 0, SECONDARY: 1, UNCERTAIN: 2, NOT_RELEVANT: 3 };
      return (order[a.relevance] || 9) - (order[b.relevance] || 9);
    });
    var html = "<p class=\"intel-intro\">Precomputed lens for <strong>" +
      escapeHtml(ROLE_LABELS[role] || role) +
      "</strong>. Same artifacts; switching roles does not call an LLM.</p>";
    if (!assessments.length) {
      html += "<p class=\"muted\">No assessments for this role.</p>";
      panel.innerHTML = html;
      return;
    }
    html += "<ul class=\"intel-list\">";
    assessments.forEach(function (item) {
      html += "<li class=\"intel-item relevance-" + escapeHtml(String(item.relevance || "").toLowerCase()) + "\">" +
        "<div class=\"intel-head\">" +
          "<button type=\"button\" class=\"intel-artifact\" data-id=\"" + escapeHtml(item.artifact_id) + "\">" +
            escapeHtml(entityLabel(item.artifact_id)) +
            " <code>" + escapeHtml(item.artifact_id) + "</code>" +
          "</button>" +
          "<span class=\"badge\">" + escapeHtml(item.relevance || "") + "</span>" +
          "<span class=\"badge soft\">" + escapeHtml(item.interpretation_basis || "") + "</span>" +
          (item.confidence != null ? "<span class=\"badge soft\">conf " + escapeHtml(item.confidence) + "</span>" : "") +
        "</div>" +
        "<p class=\"why\">" + escapeHtml(item.why_relevant || "") + "</p>" +
        "<p class=\"assoc\"><span>Actions:</span> " + idChips(item.associated_action_ids, "action") + "</p>" +
        "<p class=\"assoc\"><span>Risks:</span> " + idChips(item.associated_risk_ids, "risk") + "</p>" +
        "<p class=\"assoc\"><span>Controls:</span> " + idChips(item.associated_control_ids, "control") + "</p>" +
        "<p class=\"assoc\"><span>Evidence:</span> " + idChips(item.associated_evidence_ids, "evidence") + "</p>" +
        "<p class=\"assoc\"><span>Sources:</span> " + idChips(item.source_refs, "source") + "</p>" +
      "</li>";
    });
    html += "</ul>";
    panel.innerHTML = html;
    panel.querySelectorAll("button[data-id]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-id");
        selectEntity(id);
        if ((btn.getAttribute("data-kind") === "source") || (id && id.indexOf("SRC-") === 0)) {
          showTab("sources");
        }
      });
    });
  }

  function renderOkf() {
    var panel = $("tab-okf");
    var rows = (data.okf_index || []).map(function (row) {
      return "<li>" + escapeHtml(row) + "</li>";
    }).join("");
    panel.innerHTML = rows ? "<ul class=\"cardless-list\">" + rows + "</ul>" : "<p class=\"muted\">No OKF index</p>";
  }

  function renderSources() {
    var panel = $("tab-sources");
    var sources = data.sources || [];
    if (!sources.length) {
      panel.innerHTML = "<p class=\"muted\">No sources in this demo mode</p>";
      return;
    }
    var html = "<ul class=\"cardless-list\">";
    sources.forEach(function (s) {
      html += "<li><button type=\"button\" data-id=\"" + escapeHtml(s.id) + "\"><code>" +
        escapeHtml(s.id) + "</code> — " + escapeHtml(s.excerpt || s.section_path || "") +
        "</button></li>";
    });
    html += "</ul>";
    panel.innerHTML = html;
    panel.querySelectorAll("button[data-id]").forEach(function (btn) {
      btn.addEventListener("click", function () { selectEntity(btn.getAttribute("data-id")); });
    });
  }

  function renderQa() {
    var panel = $("tab-qa");
    var findings = data.findings || [];
    var html = "<p>Interactive ready: " + !!data.interactive_ready + "</p>";
    html += "<p>Browser verification: " + (data.browser_test || "BROWSER_TEST_NOT_RUN") + "</p>";
    html += "<ul class=\"cardless-list\">";
    findings.forEach(function (f) {
      html += "<li>[" + escapeHtml(f.severity) + "] " + escapeHtml(f.category) + ": " +
        escapeHtml(f.description) + "</li>";
    });
    html += "</ul>";
    panel.innerHTML = html;
  }

  function selectEntity(id) {
    selectedId = id;
    var box = $("selection");
    box.hidden = false;
    var hit = null;
    ["requirements", "roles", "actions", "risks", "controls", "evidence", "sources"].forEach(function (key) {
      (data[key] || []).forEach(function (item) {
        if (item.id === id) hit = item;
      });
    });
    setText(box, hit ? ("Selected " + id + ": " + JSON.stringify(hit)) : ("Selected " + id));
  }

  function showTab(tabName) {
    document.querySelectorAll("#tabs button").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-tab") === tabName);
    });
    document.querySelectorAll(".tab-panel").forEach(function (p) {
      p.classList.toggle("active", p.id === "tab-" + tabName);
    });
  }

  function initMap() {
    var status = $("map-status");
    if (!data.interactive_ready || typeof window.cytoscape !== "function") {
      setText(status, "Knowledge Map interactive view unavailable (vendor assets not ready).");
      return;
    }
    window.cytoscape({
      container: $("cy"),
      elements: data.cy_elements || [],
      style: [
        { selector: "node", style: { label: "data(label)", "background-color": "#0f5c4c", color: "#123", "font-size": 10 } },
        { selector: "edge", style: { width: 2, "line-color": "#8aa396", "target-arrow-shape": "triangle" } }
      ],
      layout: { name: "cose" }
    });
  }

  function initBpmn() {
    var status = $("bpmn-status");
    if (data.no_process) {
      setText(status, "No supported BPMN process for this policy.");
      return;
    }
    if (!data.interactive_ready || typeof window.BpmnJS !== "function") {
      setText(status, "BPMN interactive view unavailable (vendor assets not ready).");
      return;
    }
    var viewer = new window.BpmnJS({ container: "#bpmn-canvas" });
    viewer.importXML(data.bpmn_xml || "").catch(function () {
      setText(status, "BPMN XML could not be rendered.");
    });
  }

  function wireTabs() {
    document.querySelectorAll("#tabs button").forEach(function (btn) {
      btn.addEventListener("click", function () {
        showTab(btn.getAttribute("data-tab"));
      });
    });
  }

  function wireRoleSelect() {
    var select = $("role-select");
    if (!select) return;
    select.value = readRole();
    select.addEventListener("change", function () {
      writeRole(select.value);
      renderOverview();
      renderIntelligence();
      showTab("intelligence");
    });
  }

  setText($("policy-title"), (data.policy && data.policy.title) || "Policy");
  setText($("demo-mode"), "Demo mode: " + (data.mode || "unknown") + " — " + (data.mode_note || ""));
  wireRoleSelect();
  renderOverview();
  renderIntelligence();
  renderList("tab-roles", data.roles || [], function (r) { return r.name; });
  renderList("tab-risks", (data.risks || []).concat(data.controls || []), function (r) { return (r.name || r.id); });
  renderOkf();
  renderSources();
  renderQa();
  wireTabs();
  initMap();
  initBpmn();
})();
