"""Inbox processing orchestration. This module never invokes an LLM."""

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from arxiv_research_agent.config import AppConfig
from arxiv_research_agent.inbox.parser import ParseError, parse_research_result
from arxiv_research_agent.inbox.validator import revision_number, validate_research_result
from arxiv_research_agent.knowledge.linker import find_link_candidates, write_candidate_index
from arxiv_research_agent.knowledge.repository import KnowledgeRepository
from arxiv_research_agent.knowledge.topic_manager import rebuild_topics
from arxiv_research_agent.logging_utils import get_logger
from arxiv_research_agent.state.manager import StateManager, utc_now
from arxiv_research_agent.technocore.client import TechnocoreClient
from arxiv_research_agent.technocore.publisher import Publisher


@dataclass
class ProcessSummary:
    detected: int = 0
    valid: int = 0
    rejected: int = 0
    processed: int = 0
    skipped: int = 0
    revisions: int = 0
    created_insights: int = 0
    linked_insights: int = 0
    created_hypotheses: int = 0
    linked_hypotheses: int = 0
    pending_posts: int = 0
    errors: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, object]:
        return dict(self.__dict__)


def _safe_destination(destination_dir: Path, source: Path, source_hash: str) -> Path:
    destination = destination_dir / source.name
    if destination.exists():
        destination = destination_dir / (
            source.stem + "__" + source_hash[:8] + source.suffix
        )
    return destination


class InboxProcessor:
    def __init__(self, config: AppConfig):
        self.config = config
        self.repository = KnowledgeRepository(config.paths.knowledge)
        self.state = StateManager(config.paths.state)
        self.logger = get_logger(config.paths.logs)

    def _pending_files(self, selected: Optional[Path]) -> List[Path]:
        pending_root = self.config.paths.inbox_pending.resolve()
        if selected is None:
            return sorted(pending_root.glob("*.md"))
        path = selected.expanduser()
        if not path.is_absolute():
            path = self.config.paths.root / path
        path = path.resolve()
        if path.parent != pending_root:
            raise ValueError("selected file must be directly inside inbox/pending")
        if not path.exists() or path.suffix.lower() != ".md":
            raise FileNotFoundError("pending Markdown file not found: %s" % path)
        return [path]

    def validate_only(self, selected: Optional[Path] = None) -> Dict[str, object]:
        reports = []
        for path in self._pending_files(selected):
            try:
                result = parse_research_result(path)
                report = validate_research_result(
                    result, self.config.inbox.supported_schema_versions
                )
                reports.append(
                    {
                        "file": str(path),
                        "valid": report.valid,
                        "errors": report.errors,
                        "warnings": report.warnings,
                    }
                )
            except (OSError, ParseError, UnicodeError) as exc:
                reports.append(
                    {"file": str(path), "valid": False, "errors": [str(exc)], "warnings": []}
                )
        return {"files": reports, "valid": all(item["valid"] for item in reports)}

    def process(self, selected: Optional[Path] = None) -> ProcessSummary:
        summary = ProcessSummary()
        files = self._pending_files(selected)
        summary.detected = len(files)
        self.logger.info("inbox files detected=%d", len(files))
        for path in files:
            self._process_one(path, summary)
        rebuild_topics(self.config.paths.knowledge)
        state_summary = summary.as_dict()
        state_summary["error_count"] = len(summary.errors)
        state_summary.pop("errors", None)
        self.state.record_last_run(state_summary)
        self.logger.info(
            "run complete valid=%d rejected=%d processed=%d revisions=%d insights_created=%d insights_linked=%d hypotheses_created=%d pending_posts=%d errors=%d",
            summary.valid,
            summary.rejected,
            summary.processed,
            summary.revisions,
            summary.created_insights,
            summary.linked_insights,
            summary.created_hypotheses,
            summary.pending_posts,
            len(summary.errors),
        )
        return summary

    def _reject(self, path: Path, source_hash: str, reason: str, summary: ProcessSummary) -> None:
        destination = _safe_destination(
            self.config.paths.inbox_rejected, path, source_hash
        )
        shutil.move(str(path), str(destination))
        self.state.record_inbox(path.name, source_hash, "rejected")
        summary.rejected += 1
        summary.errors.append("%s: %s" % (path.name, reason))
        self.logger.error("rejected file=%s reason=%s", path.name, reason)

    def _archive(self, path: Path, source_hash: str, outcome: str) -> Path:
        destination = _safe_destination(
            self.config.paths.inbox_processed, path, source_hash
        )
        shutil.move(str(path), str(destination))
        self.state.record_inbox(path.name, source_hash, outcome)
        return destination

    def _process_one(self, path: Path, summary: ProcessSummary) -> None:
        source_hash = self.state.file_hash(path)
        try:
            result = parse_research_result(path)
        except (OSError, ParseError, UnicodeError) as exc:
            self._reject(path, source_hash, str(exc), summary)
            return
        report = validate_research_result(
            result, self.config.inbox.supported_schema_versions
        )
        for warning in report.warnings:
            self.logger.warning("file=%s warning=%s", path.name, warning)
        if not report.valid:
            self._reject(path, source_hash, "; ".join(report.errors), summary)
            return
        summary.valid += 1
        existing = self.state.arxiv_record(result.arxiv_id)
        if existing:
            incoming_revision = revision_number(result.arxiv_version)
            current_revision = revision_number(str(existing.get("version", "")))
            if incoming_revision <= current_revision:
                outcome = "skipped_duplicate" if incoming_revision == current_revision else "skipped_stale_revision"
                self._archive(path, source_hash, outcome)
                summary.skipped += 1
                self.logger.info(
                    "paper skipped arxiv_id=%s version=%s outcome=%s",
                    result.arxiv_id,
                    result.arxiv_version,
                    outcome,
                )
                return
            summary.revisions += 1

        preexisting_documents = self.repository.all_documents()
        ambiguous = find_link_candidates(result, preexisting_documents)
        write_candidate_index(
            self.repository.index_dir / "link_candidates.md",
            result.arxiv_id,
            [item for item in ambiguous if item.confidence != "high"],
        )

        links = [item.target for item in ambiguous if item.confidence == "high"]
        for insight in result.insights:
            identifier, created = self.repository.save_insight(
                insight,
                result,
                self.config.knowledge.auto_merge_exact_matches,
            )
            links.append(identifier)
            if created:
                summary.created_insights += 1
            else:
                summary.linked_insights += 1
        for hypothesis in result.hypotheses:
            identifier, created = self.repository.save_hypothesis(
                hypothesis,
                result,
                self.config.knowledge.auto_merge_exact_matches,
            )
            links.append(identifier)
            if created:
                summary.created_hypotheses += 1
            else:
                summary.linked_hypotheses += 1

        self.repository.save_paper(result, links)
        pending_path, post_written = self.repository.save_pending_post(
            result, self.config.technocore.room
        )
        if post_written:
            summary.pending_posts += 1
        self.state.record_arxiv(
            result.arxiv_id,
            {
                "version": result.arxiv_version,
                "processed_at": utc_now(),
                "source_file": path.name,
            },
        )
        self._archive(path, source_hash, "processed")
        summary.processed += 1
        self.logger.info(
            "paper processed arxiv_id=%s version=%s pending_post=%s",
            result.arxiv_id,
            result.arxiv_version,
            pending_path.name,
        )

        if self.config.technocore.auto_publish and post_written:
            passphrase = os.environ.get("TECHNOCORE_IDENTITY_PASSPHRASE")
            if not passphrase:
                message = "auto_publish enabled but TECHNOCORE_IDENTITY_PASSPHRASE is not set"
                summary.errors.append(message)
                self.logger.error(message)
                return
            try:
                client = TechnocoreClient(
                    self.config.technocore.base_url,
                    self.config.technocore.room,
                    self.config.technocore.request_timeout_seconds,
                )
                publisher = Publisher(
                    client,
                    self.state,
                    self.config.technocore.identity_file,
                    self.config.technocore.max_note_chars,
                    self.config.technocore.prohibited_patterns,
                )
                publisher.publish(result.arxiv_id, pending_path, passphrase)
                self.logger.info("Technocore publish succeeded arxiv_id=%s", result.arxiv_id)
            except Exception as exc:
                # Knowledge writes are intentionally retained when publishing fails.
                summary.errors.append("publish failed for %s: %s" % (result.arxiv_id, exc))
                self.logger.error("Technocore publish failed arxiv_id=%s error=%s", result.arxiv_id, exc)
