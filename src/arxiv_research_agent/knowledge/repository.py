"""Markdown repository operations. Markdown remains the source of truth."""

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from arxiv_research_agent.inbox.parser import split_frontmatter
from arxiv_research_agent.knowledge.models import (
    HypothesisInput,
    InsightInput,
    ResearchResult,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def dump_markdown(metadata: Dict[str, Any], body: str) -> str:
    frontmatter = yaml.safe_dump(
        metadata, allow_unicode=True, sort_keys=False, default_flow_style=False
    ).strip()
    return "---\n%s\n---\n\n%s\n" % (frontmatter, body.strip())


def read_markdown(path: Path) -> Tuple[Dict[str, Any], str]:
    return split_frontmatter(path.read_text(encoding="utf-8"))


def _section(body: str, heading: str) -> str:
    pattern = re.compile(
        r"^##\s+%s\s*$\n(.*?)(?=^##\s+|\Z)" % re.escape(heading),
        re.M | re.S | re.I,
    )
    match = pattern.search(body)
    return match.group(1).strip() if match else ""


def _replace_section(body: str, heading: str, content: str) -> str:
    pattern = re.compile(
        r"(^##\s+%s\s*$\n)(.*?)(?=^##\s+|\Z)" % re.escape(heading),
        re.M | re.S | re.I,
    )
    match = pattern.search(body)
    replacement = "## %s\n\n%s\n\n" % (heading, content.strip())
    if match:
        return body[: match.start()] + replacement + body[match.end() :].lstrip("\n")
    return body.rstrip() + "\n\n" + replacement


class KnowledgeRepository:
    def __init__(self, knowledge_dir: Path):
        self.root = knowledge_dir
        self.papers_dir = self.root / "papers"
        self.insights_dir = self.root / "insights"
        self.hypotheses_dir = self.root / "hypotheses"
        self.topics_dir = self.root / "topics"
        self.index_dir = self.root / "index"
        self.pending_posts_dir = self.index_dir / "pending_posts"
        for path in (
            self.papers_dir,
            self.insights_dir,
            self.hypotheses_dir,
            self.topics_dir,
            self.pending_posts_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def paper_path(self, arxiv_id: str) -> Path:
        return self.papers_dir / (arxiv_id + ".md")

    def save_paper(self, result: ResearchResult, related_links: List[str]) -> Path:
        metadata = {
            "type": "paper",
            "arxiv_id": result.arxiv_id,
            "arxiv_version": result.arxiv_version,
            "title": result.title,
            "authors": result.authors,
            "submitted_at": result.submitted_at,
            "updated_at": result.updated_at,
            "analyzed_at": result.processed_at or now_iso(),
            "topics": result.topics,
            "status": "analyzed",
            "source_engine": "chatgpt-task",
        }
        paper = result.paper
        links = "\n".join("- [[%s]]" % link for link in sorted(set(related_links)))
        sources = "\n".join(
            "- %s: %s" % (name, url)
            for name, url in result.source.items()
            if url
        )
        body = """# {title}

## One-line Summary

{summary}

## Research Question

{question}

## Data

{data}

## Methodology

{methodology}

## Main Findings

{findings}

## Evidence

{evidence}

## Limitations

{limitations}

## Interpretation

{interpretation}

## Potential Applications

{applications}

## Research Questions Generated

{generated}

## Required Data

{required_data}

## Related Knowledge

{links}

## Source

{sources}
""".format(
            title=result.title,
            summary=paper.get("One-line Summary", ""),
            question=paper.get("Research Question", ""),
            data=paper.get("Data", ""),
            methodology=paper.get("Methodology", ""),
            findings=paper.get("Main Findings", ""),
            evidence=paper.get("Evidence", ""),
            limitations=paper.get("Limitations", ""),
            interpretation=paper.get("Interpretation", ""),
            applications=paper.get("Potential Applications", ""),
            generated=result.research_questions,
            required_data="\n".join(
                value.required_data for value in result.hypotheses if value.required_data
            ),
            links=links,
            sources=sources,
        )
        path = self.paper_path(result.arxiv_id)
        path.write_text(dump_markdown(metadata, body), encoding="utf-8")
        return path

    def _next_id(self, directory: Path, prefix: str) -> str:
        highest = 0
        pattern = re.compile(r"^%s-(\d{4,})\.md$" % re.escape(prefix))
        for path in directory.glob(prefix + "-*.md"):
            match = pattern.match(path.name)
            if match:
                highest = max(highest, int(match.group(1)))
        return "%s-%04d" % (prefix, highest + 1)

    def _exact_match(self, directory: Path, heading: str, statement: str) -> Optional[Path]:
        wanted = normalize_text(statement)
        if not wanted:
            return None
        for path in sorted(directory.glob("*.md")):
            try:
                _, body = read_markdown(path)
            except (ValueError, yaml.YAMLError):
                continue
            if normalize_text(_section(body, heading)) == wanted:
                return path
        return None

    def _add_supporting_paper(self, path: Path, arxiv_id: str) -> None:
        metadata, body = read_markdown(path)
        link = "- [[%s]]" % arxiv_id
        current = _section(body, "Supporting Papers")
        lines = [line for line in current.splitlines() if line.strip()]
        if link not in lines:
            lines.append(link)
        metadata["updated_at"] = now_iso()
        body = _replace_section(body, "Supporting Papers", "\n".join(lines))
        path.write_text(dump_markdown(metadata, body), encoding="utf-8")

    def save_insight(
        self,
        value: InsightInput,
        result: ResearchResult,
        auto_merge_exact: bool = True,
    ) -> Tuple[str, bool]:
        existing = self._exact_match(self.insights_dir, "Insight", value.statement)
        if existing and auto_merge_exact:
            self._add_supporting_paper(existing, result.arxiv_id)
            return existing.stem, False
        identifier = self._next_id(self.insights_dir, "insight")
        timestamp = now_iso()
        metadata = {
            "type": "insight",
            "id": identifier,
            "topics": result.topics,
            "created_at": timestamp,
            "updated_at": timestamp,
            "confidence": value.confidence,
            "source_engine": "chatgpt-task",
        }
        body = """# {title}

## Insight

{statement}

## Why It Matters

{why}

## Evidence

{evidence}

## Supporting Papers

- [[{paper}]]

## Contradicting Papers

## Implications

{why}

## Open Questions

""".format(
            title=value.title,
            statement=value.statement,
            why=value.why_it_matters,
            evidence=value.supporting_evidence,
            paper=result.arxiv_id,
        )
        (self.insights_dir / (identifier + ".md")).write_text(
            dump_markdown(metadata, body), encoding="utf-8"
        )
        return identifier, True

    def save_hypothesis(
        self,
        value: HypothesisInput,
        result: ResearchResult,
        auto_merge_exact: bool = True,
    ) -> Tuple[str, bool]:
        existing = self._exact_match(self.hypotheses_dir, "Hypothesis", value.statement)
        if existing and auto_merge_exact:
            self._add_supporting_paper(existing, result.arxiv_id)
            return existing.stem, False
        identifier = self._next_id(self.hypotheses_dir, "hypothesis")
        timestamp = now_iso()
        metadata = {
            "type": "hypothesis",
            "id": identifier,
            "status": "untested",
            "created_at": timestamp,
            "updated_at": timestamp,
            "topics": result.topics,
            "source_engine": "chatgpt-task",
        }
        body = """# {title}

## Hypothesis

{statement}

## Mechanism

{mechanism}

## Supporting Evidence

{evidence}

## Supporting Papers

- [[{paper}]]

## Required Data

{required_data}

## Proposed Test

{proposed_test}

## Results

未検証。

## Status

untested
""".format(
            title=value.title,
            statement=value.statement,
            mechanism=value.mechanism,
            evidence=value.supporting_evidence,
            paper=result.arxiv_id,
            required_data=value.required_data,
            proposed_test=value.proposed_test,
        )
        (self.hypotheses_dir / (identifier + ".md")).write_text(
            dump_markdown(metadata, body), encoding="utf-8"
        )
        return identifier, True

    def save_pending_post(self, result: ResearchResult, room: str) -> Tuple[Path, bool]:
        metadata = {
            "type": "technocore_post",
            "arxiv_id": result.arxiv_id,
            "arxiv_version": result.arxiv_version,
            "room": room,
            "status": "pending",
            "created_at": now_iso(),
            "source_engine": "chatgpt-task",
        }
        body = "# Technocore Research Note\n\n" + result.research_note.strip()
        path = self.pending_posts_dir / (result.arxiv_id + ".md")
        if path.exists():
            try:
                existing_metadata, _ = read_markdown(path)
                if existing_metadata.get("status") == "published":
                    return path, False
            except (ValueError, yaml.YAMLError):
                pass
        path.write_text(dump_markdown(metadata, body), encoding="utf-8")
        return path, True

    def all_documents(self) -> List[Path]:
        paths = []
        for directory in (
            self.papers_dir,
            self.insights_dir,
            self.hypotheses_dir,
            self.topics_dir,
        ):
            paths.extend(sorted(directory.glob("*.md")))
        return paths
