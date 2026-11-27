"""Prompt loader + Pass A–E message golden tests."""

from __future__ import annotations

import json

import pytest

from policy_knowledge.intelligence.prompt_loader import (
    PromptError,
    clear_prompt_cache,
    list_prompt_ids,
    load_prompt,
    render_template,
)
from policy_knowledge.intelligence.extraction_pipeline import _blocks_payload, _pass_messages
from policy_knowledge.model.schemas import SourceBlock


LEGACY_SYSTEM = {
    "pass_a": (
        "# Pass A — Source interpretation\n\n"
        "Identify policy identity, sections, normative obligations, roles, definitions and procedure candidates.\n"
        "Every item must include source_refs that cite provided SourceBlock ids.\n"
        "Do not invent owners, dates, or obligations absent from the source.\n"
    ),
    "pass_b": (
        "# Pass B — Process candidates\n\n"
        "Extract the procedure the source describes: triggers, actions (tasks), actors, decisions, outputs, approvals and exceptions.\n\n"
        "Rules:\n"
        "- Every task a person or system must carry out is one action. Give it a short imperative label (for example \"Obtain pre-clearance\"), a one-sentence description, the actor role names as the source states them, and the SourceBlock ids that state the task in source_refs.\n"
        "- Obligations written with \"must\", \"shall\", \"is required to\", \"must not\" or \"should\" describe a task when they say who does what. Include them as actions.\n"
        "- Do not return an empty actions list when the source contains such an obligation. An empty list is correct only when the document is principles-only or purpose-only.\n"
        "- If the document is principles-only / nonprocedural, set modeling_status to unsupported and leave actions, decisions and flow empty. Do not fabricate tasks.\n"
        "- Otherwise set modeling_status to supported (the procedure is complete in the source), partial (steps are missing from the source) or needs_review (the source is unclear).\n"
        "- decisions: whenever the source requires pre-clearance, approval, permission, eligibility checks, or prohibits an activity, emit a decision with:\n"
        "  - question: clear yes/no question (for example \"Is the request approved and transaction permitted?\")\n"
        "  - branches: at least two branch objects shaped {\"condition\": \"<Approved / Permitted | Rejected / Prohibited | Yes | No>\", \"outcome\": \"<PROCEED | PROHIBITED | ESCALATE>\", \"next_action_label\": \"<exact label from actions, or null if the branch stops>\", \"end_label\": \"<short end text when next_action_label is null, for example 'Must not proceed — prohibited or rejected'>\"}\n"
        "  - source_refs: the SourceBlock ids supporting the decision and rejection/prohibition outcome.\n"
        "- flow: one entry per ordering step, shaped {\"from\": \"<action label>\", \"to\": \"<action label>\"}, using labels exactly as written in actions. Never output an empty object.\n"
        "- Do not invent actors, steps or citations absent from the source.\n"
    ),
    "pass_c": (
        "# Pass C — Governance mapping\n\n"
        "Identify source-stated risks, controls and evidence. Link only when cited.\n"
        "Leave frequency/owner as null or not_specified when absent. Never invent them.\n"
    ),
    "pass_d": (
        "# Pass D — Relationships\n\n"
        "Emit typed edges using the approved vocabulary. Mark non-explicit links as inferred_for_review.\n"
    ),
    "pass_e": (
        "# Pass E — QA findings\n\n"
        "Surface ambiguity, missing owners, uncited claims, and reviewer questions.\n"
    ),
}


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_prompt_cache()
    yield
    clear_prompt_cache()


def test_pass_system_prompts_match_legacy_text():
    for key, expected in LEGACY_SYSTEM.items():
        loaded = load_prompt(f"{key}.system").text
        assert loaded == expected
        # Legacy filename alias still resolves
        assert load_prompt(f"{key}.md").text == expected


def test_pass_user_messages_match_prior_inline_format():
    blocks = [
        SourceBlock(
            id="SRC-0001",
            policy_id="P1",
            section_path="1",
            text="Employees must escalate incidents.",
            block_type="paragraph",
            source_locator="p1",
            sequence=1,
            document_hash="abc",
        )
    ]
    payload = _blocks_payload(blocks)
    for letter, key in zip("ABCDE", ["pass_a", "pass_b", "pass_c", "pass_d", "pass_e"]):
        messages = _pass_messages(key, payload)
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == LEGACY_SYSTEM[key]
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == f"PASS_{letter}\n{payload}"


def test_render_requires_declared_vars():
    with pytest.raises(PromptError, match="Missing required"):
        load_prompt("pass_a.user", variables={})


def test_render_rejects_unknown_vars():
    with pytest.raises(PromptError, match="Unknown prompt variables"):
        render_template("Hello {{name}}", {}, required_vars=())


def test_schema_json_object_prompt():
    text = load_prompt(
        "schema_json_object",
        variables={"schema_json": '{"type":"object"}'},
    ).text
    assert "Respond with a single JSON object" in text
    assert '{"type":"object"}' in text


def test_list_prompt_ids_includes_role_relevance():
    ids = list_prompt_ids()
    assert "role_relevance.system" in ids
    assert "pass_a.system" in ids


def test_manifest_versions_are_strings():
    tmpl = load_prompt("pass_a.system")
    assert tmpl.version == "1.0.0"
