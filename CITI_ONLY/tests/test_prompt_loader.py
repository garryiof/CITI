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
        "Extract triggers, tasks, actors, decisions, outputs, approvals and exceptions when the source supports a procedure.\n"
        "If the document is principles-only / nonprocedural, set modeling_status to unsupported and do not fabricate tasks.\n"
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
