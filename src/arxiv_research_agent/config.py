"""Configuration loading with project-relative path resolution."""

from dataclasses import dataclass
from pathlib import Path
from typing import List

import yaml


@dataclass(frozen=True)
class Paths:
    root: Path
    inbox_pending: Path
    inbox_processed: Path
    inbox_rejected: Path
    knowledge: Path
    state: Path
    logs: Path


@dataclass(frozen=True)
class InboxConfig:
    supported_schema_versions: List[str]


@dataclass(frozen=True)
class KnowledgeConfig:
    auto_merge_exact_matches: bool


@dataclass(frozen=True)
class TechnocoreConfig:
    base_url: str
    room: str
    auto_publish: bool
    identity_file: Path
    max_note_chars: int
    request_timeout_seconds: float
    prohibited_patterns: List[str]
    sync_limit: int
    notify_on_reaction: bool


@dataclass(frozen=True)
class AppConfig:
    paths: Paths
    inbox: InboxConfig
    knowledge: KnowledgeConfig
    technocore: TechnocoreConfig


def load_config(path: Path = Path("config.yaml")) -> AppConfig:
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError("Configuration file not found: %s" % path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    root = path.parent
    inbox_raw = raw.get("inbox", {})
    knowledge_raw = raw.get("knowledge", {})
    tc_raw = raw.get("technocore", {})
    identity_file = root / tc_raw.get("identity_file", "identities/identity.pem")
    return AppConfig(
        paths=Paths(
            root=root,
            inbox_pending=root / "inbox" / "pending",
            inbox_processed=root / "inbox" / "processed",
            inbox_rejected=root / "inbox" / "rejected",
            knowledge=root / "knowledge",
            state=root / "state",
            logs=root / "logs",
        ),
        inbox=InboxConfig(
            supported_schema_versions=[
                str(value)
                for value in inbox_raw.get("supported_schema_versions", ["1.0"])
            ]
        ),
        knowledge=KnowledgeConfig(
            auto_merge_exact_matches=bool(
                knowledge_raw.get("auto_merge_exact_matches", True)
            )
        ),
        technocore=TechnocoreConfig(
            base_url=str(tc_raw.get("base_url", "https://technocore.chat")).rstrip("/"),
            room=str(tc_raw.get("room", "crypto")),
            auto_publish=bool(tc_raw.get("auto_publish", False)),
            identity_file=identity_file,
            max_note_chars=int(tc_raw.get("max_note_chars", 4096)),
            request_timeout_seconds=float(tc_raw.get("request_timeout_seconds", 20)),
            prohibited_patterns=list(tc_raw.get("prohibited_patterns", [])),
            sync_limit=min(200, max(1, int(tc_raw.get("sync_limit", 200)))),
            notify_on_reaction=bool(tc_raw.get("notify_on_reaction", True)),
        ),
    )
