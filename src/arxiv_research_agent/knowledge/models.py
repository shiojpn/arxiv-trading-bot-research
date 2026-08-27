"""Typed representations of the structured Research Result schema."""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class InsightInput:
    title: str
    statement: str
    why_it_matters: str = ""
    supporting_evidence: str = ""
    confidence: str = "medium"


@dataclass
class HypothesisInput:
    title: str
    statement: str
    mechanism: str = ""
    supporting_evidence: str = ""
    required_data: str = ""
    proposed_test: str = ""


@dataclass
class RelatedCandidate:
    topic: str
    relation: str = "related"


@dataclass
class ResearchResult:
    schema_version: str
    arxiv_id: str
    arxiv_version: str
    title: str
    authors: List[str]
    submitted_at: str
    updated_at: str
    processed_at: str
    relevance_score: int
    topics: List[str]
    source: Dict[str, str]
    paper: Dict[str, str]
    insights: List[InsightInput]
    hypotheses: List[HypothesisInput]
    research_questions: str
    related_candidates: List[RelatedCandidate]
    research_note: str
    raw_frontmatter: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors
