"""Parser for ChatGPT Task structured Markdown.

Input is treated only as data. No URL, command, or instruction found in the
Markdown is executed.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from arxiv_research_agent.knowledge.models import (
    HypothesisInput,
    InsightInput,
    RelatedCandidate,
    ResearchResult,
)


class ParseError(ValueError):
    """Raised when the Markdown envelope cannot be parsed."""


@dataclass
class Heading:
    level: int
    title: str
    lines: List[str] = field(default_factory=list)
    children: List["Heading"] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()

    def child(self, title: str) -> Optional["Heading"]:
        wanted = normalize_heading(title)
        for item in self.children:
            if normalize_heading(item.title) == wanted:
                return item
        return None


def normalize_heading(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def split_frontmatter(markdown: str) -> Tuple[Dict[str, Any], str]:
    lines = markdown.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ParseError("YAML frontmatter is missing")
    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing = index
            break
    if closing is None:
        raise ParseError("YAML frontmatter is not closed")
    try:
        metadata = yaml.safe_load("\n".join(lines[1:closing])) or {}
    except yaml.YAMLError as exc:
        raise ParseError("Invalid YAML frontmatter: %s" % exc) from exc
    if not isinstance(metadata, dict):
        raise ParseError("YAML frontmatter must be a mapping")
    return metadata, "\n".join(lines[closing + 1 :]).strip()


def parse_headings(body: str) -> Heading:
    root = Heading(level=0, title="")
    stack = [root]
    for line in body.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            stack[-1].lines.append(line)
            continue
        level = len(match.group(1))
        node = Heading(level=level, title=match.group(2).strip())
        while stack[-1].level >= level:
            stack.pop()
        stack[-1].children.append(node)
        stack.append(node)
    return root


def _string(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _list_of_strings(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_string(item) for item in value]
    return [_string(value)]


def _child_text(parent: Optional[Heading], title: str) -> str:
    if parent is None:
        return ""
    child = parent.child(title)
    return child.text if child else ""


def _statement_title(statement: str, fallback: str) -> str:
    for line in statement.splitlines():
        candidate = re.sub(r"^[-*]\s+", "", line).strip()
        if candidate:
            return candidate[:160]
    return fallback


def _parse_related(text: str) -> List[RelatedCandidate]:
    if not text.strip():
        return []
    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError:
        return []
    if not isinstance(value, list):
        return []
    results = []
    for item in value:
        if isinstance(item, dict) and item.get("topic"):
            results.append(
                RelatedCandidate(
                    topic=str(item["topic"]).strip(),
                    relation=str(item.get("relation", "related")).strip(),
                )
            )
    return results


def parse_research_result_text(markdown: str) -> ResearchResult:
    metadata, body = split_frontmatter(markdown)
    root = parse_headings(body)
    paper_node = root.child("Paper")
    insights_node = root.child("Insights")
    hypotheses_node = root.child("Hypotheses")

    paper_fields = [
        "One-line Summary",
        "Research Question",
        "Data",
        "Methodology",
        "Main Findings",
        "Evidence",
        "Limitations",
        "Interpretation",
        "Potential Applications",
    ]
    paper = {name: _child_text(paper_node, name) for name in paper_fields}

    insights = []
    if insights_node:
        for index, node in enumerate(insights_node.children, start=1):
            statement = _child_text(node, "Statement")
            insights.append(
                InsightInput(
                    title=_statement_title(statement, "Insight %d" % index),
                    statement=statement,
                    why_it_matters=_child_text(node, "Why It Matters"),
                    supporting_evidence=_child_text(node, "Supporting Evidence"),
                    confidence=_child_text(node, "Confidence").strip().lower()
                    or "medium",
                )
            )

    hypotheses = []
    if hypotheses_node:
        for index, node in enumerate(hypotheses_node.children, start=1):
            statement = _child_text(node, "Statement")
            hypotheses.append(
                HypothesisInput(
                    title=_statement_title(statement, "Hypothesis %d" % index),
                    statement=statement,
                    mechanism=_child_text(node, "Mechanism"),
                    supporting_evidence=_child_text(node, "Supporting Evidence"),
                    required_data=_child_text(node, "Required Data"),
                    proposed_test=_child_text(node, "Proposed Test"),
                )
            )

    questions_node = root.child("Research Questions Generated")
    related_node = root.child("Related Knowledge Candidates")
    note_node = root.child("Technocore Research Note")
    source = metadata.get("source") if isinstance(metadata.get("source"), dict) else {}

    try:
        relevance_score = int(metadata.get("relevance_score", 0))
    except (TypeError, ValueError):
        relevance_score = -1

    return ResearchResult(
        schema_version=_string(metadata.get("schema_version")),
        arxiv_id=_string(metadata.get("arxiv_id")),
        arxiv_version=_string(metadata.get("arxiv_version")),
        title=_string(metadata.get("title")),
        authors=_list_of_strings(metadata.get("authors")),
        submitted_at=_string(metadata.get("submitted_at")),
        updated_at=_string(metadata.get("updated_at")),
        processed_at=_string(metadata.get("processed_at")),
        relevance_score=relevance_score,
        topics=_list_of_strings(metadata.get("topics")),
        source={str(key): _string(value) for key, value in source.items()},
        paper=paper,
        insights=insights,
        hypotheses=hypotheses,
        research_questions=questions_node.text if questions_node else "",
        related_candidates=_parse_related(related_node.text if related_node else ""),
        research_note=note_node.text if note_node else "",
        raw_frontmatter=metadata,
    )


def parse_research_result(path: Path) -> ResearchResult:
    return parse_research_result_text(path.read_text(encoding="utf-8"))
