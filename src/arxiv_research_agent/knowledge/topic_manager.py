"""Rebuild topic pages as deterministic link indexes."""

import re
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Dict, List

import yaml

from arxiv_research_agent.knowledge.repository import dump_markdown, read_markdown


def topic_slug(value: str) -> str:
    value = value.strip().lower().replace("_", " ")
    value = re.sub(r"[^a-z0-9\- ]+", "", value)
    value = re.sub(r"[\s-]+", "-", value).strip("-")
    return value


def topic_title(slug: str) -> str:
    return " ".join(word.upper() if word in {"ai"} else word.title() for word in slug.split("-"))


def rebuild_topics(knowledge_dir: Path) -> List[Path]:
    topics: DefaultDict[str, Dict[str, List[str]]] = defaultdict(
        lambda: {"paper": [], "insight": [], "hypothesis": []}
    )
    for kind, directory in (
        ("paper", knowledge_dir / "papers"),
        ("insight", knowledge_dir / "insights"),
        ("hypothesis", knowledge_dir / "hypotheses"),
    ):
        for path in sorted(directory.glob("*.md")):
            try:
                metadata, _ = read_markdown(path)
            except (ValueError, yaml.YAMLError):
                continue
            identifier = str(metadata.get("id") or metadata.get("arxiv_id") or path.stem)
            for raw_topic in metadata.get("topics", []) or []:
                slug = topic_slug(str(raw_topic))
                if slug and identifier not in topics[slug][kind]:
                    topics[slug][kind].append(identifier)
    topic_dir = knowledge_dir / "topics"
    topic_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for slug, groups in sorted(topics.items()):
        def links(kind: str) -> str:
            return "\n".join("- [[%s]]" % item for item in sorted(groups[kind]))

        body = """# {title}

## Papers

{papers}

## Insights

{insights}

## Hypotheses

{hypotheses}
""".format(
            title=topic_title(slug),
            papers=links("paper"),
            insights=links("insight"),
            hypotheses=links("hypothesis"),
        )
        path = topic_dir / (slug + ".md")
        path.write_text(
            dump_markdown({"type": "topic", "topic": slug}, body), encoding="utf-8"
        )
        written.append(path)
    active_paths = {path.resolve() for path in written}
    for path in topic_dir.glob("*.md"):
        if path.resolve() in active_paths:
            continue
        try:
            metadata, _ = read_markdown(path)
        except (ValueError, yaml.YAMLError):
            continue
        if metadata.get("type") == "topic":
            path.unlink()
    return written
