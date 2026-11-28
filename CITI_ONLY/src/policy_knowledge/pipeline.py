"""End-to-end policy demo orchestration."""

from __future__ import annotations

from typing import Optional


import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from policy_knowledge.config import AppConfig, TransferPolicy
from policy_knowledge.exporters.bpmn_exporter import export_bpmn
from policy_knowledge.exporters.json_exporter import export_canonical_json
from policy_knowledge.exporters.matrix_exporter import export_matrices
from policy_knowledge.exporters.okf_exporter import export_okf
from policy_knowledge.exporters.p2b_exporter import export_p2b_workflows
from policy_knowledge.exporters.role_steps_exporter import export_role_steps
from policy_knowledge.exporters.viewer_exporter import build_offline_demo
from policy_knowledge.ingestion import read_policy
from policy_knowledge.intelligence.extraction_pipeline import extract_policy
from policy_knowledge.intelligence.guardrail_client import LLMAdapter
from policy_knowledge.intelligence.llm_factory import llm_runtime_status
from policy_knowledge.intelligence.role_relevance import (
    analyze_role_relevance,
    export_role_relevance,
)
from policy_knowledge.model.schemas import PolicyKnowledge
from policy_knowledge.validation.bpmn_validator import validate_bpmn_dir
from policy_knowledge.validation.offline_demo_validator import validate_offline_demo
from policy_knowledge.validation.okf_validator import validate_okf
from policy_knowledge.validation.quality_report import build_quality_report
from policy_knowledge.validation.role_relevance_validator import validate_role_relevance
from policy_knowledge.validation.schema_validator import validate_knowledge


@dataclass
class PipelineResult:
    run_dir: Path
    knowledge: PolicyKnowledge
    artifact_paths: dict[str, str] = field(default_factory=dict)
    validation: dict = field(default_factory=dict)
    run_id: str = ""
    policy_id: str = ""


def _default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-POC"


def run_policy_demo(
    policy_path: Path,
    policy_id: str,
    config: AppConfig,
    llm: LLMAdapter,
    *,
    run_id: Optional[str] = None,
    overwrite: Optional[bool] = None,
    transfer_policy: Optional[TransferPolicy] = None,
) -> PipelineResult:
    policy_path = Path(policy_path)
    run_id = run_id or config.workspace.run_id or _default_run_id()
    allow_overwrite = config.workspace.overwrite if overwrite is None else overwrite
    output_root = Path(config.workspace.output_root)
    run_dir = output_root / policy_id / run_id

    if run_dir.exists():
        if not allow_overwrite:
            raise FileExistsError(
                f"Run directory exists: {run_dir}. Pass overwrite=True to replace."
            )
        shutil.rmtree(run_dir)

    for sub in (
        "input",
        "intermediate",
        "outputs/canonical",
        "outputs/okf",
        "outputs/bpmn",
        "outputs/matrices",
        "outputs/viewer",
        "demo",
        "archive",
        "logs",
        "config_snapshot",
    ):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)

    # Optional source copy (off by default)
    if config.workspace.allow_source_copy:
        shutil.copy2(policy_path, run_dir / "input" / policy_path.name)

    blocks = read_policy(policy_path, policy_id=policy_id)
    knowledge = extract_policy(
        blocks,
        llm,
        policy_id=policy_id,
        title=policy_path.stem,
        input_path=str(policy_path),
        require_source_refs=config.processing.require_source_refs,
        max_chunk_chars=int(config.llm.max_chunk_chars or 12000),
    )

    (run_dir / "intermediate" / "source_blocks.json").write_text(
        json.dumps([b.model_dump() for b in blocks], indent=2),
        encoding="utf-8",
    )

    export_canonical_json(knowledge, run_dir / "outputs" / "canonical")
    export_okf(knowledge, run_dir / "outputs" / "okf")
    export_bpmn(knowledge, run_dir / "outputs" / "bpmn")
    export_p2b_workflows(knowledge, run_dir / "outputs" / "p2b")
    export_matrices(knowledge, run_dir / "outputs" / "matrices")

    runtime_preview = llm_runtime_status(llm)
    role_doc = analyze_role_relevance(
        knowledge,
        llm,
        provider=runtime_preview.get("llm_provider"),
        model=config.llm.model,
        temperature=float(config.llm.temperature or 0.0),
    )
    role_path = export_role_relevance(
        role_doc,
        run_dir / "outputs" / "canonical" / "role_relevance.json",
    )
    role_steps_path = export_role_steps(
        run_dir / "outputs" / "p2b",
        role_doc.model_dump(),
        run_dir / "outputs" / "canonical" / "role_steps.json",
        policy_id=knowledge.policy.id,
        policy_title=knowledge.policy.title,
    )

    demo_dir = build_offline_demo(
        knowledge,
        run_dir,
        transfer_policy=transfer_policy or config.transfer,
        role_relevance=role_doc.model_dump(),
    )

    validation = {
        "knowledge": validate_knowledge(knowledge).to_dict(),
        "okf": validate_okf(run_dir / "outputs" / "okf").to_dict(),
        "bpmn": validate_bpmn_dir(run_dir / "outputs" / "bpmn").to_dict(),
        "offline_demo": validate_offline_demo(demo_dir).to_dict(),
        "role_relevance": validate_role_relevance(role_doc, knowledge).to_dict(),
        "quality": build_quality_report(knowledge),
    }
    (run_dir / "outputs" / "qa_report.json").write_text(
        json.dumps(validation, indent=2),
        encoding="utf-8",
    )

    runtime = runtime_preview
    # Sanitized config snapshot (no secrets / no API keys)
    snap = {
        "workspace_id": config.workspace.id,
        "output_root": config.workspace.output_root,
        "llm_provider": runtime["llm_provider"],
        "llm_status": runtime["llm_status"],
        "llm_model": config.llm.model,
        "require_source_refs": config.processing.require_source_refs,
        "transfer_defaults": {
            "workstation_transfer_approved": config.transfer.workstation_transfer_approved,
            "include_policy_excerpts_in_demo": config.transfer.include_policy_excerpts_in_demo,
        },
        "role_relevance_prompt": role_doc.prompt,
    }
    (run_dir / "config_snapshot" / "app_sanitized.json").write_text(
        json.dumps(snap, indent=2),
        encoding="utf-8",
    )

    artifact_paths = {
        "canonical": str(run_dir / "outputs" / "canonical" / "policy_knowledge.json"),
        "role_relevance": str(role_path),
        "role_steps": str(role_steps_path),
        "okf": str(run_dir / "outputs" / "okf"),
        "bpmn": str(run_dir / "outputs" / "bpmn"),
        "p2b_workflows": str(run_dir / "outputs" / "p2b"),
        "matrices": str(run_dir / "outputs" / "matrices"),
        "demo": str(demo_dir),
        "qa": str(run_dir / "outputs" / "qa_report.json"),
    }
    manifest = {
        "policy_id": policy_id,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "policy_path": str(policy_path),
        "artifact_paths": artifact_paths,
        "validation_summary": {
            k: v.get("ok") if isinstance(v, dict) and "ok" in v else v
            for k, v in validation.items()
        },
        "llm_provider": runtime["llm_provider"],
        "llm_status": runtime["llm_status"],
        "guardrail_status": runtime["guardrail_status"],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return PipelineResult(
        run_dir=run_dir,
        knowledge=knowledge,
        artifact_paths=artifact_paths,
        validation=validation,
        run_id=run_id,
        policy_id=policy_id,
    )
