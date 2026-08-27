"""Simple local full-text search over Markdown knowledge."""

from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class SearchMatch:
    path: Path
    line: int
    excerpt: str
    score: int


def search_knowledge(knowledge_dir: Path, query: str) -> List[SearchMatch]:
    terms = [term.casefold() for term in query.split() if term.strip()]
    if not terms:
        return []
    matches = []
    for directory_name in ("papers", "insights", "hypotheses", "topics"):
        directory = knowledge_dir / directory_name
        for path in sorted(directory.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            lowered = text.casefold()
            filename = path.name.casefold()
            score = sum(lowered.count(term) + (3 if term in filename else 0) for term in terms)
            if score <= 0 or not all(term in lowered or term in filename for term in terms):
                continue
            line_number = 1
            excerpt = ""
            for number, line in enumerate(text.splitlines(), start=1):
                if any(term in line.casefold() for term in terms):
                    line_number = number
                    excerpt = line.strip()
                    break
            matches.append(SearchMatch(path, line_number, excerpt[:240], score))
    return sorted(matches, key=lambda item: (-item.score, str(item.path)))
