from pathlib import Path

import pytest
import yaml

from arxiv_research_agent.config import load_config


RESEARCH_RESULT = """---
schema_version: "1.0"
type: research_result
arxiv_id: "2608.12345"
arxiv_version: "v1"
title: "Price Discovery Across Crypto Venues"
authors:
  - "Alice Researcher"
  - "Bob Scholar"
submitted_at: "2026-08-26"
updated_at: "2026-08-26"
processed_at: "2026-08-27T07:00:00+09:00"
relevance_score: 88
topics:
  - price-discovery
  - market-microstructure
source:
  arxiv: "https://arxiv.org/abs/2608.12345"
  pdf: "https://arxiv.org/pdf/2608.12345"
  html: "https://arxiv.org/html/2608.12345"
---

# Paper

## One-line Summary

This paper studies price discovery across crypto venues.

## Research Question

Which venue incorporates information first?

## Data

Trades and quotes from two venues.

## Methodology

Information share analysis.

## Main Findings

Venue A leads during volatile periods.

## Evidence

- The estimated information share of Venue A is 0.71 in the reported sample.

## Limitations

The sample covers one month.

## Interpretation

The lead may depend on participant composition.

## Potential Applications

Routing and oracle design.

# Insights

## Insight 1

### Statement

Cross-venue agreement does not imply independent price discovery.

### Why It Matters

Correlated feeds may share the same upstream source.

### Supporting Evidence

- Venue A leads in the reported information-share estimates.

### Confidence

medium

# Hypotheses

## Hypothesis 1

### Statement

Oracle lag increases around the US equity market open.

### Mechanism

Underlying volatility rises faster than oracle update frequency.

### Supporting Evidence

- The paper reports time-varying venue leadership.

### Required Data

- Oracle and spot prices with millisecond timestamps.

### Proposed Test

Compare lag distributions around the market open.

# Research Questions Generated

- Does the dependency change around market open?

# Related Knowledge Candidates

- topic: oracle
  relation: extends
- topic: price-discovery
  relation: supports

# Technocore Research Note

[Research Note]

Paper:
Price Discovery Across Crypto Venues

arXiv:
2608.12345

Finding:
Cross-venue agreement does not necessarily imply independent price discovery.

Potential implication:
Oracle feeds may be mechanically dependent.

Research question:
Does dependency change around the US market open?
"""


@pytest.fixture
def app_config(tmp_path: Path):
    raw = {
        "inbox": {"supported_schema_versions": ["1.0"]},
        "knowledge": {"auto_merge_exact_matches": True},
        "technocore": {
            "base_url": "https://technocore.invalid",
            "room": "arxiv-trading-bot-research",
            "auto_publish": False,
            "identity_file": "identities/identity.pem",
            "max_note_chars": 4096,
            "request_timeout_seconds": 1,
            "prohibited_patterns": ["ignore previous instructions", "rm\\s+-rf"],
        },
    }
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(raw, sort_keys=False), encoding="utf-8"
    )
    for relative in (
        "inbox/pending",
        "inbox/processed",
        "inbox/rejected",
        "knowledge/papers",
        "knowledge/insights",
        "knowledge/hypotheses",
        "knowledge/topics",
        "knowledge/index/pending_posts",
        "state",
        "identities",
        "logs",
    ):
        (tmp_path / relative).mkdir(parents=True, exist_ok=True)
    return load_config(tmp_path / "config.yaml")


@pytest.fixture
def research_file(app_config):
    path = app_config.paths.inbox_pending / "2026-08-27_2608.12345.md"
    path.write_text(RESEARCH_RESULT, encoding="utf-8")
    return path
