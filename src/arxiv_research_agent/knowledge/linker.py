"""Deterministic knowledge candidate discovery without semantic inference."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set

import yaml

from arxiv_research_agent.knowledge.models import ResearchResult
from arxiv_research_agent.knowledge.repository import normalize_text, read_markdown


@dataclass(frozen=True)
class LinkCandidate:
    target: str
    relation: str
    reason: str
    confidence: str


def _title(body: str) -> str:
    match = re.search(r"^#\s+(.+)$", body, re.M)
    return match.group(1).strip() if match else ""


def find_link_candidates(
    result: ResearchResult, document_paths: List[Path]
) -> List[LinkCandidate]:
    requested = {
        normalize_text(item.topic): item.relation for item in result.related_candidates
    }
    result_topics = {normalize_text(topic) for topic in result.topics}
    current_text = "\n".join(
        list(result.paper.values())
        + [item.statement for item in result.insights]
        + [item.statement for item in result.hypotheses]
        + [result.research_questions]
        + [item.topic for item in result.related_candidates]
    )
    normalized_current = normalize_text(current_text)
    candidates = []
    seen: Set[str] = set()
    for path in document_paths:
        if path.stem == result.arxiv_id:
            continue
        try:
            metadata, body = read_markdown(path)
        except (ValueError, yaml.YAMLError):
            continue
        target = str(metadata.get("id") or metadata.get("arxiv_id") or path.stem)
        if target in seen:
            continue
        doc_topics = {
            normalize_text(str(topic)) for topic in metadata.get("topics", []) or []
        }
        heading = normalize_text(_title(body))
        explicit_link = "[[%s]]" % target in current_text
        exact_identifier = bool(
            re.search(
                r"(?<![A-Za-z0-9_.-])%s(?![A-Za-z0-9_.-])" % re.escape(target),
                current_text,
            )
        )
        exact_title = bool(heading and len(heading) >= 8 and heading in normalized_current)
        if (
            explicit_link
            or exact_identifier
            or normalize_text(target) in requested
            or heading in requested
            or exact_title
        ):
            relation = requested.get(normalize_text(target), requested.get(heading, "related"))
            if explicit_link:
                reason = "wikilink"
            elif exact_identifier or normalize_text(target) in requested:
                reason = "exact identifier"
            elif exact_title or heading in requested:
                reason = "normalized title"
            else:
                reason = "explicit candidate"
            candidates.append(LinkCandidate(target, relation, reason, "high"))
            seen.add(target)
            continue
        requested_topics = set(requested)
        overlap = doc_topics & (result_topics | requested_topics)
        if overlap:
            relation = "related"
            for topic in sorted(overlap):
                if topic in requested:
                    relation = requested[topic]
                    break
            candidates.append(
                LinkCandidate(
                    target=target,
                    relation=relation,
                    reason="topic match: %s" % ", ".join(sorted(overlap)),
                    confidence="low",
                )
            )
            seen.add(target)
            continue
        normalized_body = normalize_text(body).replace("-", " ")
        keyword_matches = []
        for topic in requested_topics:
            keyword = topic.replace("-", " ")
            if keyword and re.search(
                r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(keyword),
                normalized_body,
            ):
                keyword_matches.append(topic)
        if keyword_matches:
            first = sorted(keyword_matches)[0]
            candidates.append(
                LinkCandidate(
                    target=target,
                    relation=requested.get(first, "related"),
                    reason="exact keyword: %s" % ", ".join(sorted(keyword_matches)),
                    confidence="low",
                )
            )
            seen.add(target)
    return candidates


def write_candidate_index(
    index_path: Path, arxiv_id: str, candidates: List[LinkCandidate]
) -> None:
    if not candidates:
        return
    existing = index_path.read_text(encoding="utf-8") if index_path.exists() else "# Link Candidates\n"
    marker = "## [[%s]]" % arxiv_id
    block_lines = [marker, ""]
    for item in candidates:
        block_lines.append(
            "- [[%s]] — %s; %s; confidence: %s"
            % (item.target, item.relation, item.reason, item.confidence)
        )
    block = "\n".join(block_lines).rstrip() + "\n"
    pattern = re.compile(
        r"^##\s+\[\[%s\]\].*?(?=^##\s+|\Z)" % re.escape(arxiv_id),
        re.M | re.S,
    )
    if pattern.search(existing):
        updated = pattern.sub(block, existing)
    else:
        updated = existing.rstrip() + "\n\n" + block
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(updated.rstrip() + "\n", encoding="utf-8")
