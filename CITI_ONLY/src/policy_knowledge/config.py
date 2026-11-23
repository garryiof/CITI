"""Application and transfer configuration (master prompt §8.4 / §20)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml


@dataclass
class WorkspaceConfig:
    id: str = "POLICY_001"
    policy_path: str | None = None
    output_root: str = "policy_runs"
    run_id: str | None = None
    allow_source_copy: bool = False
    overwrite: bool = False


@dataclass
class LLMConfig:
    # mock | guardrail | llama4 (alias→guardrail).
    # CITI Hub: guardrail/llama4 + POLICY_LLM_MODEL (e.g. Llama-4-Scout).
    # Tests / offline: mock.
    provider: str = "guardrail"
    model: str | None = "Llama-4-Scout"
    narrative_model: str | None = None
    temperature: float = 0.0
    n: int = 1
    max_chunk_chars: int = 12000
    max_retries: int = 3
    extra_body: dict[str, Any] = field(default_factory=dict)
    parse_extra_body: dict[str, Any] = field(default_factory=dict)
    log_prompt_text: bool = False
    log_completion_text: bool = False


@dataclass
class ProcessingConfig:
    allow_ocr: bool = False
    require_source_refs: bool = True
    enable_inferred_mappings: bool = True
    inferred_mappings_need_review: bool = True


@dataclass
class ViewerConfig:
    offline_assets: bool = True
    file_url_compatible: bool = True
    embed_viewer_data: bool = True
    default_tab: str = "knowledge_map"
    renderer_bpmn: str = "bpmn_js_navigated_viewer"
    renderer_graph: str = "cytoscape_js"
    js_assets_root: str = "src/policy_knowledge/viewer/vendor"
    javascript_mode: str = "classic_script"
    require_browser_verification: bool = True
    fail_demo_ready_on_missing_vendor_assets: bool = True


@dataclass
class PackagingConfig:
    create_full_archive: bool = True
    create_demo_archive: bool = True
    exclude_archive_dir_from_full_zip: bool = True
    include_intermediate_in_full_archive: bool = False
    allow_confidential_demo_export: bool = False
    allow_workstation_transfer: bool = False


@dataclass
class TransferPolicy:
    """Archive / transfer gates.

    include_policy_excerpts_in_demo defaults True so demo/data.js always
    carries parsed policy text for index.html. Workstation DEMO ZIP transfer
    still defaults deny.
    """

    workstation_transfer_approved: bool = False
    include_source_in_full: bool = False
    include_intermediate_in_full: bool = False
    include_policy_excerpts_in_demo: bool = True


@dataclass
class AppConfig:
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)
    viewer: ViewerConfig = field(default_factory=ViewerConfig)
    packaging: PackagingConfig = field(default_factory=PackagingConfig)
    transfer: TransferPolicy = field(default_factory=TransferPolicy)


def _merge_dataclass(cls: type, data: dict[str, Any] | None) -> Any:
    if not data:
        return cls()
    allowed = {f.name for f in fields(cls)}
    kwargs = {k: v for k, v in data.items() if k in allowed}
    return cls(**kwargs)


def _from_mapping(raw: dict[str, Any]) -> AppConfig:
    return AppConfig(
        workspace=_merge_dataclass(WorkspaceConfig, raw.get("workspace")),
        llm=_merge_dataclass(LLMConfig, raw.get("llm")),
        processing=_merge_dataclass(ProcessingConfig, raw.get("processing")),
        viewer=_merge_dataclass(ViewerConfig, raw.get("viewer")),
        packaging=_merge_dataclass(PackagingConfig, raw.get("packaging")),
        transfer=_merge_dataclass(TransferPolicy, raw.get("transfer") or raw.get("packaging_transfer")),
    )


def _apply_env_overrides(config: AppConfig) -> AppConfig:
    """Apply non-secret env overrides. API keys / SOEID never persisted to files."""
    provider = os.environ.get("POLICY_LLM_PROVIDER")
    if provider:
        config.llm.provider = provider.strip().lower()
    model = os.environ.get("POLICY_LLM_MODEL")
    if model:
        config.llm.model = model
    narrative = os.environ.get("POLICY_LLM_NARRATIVE_MODEL")
    if narrative:
        config.llm.narrative_model = narrative
    policy_path = os.environ.get("POLICY_PATH")
    if policy_path:
        config.workspace.policy_path = policy_path
    workspace_id = os.environ.get("POLICY_WORKSPACE_ID")
    if workspace_id:
        config.workspace.id = workspace_id
    return config


def load_config(path: Path | None = None) -> AppConfig:
    """Load AppConfig from YAML (optional) and env overrides."""
    if path is None:
        return _apply_env_overrides(AppConfig())
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config root must be a mapping: {path}")
    return _apply_env_overrides(_from_mapping(raw))
