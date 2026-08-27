"""Structural and consistency validation for untrusted Research Results."""

import re
from datetime import date, datetime
from typing import Iterable
from urllib.parse import urlparse

from arxiv_research_agent.knowledge.models import ResearchResult, ValidationResult


ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}$")
VERSION_RE = re.compile(r"^v([1-9]\d*)$")
VALID_CONFIDENCE = {"low", "medium", "high"}
TOPIC_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _valid_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def _valid_timestamp_with_timezone(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None
    except (TypeError, ValueError):
        return False


def validate_research_result(
    result: ResearchResult, supported_versions: Iterable[str]
) -> ValidationResult:
    report = ValidationResult()
    if result.raw_frontmatter.get("type") != "research_result":
        report.errors.append("type must be research_result")
    if result.schema_version not in set(supported_versions):
        report.errors.append("unsupported schema_version: %s" % result.schema_version)
    if not ARXIV_ID_RE.fullmatch(result.arxiv_id):
        report.errors.append("invalid or missing arxiv_id")
    if not VERSION_RE.fullmatch(result.arxiv_version):
        report.errors.append("invalid or missing arxiv_version")
    if not result.title.strip():
        report.errors.append("title is required")
    if not result.authors:
        report.errors.append("authors are required")
    if not _valid_date(result.submitted_at):
        report.errors.append("submitted_at must be an ISO 8601 date")
    if not _valid_date(result.updated_at):
        report.errors.append("updated_at must be an ISO 8601 date")
    if not _valid_timestamp_with_timezone(result.processed_at):
        report.errors.append("processed_at must be an ISO 8601 timestamp with timezone")
    if not 0 <= result.relevance_score <= 100:
        report.errors.append("relevance_score must be between 0 and 100")
    arxiv_url = result.source.get("arxiv", "")
    if not _valid_http_url(arxiv_url):
        report.errors.append("source.arxiv must be an HTTP(S) URL")
    elif result.arxiv_id and result.arxiv_id not in arxiv_url:
        report.errors.append("source.arxiv must contain the arXiv ID")
    if not any(
        _valid_http_url(result.source.get(name, "")) for name in ("pdf", "html")
    ):
        report.errors.append("source.pdf or source.html must be an HTTP(S) URL")
    for name in ("pdf", "html"):
        value = result.source.get(name, "")
        if value and _valid_http_url(value) and result.arxiv_id not in value:
            report.errors.append("source.%s must contain the arXiv ID" % name)
    if not result.topics:
        report.errors.append("at least one topic is required")
    for topic in result.topics:
        if not TOPIC_RE.fullmatch(topic):
            report.errors.append("topic must be lowercase kebab-case: %s" % topic)
    if not any(value.strip() for value in result.paper.values()):
        report.errors.append("Paper section is required")
    if not result.paper.get("Evidence", "").strip():
        report.errors.append("Paper/Evidence section is required")
    if not result.insights and not result.hypotheses:
        report.errors.append("at least one parseable Insight or Hypothesis is required")
    for index, insight in enumerate(result.insights, start=1):
        if not insight.statement.strip():
            report.errors.append("Insight %d/Statement is required" % index)
        if insight.confidence not in VALID_CONFIDENCE:
            report.warnings.append(
                "Insight %d has unknown confidence; normalized to medium" % index
            )
            insight.confidence = "medium"
        if not insight.supporting_evidence.strip():
            report.warnings.append("Insight %d has no Supporting Evidence" % index)
    for index, hypothesis in enumerate(result.hypotheses, start=1):
        if not hypothesis.statement.strip():
            report.errors.append("Hypothesis %d/Statement is required" % index)
        if not hypothesis.supporting_evidence.strip():
            report.warnings.append("Hypothesis %d has no Supporting Evidence" % index)
    if not result.research_note.strip():
        report.errors.append("Technocore Research Note is required")
    elif result.arxiv_id not in result.research_note:
        report.errors.append("Technocore Research Note must contain the arXiv ID")
    return report


def revision_number(version: str) -> int:
    match = VERSION_RE.fullmatch(version)
    return int(match.group(1)) if match else -1
