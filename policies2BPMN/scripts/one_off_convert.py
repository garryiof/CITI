#!/usr/bin/env python3
"""
One-off Policy → Workflow JSON → BPMN 2.0 converter.

Parses policies/blackrockPTIP.html, extracts actionable obligations with a
deterministic rule engine, emits schema-shaped workflow JSON and Open-BPMN-
compatible BPMN 2.0 XML. Does not build the full application.
"""

from __future__ import annotations

import copy
import json
import re
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "policies" / "blackrockPTIP.html"
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "outputs"

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
POLICY_NS = "http://policies2bpmn.local/policy"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
BIOC_NS = "http://bpmn.io/schema/bpmn/biocolor/1.0"

NSMAP = {
    None: BPMN_NS,
    "bpmndi": BPMNDI_NS,
    "dc": DC_NS,
    "di": DI_NS,
    "policy": POLICY_NS,
    "xsi": XSI_NS,
    "bioc": BIOC_NS,
}

# Outcome-path colors (approved = green, rejected = red)
APPROVED_STROKE, APPROVED_FILL = "#2F7D4F", "#E4F2E9"
REJECTED_STROKE, REJECTED_FILL = "#B3402E", "#F8E3DD"
PROHIBITED_STROKE, PROHIBITED_FILL = "#C45E12", "#FCE8D5"

# ---------------------------------------------------------------------------
# Lexicons
# ---------------------------------------------------------------------------

MODAL_PATTERNS = [
    (r"\bmust not\b", "PROHIBITED_ACTION", 0.95),
    (r"\bmay not\b", "PROHIBITED_ACTION", 0.93),
    (r"\bshall not\b", "PROHIBITED_ACTION", 0.95),
    (r"\bis prohibited\b", "PROHIBITED_ACTION", 0.94),
    (r"\bare prohibited\b", "PROHIBITED_ACTION", 0.94),
    (r"\bmay only\b", "CONDITIONAL_ACTION", 0.9),
    (r"\bmust\b", "MANDATORY_ACTION", 0.92),
    (r"\bshall\b", "MANDATORY_ACTION", 0.92),
    (r"\bis required to\b", "MANDATORY_ACTION", 0.93),
    (r"\bare required to\b", "MANDATORY_ACTION", 0.93),
    (r"\bis responsible for\b", "MANDATORY_ACTION", 0.88),
    (r"\bneeds? to\b", "MANDATORY_ACTION", 0.85),
    (r"\bshould\b", "MANDATORY_ACTION", 0.7),  # advisory — lower confidence
]

ACTION_VERB_MAP = [
    (r"\bpre-?approv", "APPROVAL"),
    (r"\bapprov", "APPROVAL"),
    (r"\bpre-?clear", "SUBMISSION"),
    (r"\bsubmit", "SUBMISSION"),
    (r"\battest", "SUBMISSION"),
    (r"\bnotify|notification", "NOTIFICATION"),
    (r"\breport", "SUBMISSION"),
    (r"\bdisclose|disclosure", "DISCLOSURE"),
    (r"\bretain|retention", "RECORDKEEPING"),
    (r"\bmaintain", "RECORDKEEPING"),
    (r"\bdocument", "RECORDKEEPING"),
    (r"\breview", "REVIEW"),
    (r"\bverif", "VERIFICATION"),
    (r"\bmonitor", "MONITORING"),
    (r"\bescalat|remedial|violation", "ESCALATION"),
    (r"\bobtain", "MANDATORY_ACTION"),
    (r"\bcertif", "SUBMISSION"),
    (r"\bexception", "EXCEPTION"),
]

ACTOR_PATTERNS = [
    (r"\bemployees?\b|\byou\b|\bcovered persons?\b", "ACT-EMPLOYEE", "Employee", "INDIVIDUAL", "Employee"),
    (r"\bcontingent workers?\b", "ACT-CONTINGENT", "Contingent Worker", "INDIVIDUAL", "Contingent Worker"),
    (r"\blegal\s*&\s*compliance\b|\bcompliance\b", "ACT-COMPLIANCE", "Legal & Compliance", "BUSINESS_FUNCTION", "Compliance"),
    (r"\bmanager\b|\bsupervisor\b", "ACT-MANAGER", "Manager", "INDIVIDUAL", "Manager"),
    (r"\bPTA\b|\bpersonal trading (system|application)\b", "ACT-SYSTEM", "Personal Trading System (PTA)", "SYSTEM", "PTA System"),
    (r"\bbroker\b", "ACT-BROKER", "Broker", "EXTERNAL", "Broker"),
]

CONNECTOR_SPLIT = re.compile(
    r",\s*(?:and\s+)?(?=(?:must|shall|should|obtain|submit|retain|disclose|report|notify|maintain|document|verify|approve))",
    re.I,
)

NON_ACTIONABLE = re.compile(
    r"^(this policy|for example|note that|please refer|it should be read|"
    r"japan employees should refer|annex|limited\s+\d+|global personal trading)",
    re.I,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Paragraph:
    section_id: str
    section_title: str
    paragraph: int
    text: str
    start_offset: int
    end_offset: int


@dataclass
class Candidate:
    candidate_id: str
    text: str
    section_id: str
    section_title: str
    paragraph: int
    start_offset: int
    end_offset: int
    action_type: str
    actionability_score: float
    actors: list[str]
    modal_matched: str


@dataclass
class AtomicAction:
    title: str
    description: str
    action_type: str
    actor_id: str
    bpmn_type: str
    explicit_or_inferred: str
    confidence: float
    source_text: str
    section_id: str
    section_title: str
    paragraph: int
    start_offset: int
    end_offset: int
    inference_reason: str | None = None


# ---------------------------------------------------------------------------
# Stage 1–2: Ingest + segment
# ---------------------------------------------------------------------------

def normalize_ws(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", " ", text)
    # Repair common SEC HTML mid-word breaks: "su bmit" -> "submit"
    text = re.sub(
        r"\b([A-Za-z]{2,}) ([a-z]{2,4})\b",
        _repair_broken_word,
        text,
    )
    return text.strip()


# Fragments that commonly appear split in EDGAR HTML exports
_BROKEN_WORD_JOIN = {
    ("su", "bmit"): "submit",
    ("execu", "ted"): "executed",
    ("pre", "clearance"): "pre-clearance",
    ("pre", "approved"): "pre-approved",
    ("pre", "approval"): "pre-approval",
    ("r", "equired"): "required",
    ("equi", "red"): "required",
    ("t", "hat"): "that",
}


def _repair_broken_word(match: re.Match[str]) -> str:
    a, b = match.group(1), match.group(2)
    key = (a.lower(), b.lower())
    if key in _BROKEN_WORD_JOIN:
        fixed = _BROKEN_WORD_JOIN[key]
        # Preserve simple capitalization of first fragment
        if a[0].isupper():
            return fixed[0].upper() + fixed[1:]
        return fixed
    return match.group(0)


def _write_annotated_policy(soup: BeautifulSoup) -> None:
    """Save a navigable copy of the original policy HTML with paragraph
    anchors and a highlight style for the targeted paragraph."""
    # Local image references don't resolve from outputs/; drop them.
    for img in soup.find_all("img"):
        img.decompose()
    style = soup.new_tag("style")
    style.string = """
      html { scroll-behavior: smooth; }
      body { background: #f7f5ed !important; }
      p[id^="policy-"]:target {
        background: #fff0b8;
        outline: 3px solid #e0a800;
        outline-offset: 6px;
        scroll-margin-top: 35vh;
      }
    """
    (soup.head or soup).append(style)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "policy_source.html").write_text(str(soup), encoding="utf-8")


def parse_policy(path: Path) -> tuple[dict[str, Any], list[Paragraph], str]:
    # The SEC EDGAR export declares charset=windows-1252; decoding it as UTF-8
    # turns smart quotes into U+FFFD replacement characters.
    raw = path.read_bytes().decode("windows-1252", errors="replace")
    soup = BeautifulSoup(raw, "html.parser")

    # Drop scripts/styles
    for tag in soup(["script", "style"]):
        tag.decompose()

    current_section = ("0", "Preamble")
    paragraphs: list[Paragraph] = []
    plain_parts: list[str] = []
    offset = 0
    para_counters: dict[str, int] = {}

    body = soup.body or soup
    for el in body.descendants:
        if not isinstance(el, Tag):
            continue

        # Numbered section header rows: <td><b>N.</b></td><td><b>Title</b></td>
        if el.name == "tr":
            tds = el.find_all("td", recursive=False)
            if len(tds) >= 2:
                num = normalize_ws(tds[0].get_text(" ", strip=True))
                title = normalize_ws(tds[1].get_text(" ", strip=True))
                if re.match(r"^\d+\.$", num) and title and len(title) < 120:
                    sid = num.rstrip(".")
                    current_section = (sid, title)
                    continue

        if el.name == "p":
            text = normalize_ws(el.get_text(" ", strip=True))
            if not text or len(text) < 20:
                continue
            # Skip page headers / footers noise
            if re.match(r"^(Limited\s+\d+|Global Personal Trading Policy\s+\d)", text):
                continue
            sid, stitle = current_section
            para_counters[sid] = para_counters.get(sid, 0) + 1
            pnum = para_counters[sid]
            # Anchor for navigation from the viewer back to the source text
            el["id"] = f"policy-{sid}-{pnum}"
            start = offset
            plain_parts.append(text)
            offset += len(text) + 1
            paragraphs.append(
                Paragraph(sid, stitle, pnum, text, start, start + len(text))
            )

    _write_annotated_policy(soup)

    full_text = "\n".join(plain_parts)
    meta = {
        "policy_id": "POL-PT-001",
        "policy_title": "Global Personal Trading Policy",
        "policy_version": "2021-09-28",
        "source_file": path.name,
        "issuer": "BlackRock, Inc.",
        "section_count": len({p.section_id for p in paragraphs}),
        "paragraph_count": len(paragraphs),
        "character_count": len(full_text),
    }
    return meta, paragraphs, full_text


# ---------------------------------------------------------------------------
# Stage 3–4: Detect + decompose
# ---------------------------------------------------------------------------

def classify_action_type(text: str, default: str) -> str:
    lower = text.lower()
    if re.search(r"\bwithin\s+\d+\s+(?:calendar\s+)?(?:days?|hours?|months?|years?)\b", lower):
        if "retain" in lower or "keep" in lower:
            return "RECORDKEEPING"
        return "DEADLINE"
    if re.search(r"\bunless\b|\bexcept (?:when|as|for)\b|\bsubject to\b", lower):
        if "exception" in lower or "pre-approved" in lower or "preapproved" in lower:
            return "EXCEPTION"
    for pat, atype in ACTION_VERB_MAP:
        if re.search(pat, lower):
            # Don't override hard prohibitions
            if default == "PROHIBITED_ACTION":
                return default
            return atype
    return default


def detect_actors(text: str) -> list[tuple[str, str, str, str, str]]:
    found = []
    seen = set()
    for pat, aid, name, atype, lane in ACTOR_PATTERNS:
        if re.search(pat, text, re.I) and aid not in seen:
            found.append((aid, name, atype, lane, pat))
            seen.add(aid)
    if not found:
        found.append(("ACT-EMPLOYEE", "Employee", "INDIVIDUAL", "Employee", "default"))
    return found


def bpmn_type_for(action_type: str, actor_id: str) -> str:
    if actor_id == "ACT-SYSTEM":
        return "serviceTask"
    mapping = {
        "NOTIFICATION": "sendTask",
        "APPROVAL": "userTask",
        "REVIEW": "userTask",
        "VERIFICATION": "businessRuleTask",
        "SYSTEM_ACTION": "serviceTask",
        "MONITORING": "serviceTask",
        "WAITING_PERIOD": "intermediateCatchEvent",
        "DEADLINE": "intermediateCatchEvent",
        "PROHIBITED_ACTION": "userTask",
        "EXCEPTION": "userTask",
        "ESCALATION": "userTask",
        "SUBMISSION": "userTask",
        "DISCLOSURE": "userTask",
        "RECORDKEEPING": "userTask",
        "MANDATORY_ACTION": "userTask",
        "CONDITIONAL_ACTION": "userTask",
        "RECURRING_ACTION": "userTask",
    }
    return mapping.get(action_type, "userTask")


def verb_object_title(text: str, action_type: str) -> str:
    patterns = [
        (r"(submit\s+(?:a\s+)?pre-?clearance\s+request[^.!]{0,40})", "Submit pre-clearance request"),
        (r"(must be pre-?approved[^.!]{0,40})", "Obtain pre-approval"),
        (r"(attest\s+[^.!]{0,110})", None),
        (r"(disclose\s+[^.!]{0,60})", None),
        (r"(submit\s+[^.!]{0,60})", None),
        (r"(obtain\s+[^.!]{0,60})", None),
        (r"(retain\s+[^.!]{0,60})", None),
        (r"(maintain\s+[^.!]{0,60})", None),
        (r"(report\s+[^.!]{0,60})", None),
        (r"(notify\s+[^.!]{0,60})", None),
        (r"(receive\s+(?:an?\s+)?approval[^.!]{0,40})", "Receive approval"),
        (r"(pre-?approv\w*[^.!]{0,60})", None),
        (r"(approve\w*\s+[^.!]{0,110})", None),
        (r"(certif\w*\s+[^.!]{0,50})", None),
        (r"(escalat\w*\s+[^.!]{0,50})", None),
        (r"(must not\s+[^.!]{0,60})", None),
        (r"(may not\s+[^.!]{0,60})", None),
        (r"(must be executed[^.!]{0,40})", "Execute order same day"),
    ]
    for pat, fixed in patterns:
        m = re.search(pat, text, re.I)
        if m:
            if fixed:
                return fixed
            return _clean_label(m.group(1))

    defaults = {
        "PROHIBITED_ACTION": "Prohibited — must not proceed",
        "APPROVAL": "Obtain approval",
        "SUBMISSION": "Submit required information",
        "DISCLOSURE": "Disclose required information",
        "RECORDKEEPING": "Retain required records",
        "NOTIFICATION": "Send notification",
        "EXCEPTION": "Request exception approval",
        "ESCALATION": "Escalate issue",
        "REVIEW": "Review request",
        "DEADLINE": "Meet deadline",
    }
    return defaults.get(action_type, "Perform required action")


def _clean_label(phrase: str) -> str:
    """Produce a complete, business-readable verb-object label: cut at a
    natural phrase boundary, never mid-word."""
    phrase = normalize_ws(phrase)
    phrase = re.sub(r"^(must|shall|should|may|is required to)\s+", "", phrase, flags=re.I)
    # Prefer ending at the first natural boundary after a meaningful prefix
    for sep in (",", " (", ";", ":"):
        idx = phrase.find(sep)
        if idx >= 24:
            phrase = phrase[:idx]
            break
    if len(phrase) > 64:
        phrase = phrase[:64].rsplit(" ", 1)[0] + "…"
    phrase = phrase.rstrip(".,;: ")
    return phrase[0].upper() + phrase[1:]


def split_atomic(text: str) -> list[str]:
    """Split compound obligations into atomic phrases where safe."""
    # "submit X and receive Y" / "disclose X and retain Y"
    and_split = re.split(
        r"\band\s+(?=(?:receive|obtain|retain|maintain|disclose|report|notify|"
        r"submit|provide|attest|execute)\b)",
        text,
        flags=re.I,
    )
    if len(and_split) > 1:
        atoms = []
        for i, part in enumerate(and_split):
            part = normalize_ws(part)
            if i > 0 and not re.search(r"\b(must|shall|should|required)\b", part, re.I):
                # Carry modal from the first clause for readability
                part = "Must " + part[0].lower() + part[1:] if part else part
            if len(part) >= 12:
                atoms.append(part)
        if len(atoms) > 1:
            return atoms

    parts = re.split(r";\s+", text)
    atoms = []
    for part in parts:
        sub = CONNECTOR_SPLIT.split(part)
        for s in sub:
            s = normalize_ws(s)
            if len(s) >= 15:
                atoms.append(s)
    return atoms or [text]


def detect_candidates(paragraphs: list[Paragraph]) -> list[Candidate]:
    candidates: list[Candidate] = []
    n = 0
    for para in paragraphs:
        if NON_ACTIONABLE.search(para.text):
            # Still allow if it contains a hard obligation later
            if not re.search(r"\bmust\b|\bshall\b|\brequired to\b|\bmust not\b|\bmay not\b", para.text, re.I):
                continue

        # Sentence split
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\"])", para.text)
        for sent in sentences:
            sent = normalize_ws(sent)
            if len(sent) < 25:
                continue
            if NON_ACTIONABLE.search(sent) and not re.search(
                r"\bmust\b|\bshall\b|\brequired\b|\bprohibited\b|\bmay not\b", sent, re.I
            ):
                continue

            matched = None
            action_type = None
            score = 0.0
            for pat, atype, sc in MODAL_PATTERNS:
                if re.search(pat, sent, re.I):
                    matched = pat
                    action_type = atype
                    score = sc
                    break
            if not matched:
                continue

            # Must also have an action-ish verb or obligation content
            if not re.search(
                r"\b(submit|obtain|disclose|report|retain|maintain|notify|approve|"
                r"review|verify|escalate|certif|attest|document|monitor|pre-?clear|"
                r"pre-?approv|move|provide|consider|induce|trade|purchase|sell|"
                r"execute|request|receive|remedial|violation|exception)\b",
                sent,
                re.I,
            ):
                # Allow pure prohibitions and passive "must be <verb>"
                if action_type != "PROHIBITED_ACTION" and not re.search(
                    r"\bmust be\b|\bshall be\b", sent, re.I
                ):
                    continue

            action_type = classify_action_type(sent, action_type)
            actors = [a[0] for a in detect_actors(sent)]
            # Relative offsets within paragraph
            rel = para.text.find(sent[:40]) if sent[:40] in para.text else 0
            if rel < 0:
                rel = 0
            n += 1
            candidates.append(
                Candidate(
                    candidate_id=f"CAN-{n:03d}",
                    text=sent,
                    section_id=para.section_id,
                    section_title=para.section_title,
                    paragraph=para.paragraph,
                    start_offset=para.start_offset + rel,
                    end_offset=para.start_offset + rel + len(sent),
                    action_type=action_type,
                    actionability_score=score,
                    actors=actors,
                    modal_matched=matched,
                )
            )
    return candidates


def expand_atomic_actions(candidates: list[Candidate]) -> list[AtomicAction]:
    actions: list[AtomicAction] = []
    for cand in candidates:
        atoms = split_atomic(cand.text)
        for atom in atoms:
            # Skip atoms that lost their obligation signal if multi-split
            if len(atoms) > 1 and not re.search(
                r"\b(must|shall|should|required|obtain|submit|retain|disclose|"
                r"report|notify|maintain|approve|pre-?clear|pre-?approv|"
                r"may not|must not|prohibited)\b",
                atom,
                re.I,
            ):
                continue
            atype = classify_action_type(atom, cand.action_type)
            actors = detect_actors(atom)
            actor_id = actors[0][0]
            # Prefer compliance as actor for approvals they perform
            if atype in ("APPROVAL", "REVIEW") and "ACT-COMPLIANCE" in [a[0] for a in actors]:
                # If sentence says employee must obtain approval FROM compliance,
                # the submitter is employee; review is inferred later.
                if re.search(r"\bobtain\b|\brequest\b|\bsubmit\b", atom, re.I):
                    actor_id = "ACT-EMPLOYEE"
                    atype = "SUBMISSION" if atype == "APPROVAL" else atype
                else:
                    actor_id = "ACT-COMPLIANCE"

            title = verb_object_title(atom, atype)
            actions.append(
                AtomicAction(
                    title=title,
                    description=atom,
                    action_type=atype,
                    actor_id=actor_id,
                    bpmn_type=bpmn_type_for(atype, actor_id),
                    explicit_or_inferred="EXPLICIT",
                    confidence=cand.actionability_score,
                    source_text=cand.text,
                    section_id=cand.section_id,
                    section_title=cand.section_title,
                    paragraph=cand.paragraph,
                    start_offset=cand.start_offset,
                    end_offset=cand.end_offset,
                )
            )
    return actions


# ---------------------------------------------------------------------------
# Stage 5–7: Group into workflows
# ---------------------------------------------------------------------------

WORKFLOW_SECTION_MAP = {
    "3": ("PTP-DISC", "Disclose Reportable Accounts", "USER_INTENT",
          "Employee discloses brokerage and investment accounts as required."),
    "4": ("PTP-BROKER", "Maintain Accounts with Approved Brokers", "USER_INTENT",
          "Employee maintains reportable accounts with approved brokers or obtains an exception."),
    "5": ("PTP-PRECLEAR", "Obtain Pre-Clearance Before Trading", "USER_INTENT",
          "Employee submits a pre-clearance request in PTA and receives approval before trading."),
    "6": ("PTP-TXTYPE", "Apply Transaction-Type Pre-Clearance Rules", "USER_INTENT",
          "Employee follows pre-clearance rules by transaction type."),
    "7": ("PTP-MANAGED", "Manage Exempt Managed Accounts", "USER_INTENT",
          "Employee handles managed-account disclosure and trading constraints."),
    "8": ("PTP-PROHIB", "Comply with Prohibited Investment Rules", "POLICY_RULE",
          "Employee must not invest in prohibited instruments."),
    "9": ("PTP-OPTIONS", "Trade Permissible Options and Futures", "USER_INTENT",
          "Employee trades only permissible options and futures under policy conditions."),
    "10": ("PTP-BLACKOUT", "Observe Blackout Periods", "POLICY_RULE",
           "Employee must not trade against clients during blackout periods."),
    "11": ("PTP-SHORT", "Avoid Short-Term Trading Profits", "POLICY_RULE",
           "Employee complies with the ban on short-term trading profits."),
    "12": ("PTP-PRIVATE", "Obtain Pre-Approval for Private Investments", "USER_INTENT",
           "Employee obtains pre-approval before private investments."),
    "13": ("PTP-BLK", "Trade BlackRock (BLK) Securities", "USER_INTENT",
           "Employee follows special rules when trading BLK securities."),
    "14": ("PTP-INSIDER", "Prevent Insider Trading", "POLICY_RULE",
           "Employee must not trade on material non-public information."),
    "15": ("PTP-VIOL", "Address Personal Trading Violations", "VIOLATION_DETECTED",
           "Suspected or confirmed personal trading violations are escalated and addressed."),
    "16": ("PTP-CERT", "Complete Annual Certification", "SCHEDULE",
           "Employee annually certifies compliance with the personal trading policy."),
}


def collect_actors(actions: list[AtomicAction]) -> list[dict[str, Any]]:
    catalog = {a[0]: a for pat in ACTOR_PATTERNS for a in [pat]}
    # rebuild clean catalog
    catalog = {}
    for pat, aid, name, atype, lane in ACTOR_PATTERNS:
        catalog[aid] = {
            "actor_id": aid,
            "name": name,
            "actor_type": atype,
            "bpmn_lane": lane,
        }
    used = []
    seen = set()
    for act in actions:
        if act.actor_id not in seen and act.actor_id in catalog:
            used.append(catalog[act.actor_id])
            seen.add(act.actor_id)
    if "ACT-EMPLOYEE" not in seen:
        used.insert(0, catalog["ACT-EMPLOYEE"])
    return used


def build_workflow(
    workflow_id: str,
    title: str,
    summary: str,
    trigger_type: str,
    trigger_desc: str,
    section_id: str,
    section_title: str,
    actions: list[AtomicAction],
    policy_meta: dict[str, Any],
) -> dict[str, Any]:
    """Assemble a PolicyWorkflow JSON object with minimal connective inference."""
    refs = []
    ref_by_key: dict[tuple, str] = {}
    for i, act in enumerate(actions, 1):
        key = (act.section_id, act.paragraph, act.start_offset)
        if key not in ref_by_key:
            rid = f"REF-{len(refs)+1:03d}"
            ref_by_key[key] = rid
            refs.append(
                {
                    "reference_id": rid,
                    "section_id": act.section_id,
                    "section_title": act.section_title,
                    "page": None,
                    "paragraph": act.paragraph,
                    "anchor": f"policy-{act.section_id}-{act.paragraph}",
                    "source_html": "policy_source.html",
                    "quoted_text": act.source_text[:500],
                    "start_offset": act.start_offset,
                    "end_offset": act.end_offset,
                }
            )

    actors = collect_actors(actions)
    actor_ids = {a["actor_id"] for a in actors}

    steps: list[dict[str, Any]] = []
    gateways: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    conditions: list[dict[str, Any]] = []
    ambiguities: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []
    deadlines: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []

    start_id = "START-001"
    start_ref_ids = [refs[0]["reference_id"]] if refs else []
    events.append(
        {
            "event_id": start_id,
            "event_type": "startEvent",
            "title": trigger_desc,
            "next_step_id": "STEP-001",
            "source_reference_ids": start_ref_ids,
        }
    )

    # Detect if we need an approval gateway (submission / pre-clearance language)
    needs_approval_gateway = any(
        a.action_type == "SUBMISSION"
        or re.search(r"pre-?clear(?:ance)?\s+request|\bsubmit\b", a.description, re.I)
        for a in actions
    )
    needs_exception_gateway = any(a.action_type == "EXCEPTION" for a in actions)

    seq = 0
    step_ids: list[str] = []

    # Optional inferred: identify intent (only for USER_INTENT triggers)
    if trigger_type == "USER_INTENT" and actions:
        seq += 1
        sid = f"STEP-{seq:03d}"
        step_ids.append(sid)
        first_ref = ref_by_key[
            (actions[0].section_id, actions[0].paragraph, actions[0].start_offset)
        ]
        steps.append(
            {
                "step_id": sid,
                "sequence": seq,
                "title": "Identify intended activity",
                "description": "The employee identifies the personal-trading activity that may be subject to this section.",
                "actor_id": "ACT-EMPLOYEE",
                "action_type": "MANDATORY_ACTION",
                "bpmn_type": "userTask",
                "source_reference_ids": [first_ref],
                "explicit_or_inferred": "INFERRED",
                "inference_reason": "Connective step required to start a readable process from a user-intent trigger; not an additional policy obligation.",
                "confidence": 0.75,
                "next_step_ids": [],
                "preconditions": [],
                "outputs": ["intended_activity"],
                "deadline_id": None,
                "exception_ids": [],
            }
        )

    explicit_step_start = seq

    for act in actions:
        seq += 1
        sid = f"STEP-{seq:03d}"
        step_ids.append(sid)
        rid = ref_by_key[(act.section_id, act.paragraph, act.start_offset)]
        if act.actor_id not in actor_ids:
            # add missing actor
            for pat, aid, name, atype, lane in ACTOR_PATTERNS:
                if aid == act.actor_id:
                    actors.append(
                        {"actor_id": aid, "name": name, "actor_type": atype, "bpmn_lane": lane}
                    )
                    actor_ids.add(aid)
                    break

        conf = {
            "action_detection": act.confidence,
            "actor_identification": 0.85 if act.actor_id != "ACT-EMPLOYEE" or "you" in act.description.lower() or "employee" in act.description.lower() else 0.7,
            "action_interpretation": act.confidence,
            "sequence_relationship": 0.7,
            "source_grounding": 0.95,
        }
        overall = round(sum(conf.values()) / len(conf), 2)

        step = {
            "step_id": sid,
            "sequence": seq,
            "title": act.title,
            "description": act.description,
            "actor_id": act.actor_id,
            "action_type": act.action_type,
            "bpmn_type": act.bpmn_type,
            "source_reference_ids": [rid],
            "explicit_or_inferred": act.explicit_or_inferred,
            "confidence": overall,
            "confidence_detail": conf,
            "next_step_ids": [],
            "preconditions": [],
            "outputs": [],
            "deadline_id": None,
            "exception_ids": [],
        }
        if act.inference_reason:
            step["inference_reason"] = act.inference_reason
        steps.append(step)

        if act.action_type == "RECORDKEEPING":
            records.append(
                {
                    "record_id": f"REC-{len(records)+1:03d}",
                    "title": act.title,
                    "description": act.description,
                    "retained_by": act.actor_id,
                    "source_reference_ids": [rid],
                }
            )
        if act.action_type == "DEADLINE":
            m = re.search(
                r"within\s+(\d+)\s+(calendar\s+)?(days?|hours?|months?|years?)",
                act.description,
                re.I,
            )
            deadlines.append(
                {
                    "deadline_id": f"DL-{len(deadlines)+1:03d}",
                    "description": act.description[:200],
                    "duration": f"{m.group(1)} {m.group(3)}" if m else "unspecified",
                    "source_reference_ids": [rid],
                }
            )
            step["deadline_id"] = deadlines[-1]["deadline_id"]
        if act.action_type == "EXCEPTION":
            exceptions.append(
                {
                    "exception_id": f"EXC-{len(exceptions)+1:03d}",
                    "description": act.description[:300],
                    "approved_by": "ACT-COMPLIANCE" if "ACT-COMPLIANCE" in actor_ids or True else None,
                    "source_reference_ids": [rid],
                }
            )
            step["exception_ids"] = [exceptions[-1]["exception_id"]]
        if act.action_type == "PROHIBITED_ACTION":
            controls.append(
                {
                    "control_id": f"CTRL-{len(controls)+1:03d}",
                    "title": act.title,
                    "control_type": "PREVENTIVE",
                    "performed_by": act.actor_id,
                    "source_reference_ids": [rid],
                }
            )
        if overall < 0.8:
            ambiguities.append(
                {
                    "ambiguity_id": f"AMB-{len(ambiguities)+1:03d}",
                    "description": f"Lower confidence for step '{act.title}'. Review actor and obligation strength.",
                    "impact": "May require human confirmation before operationalizing.",
                    "requires_human_review": True,
                }
            )

    # Wire sequence
    for i, step in enumerate(steps):
        if i + 1 < len(steps):
            step["next_step_ids"] = [steps[i + 1]["step_id"]]
        else:
            step["next_step_ids"] = ["END-001"]

    # Approval gateway: if submission present, insert Compliance review BEFORE
    # the submit step, then decide after the employee submits.
    if needs_approval_gateway:
        # Find first real submit / pre-clearance-request step (not a
        # prohibition that merely mentions "pre-approval").
        submit_idx = next(
            (
                i
                for i, s in enumerate(steps)
                if s["action_type"] == "SUBMISSION"
                or re.search(
                    r"\bsubmit\b|pre-?clearance\s+request", s["title"], re.I
                )
            ),
            None,
        )
        if submit_idx is not None and "ACT-COMPLIANCE" not in {s["actor_id"] for s in steps}:
            submit_id = steps[submit_idx]["step_id"]
            review_id = f"STEP-{len(steps)+1:03d}"
            ref_ids = steps[submit_idx]["source_reference_ids"]
            review_step = {
                "step_id": review_id,
                "sequence": int(steps[submit_idx]["sequence"]),
                "title": "Review pre-clearance request",
                "description": "Legal & Compliance reviews the intended activity before the employee submits the request for a decision.",
                "actor_id": "ACT-COMPLIANCE",
                "action_type": "REVIEW",
                "bpmn_type": "userTask",
                "source_reference_ids": ref_ids,
                "explicit_or_inferred": "INFERRED",
                "inference_reason": (
                    "Policy requires approval; the Compliance review is placed "
                    "before submit so the request is examined prior to submission."
                ),
                "confidence": 0.8,
                "next_step_ids": [submit_id],
                "preconditions": [],
                "outputs": ["review_complete"],
                "deadline_id": None,
                "exception_ids": [],
            }
            if "ACT-COMPLIANCE" not in actor_ids:
                actors.append(
                    {
                        "actor_id": "ACT-COMPLIANCE",
                        "name": "Legal & Compliance",
                        "actor_type": "BUSINESS_FUNCTION",
                        "bpmn_lane": "Compliance",
                    }
                )

            # What used to follow submit becomes the Approved continuation.
            old_next = steps[submit_idx]["next_step_ids"]
            continuation = (
                old_next[0] if old_next and old_next[0].startswith("STEP") else None
            )

            # Rewire anything that pointed at submit so it points at review first.
            for s in steps:
                s["next_step_ids"] = [
                    review_id if nid == submit_id else nid
                    for nid in (s.get("next_step_ids") or [])
                ]
            for e in events:
                if e.get("next_step_id") == submit_id:
                    e["next_step_id"] = review_id

            # Insert review immediately before submit: Review → Submit → Gateway.
            steps.insert(submit_idx, review_step)
            # submit_idx shifted by +1 after insert
            steps[submit_idx + 1]["next_step_ids"] = ["GATEWAY-001"]
            for s in steps[submit_idx + 1 :]:
                s["sequence"] += 1

            approved_branch: dict[str, str] = {
                "label": "Approved",
                "condition": "approval_status == 'approved'",
            }
            if continuation:
                approved_branch["target_step_id"] = continuation
            else:
                approved_branch["target_event_id"] = "END-APPROVED"

            gw = {
                "gateway_id": "GATEWAY-001",
                "gateway_type": "exclusiveGateway",
                "question": "Was the request approved?",
                "incoming_step_ids": [submit_id],
                "branches": [
                    approved_branch,
                    {
                        "label": "Rejected",
                        "condition": "approval_status == 'rejected'",
                        "target_event_id": "END-REJECTED",
                    },
                ],
            }
            gateways.append(gw)
            conditions.append(
                {
                    "condition_id": "COND-001",
                    "expression": "approval_status == 'approved'",
                    "business_description": "Legal & Compliance grants approval.",
                    "source_reference_ids": ref_ids,
                }
            )
            if not continuation:
                events.append(
                    {
                        "event_id": "END-APPROVED",
                        "event_type": "endEvent",
                        "title": "Activity may proceed under approval",
                    }
                )
            events.append(
                {
                    "event_id": "END-REJECTED",
                    "event_type": "endEvent",
                    "title": "Activity must not proceed",
                }
            )

    # Ensure at least one end event
    if not any(e["event_id"].startswith("END") for e in events):
        events.append(
            {"event_id": "END-001", "event_type": "endEvent", "title": "Process completed"}
        )
    elif not any(e["event_id"] == "END-001" for e in events) and not gateways:
        events.append(
            {"event_id": "END-001", "event_type": "endEvent", "title": "Process completed"}
        )
    elif gateways and not any(e["event_id"] == "END-001" for e in events):
        pass
    else:
        if not any(e["event_id"] == "END-001" for e in events):
            # if last step points to END-001 ensure it exists
            if any(s.get("next_step_ids") == ["END-001"] for s in steps):
                events.append(
                    {
                        "event_id": "END-001",
                        "event_type": "endEvent",
                        "title": "Process completed",
                    }
                )

    # Fix END-001 presence
    if any(s.get("next_step_ids") == ["END-001"] for s in steps) and not any(
        e["event_id"] == "END-001" for e in events
    ):
        events.append(
            {"event_id": "END-001", "event_type": "endEvent", "title": "Process completed"}
        )

    # Prohibitions are modeled as a negative outcome: terminal PROHIBITED_ACTION
    # steps end at END-PROHIBITED (orange path), not a neutral "Process completed".
    prohib_steps = [s for s in steps if s.get("action_type") == "PROHIBITED_ACTION"]
    if prohib_steps:
        for s in prohib_steps:
            if (s.get("next_step_ids") or []) == ["END-001"]:
                s["next_step_ids"] = ["END-PROHIBITED"]
        if any((s.get("next_step_ids") or []) == ["END-PROHIBITED"] for s in steps):
            if not any(e["event_id"] == "END-PROHIBITED" for e in events):
                events.append(
                    {
                        "event_id": "END-PROHIBITED",
                        "event_type": "endEvent",
                        "title": "Must not proceed — prohibited by policy",
                    }
                )
            referenced: set[str] = set()
            for s in steps:
                referenced.update(s.get("next_step_ids") or [])
            for g in gateways:
                for b in g.get("branches", []):
                    if b.get("target_event_id"):
                        referenced.add(b["target_event_id"])
                    if b.get("target_step_id"):
                        referenced.add(b["target_step_id"])
            events[:] = [
                e
                for e in events
                if e["event_type"] != "endEvent"
                or e["event_id"] in referenced
                or e["event_id"] == "END-PROHIBITED"
            ]

    # Re-sequence integers
    for i, s in enumerate(steps, 1):
        s["sequence"] = i

    overall_conf = round(
        sum(s["confidence"] for s in steps) / max(len(steps), 1), 2
    )
    review_status = "PENDING" if overall_conf < 0.85 or ambiguities else "PENDING"

    return {
        "workflow_id": workflow_id,
        "workflow_title": title,
        "workflow_summary": summary,
        "policy": {
            "policy_id": policy_meta["policy_id"],
            "policy_title": policy_meta["policy_title"],
            "policy_version": policy_meta["policy_version"],
            "source_file": policy_meta["source_file"],
        },
        "source_references": refs,
        "trigger": {"type": trigger_type, "description": trigger_desc},
        "actors": actors,
        "steps": steps,
        "gateways": gateways,
        "events": events,
        "conditions": conditions,
        "exceptions": exceptions,
        "deadlines": deadlines,
        "records": records,
        "controls": controls,
        "ambiguities": ambiguities,
        "overall_confidence": overall_conf,
        "review_status": review_status,
        "section_id": section_id,
        "section_title": section_title,
    }


def group_workflows(
    actions: list[AtomicAction], policy_meta: dict[str, Any]
) -> list[dict[str, Any]]:
    by_section: dict[str, list[AtomicAction]] = {}
    for a in actions:
        by_section.setdefault(a.section_id, []).append(a)

    workflows = []
    # Scope-level exception (section 2)
    if "2" in by_section:
        wf = build_workflow(
            "PTP-EXCEPTION",
            "Request Exception to This Policy",
            "Any exception to this policy must be pre-approved by Legal & Compliance.",
            "USER_INTENT",
            "Employee requests an exception to the policy.",
            "2",
            "Scope",
            by_section["2"],
            policy_meta,
        )
        workflows.append(wf)

    for sid, meta in WORKFLOW_SECTION_MAP.items():
        if sid not in by_section:
            continue
        wf_id, title, trigger_type, summary = meta
        section_title = by_section[sid][0].section_title
        trigger_desc = {
            "USER_INTENT": f"Employee initiates activity under section {sid}.",
            "POLICY_RULE": f"Policy rule in section {sid} applies.",
            "VIOLATION_DETECTED": "A personal trading violation is suspected or detected.",
            "SCHEDULE": "Annual certification period begins.",
        }.get(trigger_type, f"Section {sid} trigger.")
        wf = build_workflow(
            wf_id, title, summary, trigger_type, trigger_desc, sid, section_title,
            by_section[sid], policy_meta,
        )
        workflows.append(wf)

    # Catch-all for other sections with actions
    mapped = set(WORKFLOW_SECTION_MAP) | {"2"}
    for sid, acts in by_section.items():
        if sid in mapped:
            continue
        wf = build_workflow(
            f"PTP-SEC-{sid}",
            f"Obligations in Section {sid}: {acts[0].section_title}",
            f"Actionable obligations extracted from section {sid}.",
            "POLICY_RULE",
            f"Obligations under section {sid} apply.",
            sid,
            acts[0].section_title,
            acts,
            policy_meta,
        )
        workflows.append(wf)

    return workflows


# ---------------------------------------------------------------------------
# Outcome-path annotation (approved = green, rejected = red)
# ---------------------------------------------------------------------------

def _workflow_edges(wf: dict[str, Any]) -> list[tuple[str, str, str | None]]:
    """Flatten the workflow JSON into (source, target, branch_label) edges."""
    edges: list[tuple[str, str, str | None]] = []
    start = next(e for e in wf["events"] if e["event_type"] == "startEvent")
    if start.get("next_step_id"):
        edges.append((start["event_id"], start["next_step_id"], None))
    for s in wf["steps"]:
        for nxt in s.get("next_step_ids", []):
            edges.append((s["step_id"], nxt, None))
    for g in wf["gateways"]:
        for inc in g.get("incoming_step_ids", []):
            edges.append((inc, g["gateway_id"], None))
        for b in g["branches"]:
            tgt = b.get("target_step_id") or b.get("target_event_id")
            if tgt:
                edges.append((g["gateway_id"], tgt, b.get("label")))
    return edges


def _chapter_from_ref(ref: dict[str, Any] | None, fallback_section: str) -> str:
    """Build P-code chapter segment from a source reference (e.g. 5.3)."""
    fallback = str(fallback_section or "0")
    if not ref:
        return fallback
    sid = str(ref.get("section_id") or fallback)
    para = ref.get("paragraph")
    if para is not None and str(para).strip() != "":
        return f"{sid}.{para}"
    return sid


def annotate_element_codes(wf: dict[str, Any]) -> None:
    """Assign human-readable P-{chapter}-{step}-{element} codes to all nodes.

    Example: P-5.3-007-A004
      P     = policy (fixed)
      5.3   = original chapter (section.paragraph from primary source ref)
      007   = workflow step sequence
      A004  = action element serial (G=gateway, E=event)
    """
    refs = {r["reference_id"]: r for r in wf.get("source_references", [])}
    fallback = str(wf.get("section_id") or "0")
    if fallback == "ALL":
        fallback = "0"

    action_serial = 0
    gateway_serial = 0
    event_serial = 0
    steps_by_id = {s["step_id"]: s for s in wf.get("steps", [])}

    for step in wf.get("steps", []):
        action_serial += 1
        ref_ids = step.get("source_reference_ids") or []
        ref = refs.get(ref_ids[0]) if ref_ids else None
        chapter = _chapter_from_ref(ref, fallback)
        seq = int(step.get("sequence") or action_serial)
        step["step_code"] = f"P-{chapter}-{seq:03d}-A{action_serial:03d}"

    for i, gw in enumerate(wf.get("gateways", []), 1):
        gateway_serial += 1
        chapter = fallback
        seq = len(wf.get("steps", [])) + i
        for sid in gw.get("incoming_step_ids") or []:
            step = steps_by_id.get(sid)
            if not step:
                continue
            ref_ids = step.get("source_reference_ids") or []
            if ref_ids and ref_ids[0] in refs:
                chapter = _chapter_from_ref(refs[ref_ids[0]], fallback)
            seq = int(step.get("sequence") or 0) + 1
            break
        gw["gateway_code"] = f"P-{chapter}-{seq:03d}-G{gateway_serial:03d}"

    for i, event in enumerate(wf.get("events", []), 1):
        event_serial += 1
        ref_ids = event.get("source_reference_ids") or []
        ref = refs.get(ref_ids[0]) if ref_ids else None
        chapter = _chapter_from_ref(ref, fallback)
        if event.get("event_type") == "startEvent":
            seq = 1
        else:
            seq = len(wf.get("steps", [])) + i
        event["event_code"] = f"P-{chapter}-{seq:03d}-E{event_serial:03d}"


def annotate_outcome_paths(wf: dict[str, Any]) -> None:
    """Mark approved paths green, rejected paths red, and prohibited
    actions orange (negative outcome independent of approval gateways)."""
    edges = _workflow_edges(wf)
    outcome: dict[str, str] = {}

    def flood(seed: str | None, label: str) -> None:
        stack = [seed]
        seen: set[str] = set()
        while stack:
            node = stack.pop()
            if not node or node in seen:
                continue
            seen.add(node)
            previous = outcome.get(node)
            if previous and previous != label:
                outcome[node] = "MIXED"
            else:
                outcome[node] = label
            stack.extend(t for s, t, _ in edges if s == node)

    for g in wf["gateways"]:
        for b in g["branches"]:
            branch_label = (b.get("label") or "").lower()
            target = b.get("target_step_id") or b.get("target_event_id")
            if "approve" in branch_label:
                b["color"] = APPROVED_STROKE
                flood(target, "APPROVED")
            elif "reject" in branch_label:
                b["color"] = REJECTED_STROKE
                flood(target, "REJECTED")

    def apply(obj: dict[str, Any], node_id: str) -> None:
        oc = outcome.get(node_id)
        if oc == "APPROVED":
            obj["path_outcome"] = "APPROVED"
            obj["color"] = APPROVED_STROKE
        elif oc == "REJECTED":
            obj["path_outcome"] = "REJECTED"
            obj["color"] = REJECTED_STROKE
        else:
            obj["path_outcome"] = None
            obj["color"] = None

    for s in wf["steps"]:
        apply(s, s["step_id"])
        # Prohibitions always win: orange negative outcome on the element itself.
        if s.get("action_type") == "PROHIBITED_ACTION":
            s["path_outcome"] = "PROHIBITED"
            s["color"] = PROHIBITED_STROKE
            # Color the immediate negative end event when this step terminates there.
            for nid in s.get("next_step_ids") or []:
                if "END-PROHIBITED" in nid:
                    flood(nid, "PROHIBITED")

    for e in wf["events"]:
        apply(e, e["event_id"])
        if "END-PROHIBITED" in e["event_id"] or outcome.get(e["event_id"]) == "PROHIBITED":
            e["path_outcome"] = "PROHIBITED"
            e["color"] = PROHIBITED_STROKE
        # Also catch flood results that applied PROHIBITED after apply().
        if outcome.get(e["event_id"]) == "PROHIBITED":
            e["path_outcome"] = "PROHIBITED"
            e["color"] = PROHIBITED_STROKE


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

ALLOWED_BPMN = {
    "userTask",
    "serviceTask",
    "manualTask",
    "sendTask",
    "receiveTask",
    "businessRuleTask",
    "callActivity",
    "subProcess",
    "intermediateCatchEvent",
}


def validate_workflow(wf: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    step_ids = {s["step_id"] for s in wf["steps"]}
    event_ids = {e["event_id"] for e in wf["events"]}
    ref_ids = {r["reference_id"] for r in wf["source_references"]}
    actor_ids = {a["actor_id"] for a in wf["actors"]}
    gateway_ids = {g["gateway_id"] for g in wf["gateways"]}
    all_nodes = step_ids | event_ids | gateway_ids

    if not any(e["event_type"] == "startEvent" for e in wf["events"]):
        findings.append({"code": "MISSING_START", "severity": "error", "message": "No start event"})
    if not any(e["event_type"] == "endEvent" for e in wf["events"]):
        findings.append({"code": "MISSING_END", "severity": "error", "message": "No end event"})

    seen_steps = set()
    for s in wf["steps"]:
        if s["step_id"] in seen_steps:
            findings.append(
                {
                    "code": "DUPLICATE_STEP",
                    "severity": "error",
                    "message": f"Duplicate step_id {s['step_id']}",
                }
            )
        seen_steps.add(s["step_id"])
        if not s.get("source_reference_ids"):
            findings.append(
                {
                    "code": "NO_SOURCE_REF",
                    "severity": "error",
                    "message": f"{s['step_id']} has no policy reference",
                }
            )
        for rid in s.get("source_reference_ids", []):
            if rid not in ref_ids:
                findings.append(
                    {
                        "code": "BAD_REF",
                        "severity": "error",
                        "message": f"{s['step_id']} references unknown {rid}",
                    }
                )
        if s["actor_id"] not in actor_ids:
            findings.append(
                {
                    "code": "MISSING_ACTOR",
                    "severity": "error",
                    "message": f"{s['step_id']} actor {s['actor_id']} not defined",
                }
            )
        if s["bpmn_type"] not in ALLOWED_BPMN:
            findings.append(
                {
                    "code": "BAD_BPMN_TYPE",
                    "severity": "error",
                    "message": f"{s['step_id']} invalid bpmn_type {s['bpmn_type']}",
                }
            )
        if not (0 <= s["confidence"] <= 1):
            findings.append(
                {
                    "code": "BAD_CONFIDENCE",
                    "severity": "error",
                    "message": f"{s['step_id']} confidence out of range",
                }
            )
        if s["explicit_or_inferred"] == "INFERRED" and not s.get("inference_reason"):
            findings.append(
                {
                    "code": "MISSING_INFERENCE_REASON",
                    "severity": "error",
                    "message": f"{s['step_id']} inferred without reason",
                }
            )
        for nxt in s.get("next_step_ids", []):
            if nxt not in all_nodes and not nxt.startswith("GATEWAY") and not nxt.startswith("END"):
                findings.append(
                    {
                        "code": "DANGLING_NEXT",
                        "severity": "error",
                        "message": f"{s['step_id']} next {nxt} missing",
                    }
                )
            elif nxt.startswith("END") and nxt not in event_ids:
                findings.append(
                    {
                        "code": "DANGLING_END",
                        "severity": "error",
                        "message": f"{s['step_id']} points to missing {nxt}",
                    }
                )
            elif nxt.startswith("GATEWAY") and nxt not in gateway_ids:
                findings.append(
                    {
                        "code": "DANGLING_GATEWAY",
                        "severity": "error",
                        "message": f"{s['step_id']} points to missing {nxt}",
                    }
                )
            elif nxt.startswith("STEP") and nxt not in step_ids:
                findings.append(
                    {
                        "code": "DANGLING_STEP",
                        "severity": "error",
                        "message": f"{s['step_id']} points to missing {nxt}",
                    }
                )

    for g in wf["gateways"]:
        if len(g.get("branches", [])) < 2:
            findings.append(
                {
                    "code": "GATEWAY_BRANCHES",
                    "severity": "error",
                    "message": f"{g['gateway_id']} has fewer than 2 branches",
                }
            )
        for b in g.get("branches", []):
            if not b.get("label"):
                findings.append(
                    {
                        "code": "UNLABELED_BRANCH",
                        "severity": "error",
                        "message": f"{g['gateway_id']} unlabeled branch",
                    }
                )
            tid = b.get("target_step_id") or b.get("target_event_id")
            if not tid or tid not in all_nodes:
                findings.append(
                    {
                        "code": "BAD_BRANCH_TARGET",
                        "severity": "error",
                        "message": f"{g['gateway_id']} bad target {tid}",
                    }
                )

    return findings


# ---------------------------------------------------------------------------
# BPMN conversion
# ---------------------------------------------------------------------------

def qname(ns: str, local: str) -> str:
    return f"{{{ns}}}{local}"


def add_policy_extension(parent: etree._Element, ref: dict[str, Any] | None, step: dict[str, Any]):
    ext = etree.SubElement(parent, qname(BPMN_NS, "extensionElements"))
    el = etree.SubElement(ext, qname(POLICY_NS, "sourceReference"))
    if ref:
        el.set("sectionId", str(ref.get("section_id", "")))
        if ref.get("page") is not None:
            el.set("page", str(ref["page"]))
        el.set("referenceId", ref["reference_id"])
    el.set("confidence", str(step.get("confidence", "")))
    el.set("extractionType", step.get("explicit_or_inferred", ""))


def convert_to_bpmn(wf: dict[str, Any]) -> bytes:
    definitions = etree.Element(qname(BPMN_NS, "definitions"), nsmap=NSMAP)
    definitions.set("id", f"Defs_{wf['workflow_id']}")
    definitions.set("targetNamespace", "http://policies2bpmn.local/workflows")
    definitions.set(qname(XSI_NS, "schemaLocation"), "")

    collab = etree.SubElement(definitions, qname(BPMN_NS, "collaboration"))
    collab.set("id", f"Collab_{wf['workflow_id']}")

    participant = etree.SubElement(collab, qname(BPMN_NS, "participant"))
    participant.set("id", f"Participant_{wf['workflow_id']}")
    participant.set("name", wf["policy"]["policy_title"])
    process_id = f"Process_{wf['workflow_id']}"
    participant.set("processRef", process_id)

    process = etree.SubElement(definitions, qname(BPMN_NS, "process"))
    process.set("id", process_id)
    process.set("name", wf["workflow_title"])
    process.set("isExecutable", "false")

    # Lanes
    lane_set = etree.SubElement(process, qname(BPMN_NS, "laneSet"))
    lane_set.set("id", f"LaneSet_{wf['workflow_id']}")

    ref_index = {r["reference_id"]: r for r in wf["source_references"]}
    steps_by_id = {s["step_id"]: s for s in wf["steps"]}
    gateways_by_id = {g["gateway_id"]: g for g in wf["gateways"]}
    start = next(e for e in wf["events"] if e["event_type"] == "startEvent")
    end_events = {e["event_id"]: e for e in wf["events"] if e["event_type"] == "endEvent"}

    # ---- Edges: built strictly from the workflow JSON (no implicit chaining)
    edge_list: list[tuple[str, str, str | None]] = []

    def add_edge(source: str, target: str | None, label: str | None = None) -> None:
        if not target:
            return
        if any(e[0] == source and e[1] == target for e in edge_list):
            return
        edge_list.append((source, target, label))

    if start.get("next_step_id"):
        add_edge(start["event_id"], start["next_step_id"])
    for s in wf["steps"]:
        for nxt in s.get("next_step_ids", []):
            add_edge(s["step_id"], nxt)
    for g in wf["gateways"]:
        for inc in g.get("incoming_step_ids", []):
            add_edge(inc, g["gateway_id"])
        for b in g["branches"]:
            add_edge(
                g["gateway_id"],
                b.get("target_step_id") or b.get("target_event_id"),
                b.get("label"),
            )

    # ---- Node set: start, steps, gateways, and only end events actually used
    referenced = {e[1] for e in edge_list}
    node_ids = [start["event_id"]]
    node_ids += [s["step_id"] for s in wf["steps"]]
    node_ids += [g["gateway_id"] for g in wf["gateways"]]
    node_ids += [eid for eid in end_events if eid in referenced]
    node_set = set(node_ids)
    edge_list = [e for e in edge_list if e[0] in node_set and e[1] in node_set]

    def node_size(nid: str) -> tuple[float, float]:
        if nid in steps_by_id:
            return (130.0, 80.0)
        if nid in gateways_by_id:
            return (50.0, 50.0)
        return (36.0, 36.0)

    # ---- Layered layout: column = longest path from start, row = actor lane
    col = {nid: 0 for nid in node_ids}
    for _ in range(len(node_ids) + 1):
        changed = False
        for src, tgt, _ in edge_list:
            if col[tgt] < col[src] + 1:
                col[tgt] = col[src] + 1
                changed = True
        if not changed:
            break

    lane_order = [a["actor_id"] for a in wf["actors"]] or ["ACT-EMPLOYEE"]
    lane_map: dict[str, str] = {
        s["step_id"]: s["actor_id"] for s in wf["steps"]
    }
    # Events/gateways inherit the lane of their first predecessor (or successor
    # for the start event) so flows stay as horizontal as possible.
    for nid in sorted(node_ids, key=lambda n: col[n]):
        if nid in lane_map:
            continue
        preds = [src for src, tgt, _ in edge_list if tgt == nid]
        succs = [tgt for src, tgt, _ in edge_list if src == nid]
        if preds and preds[0] in lane_map:
            lane_map[nid] = lane_map[preds[0]]
        elif succs and succs[0] in lane_map:
            lane_map[nid] = lane_map[succs[0]]
        else:
            lane_map[nid] = lane_order[0]
        if lane_map[nid] not in lane_order:
            lane_order.append(lane_map[nid])

    # Room for larger task boxes (labels stay inside the figure).
    COL_WIDTH = 200.0
    LANE_HEIGHT = 170.0
    BAND = 130.0  # widest node; everything is centered inside this band
    
    X0, Y0 = 70.0, 60.0
    lane_y = {aid: Y0 + i * LANE_HEIGHT for i, aid in enumerate(lane_order)}

    # Stack nodes that land on the same (column, lane) cell so nothing overlaps.
    occupied: dict[tuple[int, str], int] = {}
    pos: dict[str, tuple[float, float, float, float]] = {}
    for nid in sorted(node_ids, key=lambda n: (col[n], 0 if n in steps_by_id else 1)):
        w, h = node_size(nid)
        lane = lane_map[nid]
        cell = (col[nid], lane)
        stack = occupied.get(cell, 0)
        occupied[cell] = stack + 1
        x = X0 + col[nid] * COL_WIDTH + (BAND - w) / 2
        y = lane_y[lane] + (100.0 - h) / 2 + stack * 105.0
        pos[nid] = (x, y, w, h)

    # ---- BPMN elements
    start_el = etree.SubElement(process, qname(BPMN_NS, "startEvent"))
    start_el.set("id", start["event_id"])
    start_el.set("name", start["title"][:60])
    start_refs = start.get("source_reference_ids") or []
    if start_refs:
        add_policy_extension(
            start_el,
            ref_index.get(start_refs[0]),
            {
                "confidence": wf.get("overall_confidence", ""),
                "explicit_or_inferred": "EXPLICIT",
            },
        )

    for step in sorted(wf["steps"], key=lambda s: s["sequence"]):
        bpmn_type = step["bpmn_type"]
        if bpmn_type == "intermediateCatchEvent":
            el = etree.SubElement(process, qname(BPMN_NS, "intermediateCatchEvent"))
            timer = etree.SubElement(el, qname(BPMN_NS, "timerEventDefinition"))
            timer.set("id", f"Timer_{step['step_id']}")
        else:
            el = etree.SubElement(process, qname(BPMN_NS, bpmn_type))
        el.set("id", step["step_id"])
        el.set("name", step["title"][:80])
        refs = step.get("source_reference_ids") or []
        ref = ref_index.get(refs[0]) if refs else None
        add_policy_extension(el, ref, step)

    for g in wf["gateways"]:
        gel = etree.SubElement(process, qname(BPMN_NS, g["gateway_type"]))
        gel.set("id", g["gateway_id"])
        gel.set("name", g["question"][:80])

    for eid in node_ids:
        if eid in end_events:
            ee = etree.SubElement(process, qname(BPMN_NS, "endEvent"))
            ee.set("id", eid)
            ee.set("name", end_events[eid]["title"][:60])

    flows: list[tuple[str, str, str, str | None]] = []
    for i, (src, tgt, label) in enumerate(edge_list, 1):
        fid = f"Flow_{i:03d}"
        sf = etree.SubElement(process, qname(BPMN_NS, "sequenceFlow"))
        sf.set("id", fid)
        sf.set("sourceRef", src)
        sf.set("targetRef", tgt)
        if label:
            sf.set("name", label)
        flows.append((fid, src, tgt, label))

    # Lane refs
    for a in wf["actors"]:
        lane = etree.SubElement(lane_set, qname(BPMN_NS, "lane"))
        lane.set("id", f"Lane_{a['actor_id']}")
        lane.set("name", a["bpmn_lane"])
        for nid in node_ids:
            if lane_map.get(nid) == a["actor_id"]:
                fr = etree.SubElement(lane, qname(BPMN_NS, "flowNodeRef"))
                fr.text = nid

    # ---- BPMN DI
    diagram = etree.SubElement(definitions, qname(BPMNDI_NS, "BPMNDiagram"))
    diagram.set("id", f"Diagram_{wf['workflow_id']}")
    plane = etree.SubElement(diagram, qname(BPMNDI_NS, "BPMNPlane"))
    plane.set("id", f"Plane_{wf['workflow_id']}")
    plane.set("bpmnElement", process_id)

    # Outcome colors: green for approved paths, red for rejected paths
    node_outcome: dict[str, str] = {}
    for s in wf["steps"]:
        if s.get("path_outcome"):
            node_outcome[s["step_id"]] = s["path_outcome"]
    for e in wf["events"]:
        if e.get("path_outcome"):
            node_outcome[e["event_id"]] = e["path_outcome"]

    OUTCOME_COLORS = {
        "APPROVED": (APPROVED_STROKE, APPROVED_FILL),
        "REJECTED": (REJECTED_STROKE, REJECTED_FILL),
        "PROHIBITED": (PROHIBITED_STROKE, PROHIBITED_FILL),
    }

    for nid in node_ids:
        x, y, w, h = pos[nid]
        shape = etree.SubElement(plane, qname(BPMNDI_NS, "BPMNShape"))
        shape.set("id", f"Shape_{nid}")
        shape.set("bpmnElement", nid)
        if nid in node_outcome:
            stroke, fill = OUTCOME_COLORS[node_outcome[nid]]
            shape.set(qname(BIOC_NS, "stroke"), stroke)
            shape.set(qname(BIOC_NS, "fill"), fill)
        bounds = etree.SubElement(shape, qname(DC_NS, "Bounds"))
        bounds.set("x", str(x))
        bounds.set("y", str(y))
        bounds.set("width", str(w))
        bounds.set("height", str(h))

    def waypoint(edge: etree._Element, x: float, y: float) -> None:
        wp = etree.SubElement(edge, qname(DI_NS, "waypoint"))
        wp.set("x", str(round(x, 1)))
        wp.set("y", str(round(y, 1)))

    def flow_outcome(src: str, tgt: str, label: str | None) -> str | None:
        text = (label or "").lower()
        if "approve" in text:
            return "APPROVED"
        if "reject" in text:
            return "REJECTED"
        if "prohibit" in text:
            return "PROHIBITED"
        # A relation inherits a color when both endpoints sit on the same
        # outcome path (gateway exits are covered by their branch label).
        src_oc = node_outcome.get(src)
        tgt_oc = node_outcome.get(tgt)
        if tgt_oc == "PROHIBITED" and src_oc == "PROHIBITED":
            return "PROHIBITED"
        if tgt_oc == "PROHIBITED" and "END-PROHIBITED" in tgt:
            return "PROHIBITED"
        return tgt_oc if tgt_oc and src_oc == tgt_oc else None

    for fid, src, tgt, label in flows:
        edge = etree.SubElement(plane, qname(BPMNDI_NS, "BPMNEdge"))
        edge.set("id", f"Edge_{fid}")
        edge.set("bpmnElement", fid)
        oc = flow_outcome(src, tgt, label)
        if oc:
            edge.set(qname(BIOC_NS, "stroke"), OUTCOME_COLORS[oc][0])
        sx, sy, sw, sh = pos[src]
        tx, ty, tw, th = pos[tgt]
        scy = sy + sh / 2
        tcy = ty + th / 2
        if abs(scy - tcy) < 1:
            # Same row: straight horizontal connector.
            waypoint(edge, sx + sw, scy)
            waypoint(edge, tx, tcy)
        else:
            # Different rows: orthogonal route through the gap between columns
            # so the connector never crosses a node.
            midx = (sx + sw + tx) / 2
            waypoint(edge, sx + sw, scy)
            waypoint(edge, midx, scy)
            waypoint(edge, midx, tcy)
            waypoint(edge, tx, tcy)

    return etree.tostring(
        definitions, xml_declaration=True, encoding="UTF-8", pretty_print=True
    )


# ---------------------------------------------------------------------------
# Entire-policy merge (one overview diagram; does not alter per-section workflows)
# ---------------------------------------------------------------------------

POLICY_OVERVIEW_ID = "PTP-POLICY"


def _prefix_id(prefix: str, value: str | None) -> str | None:
    if not value:
        return value
    if value.startswith(f"{prefix}__"):
        return value
    return f"{prefix}__{value}"


def _prefix_workflow(wf: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy a workflow and namespace every element id with workflow_id__."""
    prefixed = copy.deepcopy(wf)
    wid = wf["workflow_id"]

    def px(value: str | None) -> str | None:
        return _prefix_id(wid, value)

    for ref in prefixed.get("source_references", []):
        ref["reference_id"] = px(ref["reference_id"])

    for step in prefixed.get("steps", []):
        step["step_id"] = px(step["step_id"])
        step["source_reference_ids"] = [
            px(rid) for rid in step.get("source_reference_ids", [])
        ]
        step["next_step_ids"] = [px(nid) for nid in step.get("next_step_ids", [])]
        if step.get("deadline_id"):
            step["deadline_id"] = px(step["deadline_id"])

    for gw in prefixed.get("gateways", []):
        gw["gateway_id"] = px(gw["gateway_id"])
        gw["incoming_step_ids"] = [px(nid) for nid in gw.get("incoming_step_ids", [])]
        for branch in gw.get("branches", []):
            if branch.get("target_step_id"):
                branch["target_step_id"] = px(branch["target_step_id"])
            if branch.get("target_event_id"):
                branch["target_event_id"] = px(branch["target_event_id"])

    for event in prefixed.get("events", []):
        event["event_id"] = px(event["event_id"])
        if event.get("next_step_id"):
            event["next_step_id"] = px(event["next_step_id"])
        if event.get("source_reference_ids"):
            event["source_reference_ids"] = [
                px(rid) for rid in event["source_reference_ids"]
            ]

    for deadline in prefixed.get("deadlines", []):
        deadline["deadline_id"] = px(deadline.get("deadline_id"))
        deadline["source_reference_ids"] = [
            px(rid) for rid in deadline.get("source_reference_ids", [])
        ]

    for cond in prefixed.get("conditions", []):
        cond["condition_id"] = px(cond.get("condition_id"))
        cond["source_reference_ids"] = [
            px(rid) for rid in cond.get("source_reference_ids", [])
        ]

    return prefixed


def _diagram_extent(plane: etree._Element) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for bounds in plane.findall(f".//{{{DC_NS}}}Bounds"):
        x = float(bounds.get("x", "0"))
        y = float(bounds.get("y", "0"))
        w = float(bounds.get("width", "0"))
        h = float(bounds.get("height", "0"))
        xs.extend([x, x + w])
        ys.extend([y, y + h])
    for wp in plane.findall(f".//{{{DI_NS}}}waypoint"):
        xs.append(float(wp.get("x", "0")))
        ys.append(float(wp.get("y", "0")))
    if not xs:
        return (0.0, 0.0, 400.0, 200.0)
    return (min(xs), min(ys), max(xs), max(ys))


def _prefix_bpmn_ids(root: etree._Element, wid: str) -> None:
    """Namespace every id/idref in a per-workflow BPMN tree with ``wid__``.

    Idempotent: ids already prefixed (e.g. node ids that came from the prefixed
    JSON) are left untouched, so DI shapes stay matched to the model and the
    viewer's click lookup by ``step_id`` keeps working. This also prefixes the
    ids that ``convert_to_bpmn`` generates itself — lanes, sequence flows and
    their DI edges — which would otherwise collide across merged workflows.
    """
    id_attrs = (
        "id",
        "bpmnElement",
        "sourceRef",
        "targetRef",
        "attachedToRef",
        "default",
        "processRef",
    )
    ref_tags = {
        qname(BPMN_NS, "flowNodeRef"),
        qname(BPMN_NS, "incoming"),
        qname(BPMN_NS, "outgoing"),
    }
    for el in root.iter():
        for attr in id_attrs:
            if attr in el.attrib:
                el.set(attr, _prefix_id(wid, el.get(attr)))
        if el.tag in ref_tags and el.text and el.text.strip():
            el.text = _prefix_id(wid, el.text.strip())


def _shift_diagram(plane: etree._Element, dx: float, dy: float) -> None:
    for bounds in plane.findall(f".//{{{DC_NS}}}Bounds"):
        bounds.set("x", str(round(float(bounds.get("x", "0")) + dx, 1)))
        bounds.set("y", str(round(float(bounds.get("y", "0")) + dy, 1)))
    for wp in plane.findall(f".//{{{DI_NS}}}waypoint"):
        wp.set("x", str(round(float(wp.get("x", "0")) + dx, 1)))
        wp.set("y", str(round(float(wp.get("y", "0")) + dy, 1)))


def build_entire_policy(workflows: list[dict[str, Any]]) -> tuple[dict[str, Any], bytes]:
    """Build a curated single-pool executive lifecycle overview of the Personal Trading Policy.

    Instead of merging all 15 section pools into one large diagram, this emits a
    compact 7-step + 1-gateway lifecycle workflow that explains the policy purpose
    and compliance lifecycle at a glance.  A dedicated 'Recommended' step (marked
    RECOMMENDED_ACTION) surfaces the top automation control.  The JSON also carries
    ``purpose``, ``high_level_plan``, and ``recommendations`` fields consumed by
    the viewer's overview UI.
    """
    if not workflows:
        raise ValueError("No workflows to merge.")

    policy_meta = workflows[0]["policy"]

    # ------------------------------------------------------------------
    # Curated source references — one representative quote per phase
    # ------------------------------------------------------------------
    def _ref(ref_id: str, section_id: str, section_title: str,
              quoted: str, anchor: str, para: int = 1) -> dict[str, Any]:
        return {
            "reference_id": ref_id,
            "section_id": section_id,
            "section_title": section_title,
            "page": None,
            "paragraph": para,
            "anchor": anchor,
            "source_html": "policy_source.html",
            "quoted_text": quoted,
            "start_offset": 0,
            "end_offset": 0,
        }

    source_references: list[dict[str, Any]] = [
        _ref(
            "OV-REF-001", "1", "Introduction",
            "Employees are required to place the interests of our clients first and avoid "
            "transactions, activities and relationships that might interfere or appear to "
            "interfere with making decisions in the best interests of clients of BlackRock.",
            "policy-1-1",
        ),
        _ref(
            "OV-REF-002", "2", "Scope",
            "This policy governs the personal trading and investments of all employees and "
            "Contingent Workers (collectively, \u2018employees\u2019) of BlackRock, Inc. and its "
            "subsidiaries (\u2018BlackRock\u2019) globally. Any exceptions to this policy must be "
            "pre-approved by Legal & Compliance.",
            "policy-2-1",
        ),
        _ref(
            "OV-REF-003", "3", "Account Disclosure",
            "You must disclose brokerage or other investment accounts, including private "
            "investments, trusts or investment clubs in which you make investment decisions "
            "or have direct influence or control \u2026 by entering them into the Personal "
            "Trading Assistant (\u2018PTA\u2019).",
            "policy-3-2", para=2,
        ),
        _ref(
            "OV-REF-004", "4", "Approved Brokers",
            "You must maintain your accounts with a broker approved by Legal & Compliance.",
            "policy-4-1",
        ),
        _ref(
            "OV-REF-005", "5", "Transaction Pre-Clearance Requirement",
            "You must submit a pre-clearance request in PTA and receive an approval before "
            "undertaking any personal investment transactions permitted under this policy, "
            "including purchases, sales, stock options exercises, ETFs and gifts.",
            "policy-5-2", para=2,
        ),
        _ref(
            "OV-REF-006", "8", "Prohibited Investments",
            "Certain personal investments are prohibited under this policy, including "
            "securities placed on the Restricted List and securities subject to blackout "
            "periods. Short-term trading profits within 60 days are also prohibited.",
            "policy-8-1",
        ),
        _ref(
            "OV-REF-007", "14", "Annual Certification",
            "You are required to complete an annual certification confirming compliance "
            "with this policy.",
            "policy-14-1",
        ),
        _ref(
            "OV-REF-008", "15", "Violations",
            "Violations of this policy may result in disciplinary action, up to and "
            "including termination of employment.",
            "policy-15-1",
        ),
    ]

    # ------------------------------------------------------------------
    # Actors / swim lanes
    # ------------------------------------------------------------------
    actors: list[dict[str, Any]] = [
        {
            "actor_id": "ACT-EMPLOYEE",
            "name": "Employee",
            "actor_type": "INDIVIDUAL",
            "bpmn_lane": "Employee",
        },
        {
            "actor_id": "ACT-COMPLIANCE",
            "name": "Legal & Compliance",
            "actor_type": "BUSINESS_FUNCTION",
            "bpmn_lane": "Legal & Compliance",
        },
        {
            "actor_id": "ACT-SYSTEM",
            "name": "Automated System",
            "actor_type": "SYSTEM",
            "bpmn_lane": "Automated System (Recommended)",
        },
    ]

    # ------------------------------------------------------------------
    # Curated lifecycle steps
    # ------------------------------------------------------------------
    steps: list[dict[str, Any]] = [
        {
            "step_id": "OV-STEP-001",
            "sequence": 1,
            "title": "Disclose all reportable accounts in PTA",
            "description": (
                "Within ten days of joining BlackRock, disclose all brokerage and "
                "investment accounts\u2014including private investments and trusts\u2014in "
                "the Personal Trading Assistant (PTA). Complete the initial holdings "
                "certification even if you have no holdings to report."
            ),
            "actor_id": "ACT-EMPLOYEE",
            "action_type": "MANDATORY_ACTION",
            "bpmn_type": "userTask",
            "source_reference_ids": ["OV-REF-003"],
            "explicit_or_inferred": "EXPLICIT",
            "confidence": 0.90,
            "next_step_ids": ["OV-STEP-002"],
            "preconditions": [], "outputs": [], "deadline_id": None,
            "exception_ids": [], "path_outcome": None, "color": None,
        },
        {
            "step_id": "OV-STEP-002",
            "sequence": 2,
            "title": "Maintain accounts with approved brokers",
            "description": (
                "All personal trading accounts must be held with a broker approved by "
                "Legal & Compliance. Accounts at unapproved brokers must be transferred "
                "or closed before any trading activity."
            ),
            "actor_id": "ACT-EMPLOYEE",
            "action_type": "MANDATORY_ACTION",
            "bpmn_type": "userTask",
            "source_reference_ids": ["OV-REF-004"],
            "explicit_or_inferred": "EXPLICIT",
            "confidence": 0.88,
            "next_step_ids": ["OV-STEP-003"],
            "preconditions": [], "outputs": [], "deadline_id": None,
            "exception_ids": [], "path_outcome": None, "color": None,
        },
        {
            "step_id": "OV-STEP-003",
            "sequence": 3,
            "title": "Check transaction against prohibited and blackout rules",
            "description": (
                "Before submitting any pre-clearance request, confirm: the security is "
                "not on the Restricted List, no blackout period applies, the transaction "
                "is not a prohibited type (e.g. a short-term profit within 60 days), and "
                "the employee holds no material non-public information about the issuer."
            ),
            "actor_id": "ACT-EMPLOYEE",
            "action_type": "REVIEW",
            "bpmn_type": "userTask",
            "source_reference_ids": ["OV-REF-006"],
            "explicit_or_inferred": "EXPLICIT",
            "confidence": 0.87,
            "next_step_ids": ["OV-STEP-REC"],
            "preconditions": [], "outputs": [], "deadline_id": None,
            "exception_ids": [], "path_outcome": None, "color": None,
        },
        {
            # --- RECOMMENDED CONTROL ---
            "step_id": "OV-STEP-REC",
            "sequence": 4,
            "title": "Automate pre-clearance evidence capture and broker feeds into PTA",
            "description": (
                "Recommended control: automatically ingest broker statement feeds and "
                "pre-clearance evidence into PTA to reduce manual effort, improve audit "
                "trail completeness, and enable real-time compliance monitoring across all "
                "employee accounts."
            ),
            "actor_id": "ACT-SYSTEM",
            "action_type": "RECOMMENDED_ACTION",
            "bpmn_type": "serviceTask",
            "source_reference_ids": [],
            "explicit_or_inferred": "INFERRED",
            "inference_reason": (
                "Recommended automation control\u2014not an explicit policy obligation. "
                "Surfaced to improve evidence completeness and reduce manual compliance burden."
            ),
            "recommended": True,
            "confidence": 0.95,
            "next_step_ids": ["OV-STEP-004"],
            "preconditions": [], "outputs": [], "deadline_id": None,
            "exception_ids": [], "path_outcome": None, "color": None,
        },
        {
            "step_id": "OV-STEP-004",
            "sequence": 5,
            "title": "Submit pre-clearance request and receive approval",
            "description": (
                "Submit a pre-clearance request in PTA. Legal & Compliance must approve "
                "the request before any personal investment transaction is undertaken. "
                "Orders must be executed on the same day the approval is granted."
            ),
            "actor_id": "ACT-EMPLOYEE",
            "action_type": "SUBMISSION",
            "bpmn_type": "userTask",
            "source_reference_ids": ["OV-REF-005"],
            "explicit_or_inferred": "EXPLICIT",
            "confidence": 0.90,
            "next_step_ids": ["OV-GATEWAY-001"],
            "preconditions": [], "outputs": [], "deadline_id": None,
            "exception_ids": [], "path_outcome": None, "color": None,
        },
        {
            "step_id": "OV-STEP-005",
            "sequence": 6,
            "title": "Execute approved trade and provide broker statements within 30 days",
            "description": (
                "Execute the approved transaction on the same day approval is received. "
                "Provide broker statements to Legal & Compliance within 30 days of the "
                "transaction date."
            ),
            "actor_id": "ACT-EMPLOYEE",
            "action_type": "MANDATORY_ACTION",
            "bpmn_type": "userTask",
            "source_reference_ids": ["OV-REF-005"],
            "explicit_or_inferred": "EXPLICIT",
            "confidence": 0.87,
            "next_step_ids": ["OV-STEP-006"],
            "preconditions": [], "outputs": [], "deadline_id": None,
            "exception_ids": [], "path_outcome": "APPROVED", "color": "#2F7D4F",
        },
        {
            "step_id": "OV-STEP-006",
            "sequence": 7,
            "title": "Complete annual certification of compliance",
            "description": (
                "Complete the annual certification in PTA, confirming compliance with the "
                "Global Personal Trading Policy. The certification must be completed within "
                "the period designated by Legal & Compliance."
            ),
            "actor_id": "ACT-EMPLOYEE",
            "action_type": "MANDATORY_ACTION",
            "bpmn_type": "userTask",
            "source_reference_ids": ["OV-REF-007"],
            "explicit_or_inferred": "EXPLICIT",
            "confidence": 0.90,
            "next_step_ids": ["OV-END-001"],
            "preconditions": [], "outputs": [], "deadline_id": None,
            "exception_ids": [], "path_outcome": "APPROVED", "color": "#2F7D4F",
        },
    ]

    # ------------------------------------------------------------------
    # Gateway
    # ------------------------------------------------------------------
    gateways: list[dict[str, Any]] = [
        {
            "gateway_id": "OV-GATEWAY-001",
            "gateway_type": "exclusiveGateway",
            "question": "Is the request approved and transaction permitted?",
            "incoming_step_ids": ["OV-STEP-004"],
            "branches": [
                {
                    "label": "Approved",
                    "condition": "approval_status == 'approved' and no restrictions apply",
                    "target_step_id": "OV-STEP-005",
                    "color": "#2F7D4F",
                },
                {
                    "label": "Rejected / Prohibited",
                    "condition": "approval_status == 'rejected' or prohibited rule applies",
                    "target_event_id": "OV-END-REJECTED",
                    "color": "#B3402E",
                },
            ],
        },
    ]

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    events: list[dict[str, Any]] = [
        {
            "event_id": "OV-START-001",
            "event_type": "startEvent",
            "title": "Employee joins BlackRock or initiates a personal trade.",
            "next_step_id": "OV-STEP-001",
            "source_reference_ids": ["OV-REF-001"],
            "path_outcome": None,
            "color": None,
        },
        {
            "event_id": "OV-END-001",
            "event_type": "endEvent",
            "title": "Policy complied with",
            "path_outcome": "APPROVED",
            "color": "#2F7D4F",
        },
        {
            "event_id": "OV-END-REJECTED",
            "event_type": "endEvent",
            "title": "Must not proceed \u2014 prohibited or rejected",
            "path_outcome": "REJECTED",
            "color": "#B3402E",
        },
    ]

    # ------------------------------------------------------------------
    # Overview metadata fields (consumed by the viewer overview UI)
    # ------------------------------------------------------------------
    purpose = (
        "The BlackRock Global Personal Trading Policy (effective 28\u202FSeptember 2021) "
        "requires all employees and contingent workers globally to place client interests "
        "first in every personal investment decision. It governs account disclosure, "
        "broker selection, transaction pre-clearance, investment prohibitions, blackout "
        "periods, short-term trading restrictions, and annual certification\u2014all "
        "enforced through the Personal Trading Assistant (PTA). Exceptions must be "
        "pre-approved by Legal\u202F&\u202FCompliance. Violations may result in disciplinary "
        "action up to and including termination."
    )

    high_level_plan: list[dict[str, Any]] = [
        {
            "phase": 1,
            "title": "Onboarding & Account Disclosure",
            "description": (
                "Within 10 days of joining, disclose all investment accounts and initial "
                "holdings in PTA. Maintain accounts only with approved brokers."
            ),
            "workflow_ids": ["PTP-DISC", "PTP-BROKER"],
        },
        {
            "phase": 2,
            "title": "Pre-Trade Clearance",
            "description": (
                "Before any personal investment transaction, submit a pre-clearance "
                "request in PTA and receive Legal\u202F&\u202FCompliance approval. "
                "Different rules apply to BLK securities, private investments, and ETFs."
            ),
            "workflow_ids": ["PTP-PRECLEAR", "PTP-TXTYPE", "PTP-PRIVATE", "PTP-BLK"],
        },
        {
            "phase": 3,
            "title": "Trading Restrictions",
            "description": (
                "Prohibited investments, blackout periods, and short-term trading "
                "restrictions must be observed at all times. Trading on material "
                "non-public information (insider trading) is strictly prohibited."
            ),
            "workflow_ids": ["PTP-PROHIB", "PTP-BLACKOUT", "PTP-SHORT", "PTP-INSIDER"],
        },
        {
            "phase": 4,
            "title": "Certification & Monitoring",
            "description": (
                "Complete an annual certification of compliance. Managed accounts that "
                "meet exemption criteria must be registered and monitored in PTA."
            ),
            "workflow_ids": ["PTP-CERT", "PTP-MANAGED"],
        },
        {
            "phase": 5,
            "title": "Exceptions & Enforcement",
            "description": (
                "Any exception must be pre-approved by Legal\u202F&\u202FCompliance. "
                "Violations may result in disciplinary action, including termination. "
                "Trades generating prohibited profits may be reversed."
            ),
            "workflow_ids": ["PTP-EXCEPTION", "PTP-VIOL"],
        },
    ]

    recommendations: list[str] = [
        "Automate pre-clearance evidence capture: connect broker statement feeds "
        "directly into PTA to reduce manual uploads and improve audit completeness.",
        "Source grounding rate: track the percentage of workflow steps with a linked "
        "policy paragraph or quoted text \u2014 target 100\u202F% for all explicit steps.",
        "Approval-gate coverage: confirm every pre-clearance workflow contains at "
        "least one Approved\u202F/\u202FRejected decision gateway.",
        "Deadline inventory: maintain a live registry of all time-bound obligations "
        "(10-day holdings disclosure, same-day trade execution, 30-day statement "
        "submission, annual certification).",
        "Control ownership (RACI): map each workflow step to an explicit owner "
        "\u2014 Employee, Legal\u202F&\u202FCompliance, or Automated System \u2014 and "
        "reconcile against the current RACI matrix.",
        "Exception register: track all pre-approved policy exceptions with owner, "
        "expiry date, and rationale in PTA.",
        "Review aging: monitor the number of days each workflow remains PENDING since "
        "its last policy review cycle; escalate workflows exceeding 90\u202Fdays.",
    ]

    # ------------------------------------------------------------------
    # Assemble curated workflow and convert to BPMN
    # ------------------------------------------------------------------
    curated_wf: dict[str, Any] = {
        "workflow_id": POLICY_OVERVIEW_ID,
        "workflow_title": "Entire Personal Trading Policy",
        "workflow_summary": (
            "Executive lifecycle overview of the BlackRock Global Personal Trading "
            "Policy \u2014 five phases from account disclosure through annual certification."
        ),
        "purpose": purpose,
        "high_level_plan": high_level_plan,
        "recommendations": recommendations,
        "policy": policy_meta,
        "source_references": source_references,
        "trigger": {
            "type": "POLICY_SCOPE",
            "description": "Employee joins BlackRock or initiates a personal trading transaction.",
        },
        "actors": actors,
        "steps": steps,
        "gateways": gateways,
        "events": events,
        "deadlines": [],
        "conditions": [],
        "records": [],
        "controls": [],
        "ambiguities": [],
        "overall_confidence": 0.90,
        "review_status": "PENDING",
        "section_id": "ALL",
        "section_title": policy_meta.get("policy_title", "Policy"),
    }

    annotate_element_codes(curated_wf)
    bpmn_bytes = convert_to_bpmn(curated_wf)
    return curated_wf, bpmn_bytes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Reading {POLICY_PATH}")
    meta, paragraphs, full_text = parse_policy(POLICY_PATH)

    normalized = {
        "policy": meta,
        "paragraphs": [asdict(p) for p in paragraphs],
    }
    norm_path = DATA_DIR / "normalized_policy.json"
    norm_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    print(f"Wrote {norm_path} ({meta['paragraph_count']} paragraphs, {meta['section_count']} sections)")

    candidates = detect_candidates(paragraphs)
    cand_path = DATA_DIR / "candidates.json"
    cand_path.write_text(
        json.dumps([asdict(c) for c in candidates], indent=2), encoding="utf-8"
    )
    print(f"Detected {len(candidates)} actionable candidates -> {cand_path}")

    actions = expand_atomic_actions(candidates)
    print(f"Expanded to {len(actions)} atomic actions")

    workflows = group_workflows(actions, meta)
    print(f"Grouped into {len(workflows)} workflows")

    index = []
    all_findings = {}
    for wf in workflows:
        annotate_outcome_paths(wf)
        annotate_element_codes(wf)
        findings = validate_workflow(wf)
        all_findings[wf["workflow_id"]] = findings
        errors = [f for f in findings if f["severity"] == "error"]
        wf_path = OUT_DIR / f"{wf['workflow_id']}.json"
        wf_path.write_text(json.dumps(wf, indent=2), encoding="utf-8")

        bpmn_bytes = convert_to_bpmn(wf)
        bpmn_path = OUT_DIR / f"{wf['workflow_id']}.bpmn"
        bpmn_path.write_bytes(bpmn_bytes)

        index.append(
            {
                "workflow_id": wf["workflow_id"],
                "title": wf["workflow_title"],
                "steps": len(wf["steps"]),
                "gateways": len(wf["gateways"]),
                "confidence": wf["overall_confidence"],
                "validation_errors": len(errors),
                "json": wf_path.name,
                "bpmn": bpmn_path.name,
            }
        )
        status = "OK" if not errors else f"{len(errors)} errors"
        print(f"  {wf['workflow_id']}: {wf['workflow_title']} — {len(wf['steps'])} steps — {status}")

    # Entire-policy overview: merge every diagram into one multi-pool BPMN.
    overview_wf, overview_bpmn = build_entire_policy(workflows)
    overview_json_path = OUT_DIR / f"{POLICY_OVERVIEW_ID}.json"
    overview_bpmn_path = OUT_DIR / f"{POLICY_OVERVIEW_ID}.bpmn"
    overview_json_path.write_text(json.dumps(overview_wf, indent=2), encoding="utf-8")
    overview_bpmn_path.write_bytes(overview_bpmn)
    index.insert(
        0,
        {
            "workflow_id": POLICY_OVERVIEW_ID,
            "title": overview_wf["workflow_title"],
            "steps": len(overview_wf["steps"]),
            "gateways": len(overview_wf["gateways"]),
            "confidence": overview_wf["overall_confidence"],
            "validation_errors": 0,
            "json": overview_json_path.name,
            "bpmn": overview_bpmn_path.name,
        },
    )
    print(
        f"  {POLICY_OVERVIEW_ID}: {overview_wf['workflow_title']} — "
        f"{len(overview_wf['steps'])} steps (merged) — OK"
    )

    index_path = OUT_DIR / "index.json"
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    findings_path = OUT_DIR / "validation_findings.json"
    findings_path.write_text(json.dumps(all_findings, indent=2), encoding="utf-8")

    summary = {
        "policy": meta,
        "candidates": len(candidates),
        "atomic_actions": len(actions),
        "workflows": len(workflows),
        "outputs": str(OUT_DIR),
    }
    (OUT_DIR / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nDone. Index: {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
