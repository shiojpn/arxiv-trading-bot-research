import json
from pathlib import Path

from arxiv_research_agent.inbox.processor import InboxProcessor
from arxiv_research_agent.inbox.parser import parse_research_result_text
from arxiv_research_agent.knowledge.linker import find_link_candidates
from arxiv_research_agent.knowledge.repository import dump_markdown, read_markdown
from arxiv_research_agent.knowledge.search import search_knowledge
from arxiv_research_agent.knowledge.topic_manager import rebuild_topics

from conftest import RESEARCH_RESULT


def test_process_generates_knowledge_state_topics_and_moves(app_config, research_file):
    summary = InboxProcessor(app_config).process()
    assert summary.processed == 1
    assert summary.created_insights == 1
    assert summary.created_hypotheses == 1
    assert not research_file.exists()
    assert (app_config.paths.inbox_processed / research_file.name).exists()

    paper = app_config.paths.knowledge / "papers" / "2608.12345.md"
    assert paper.exists()
    metadata, body = read_markdown(paper)
    assert metadata["source_engine"] == "chatgpt-task"
    assert "## Evidence" in body
    assert "[[insight-0001]]" in body
    assert (app_config.paths.knowledge / "topics" / "price-discovery.md").exists()
    assert (app_config.paths.knowledge / "index" / "pending_posts" / "2608.12345.md").exists()

    state = json.loads((app_config.paths.state / "processed_arxiv_ids.json").read_text())
    assert state["2608.12345"]["version"] == "v1"
    last_run = json.loads((app_config.paths.state / "last_run.json").read_text())
    assert last_run["processed"] == 1


def test_invalid_file_is_rejected(app_config):
    path = app_config.paths.inbox_pending / "bad.md"
    path.write_text("not frontmatter", encoding="utf-8")
    summary = InboxProcessor(app_config).process()
    assert summary.rejected == 1
    assert not path.exists()
    assert (app_config.paths.inbox_rejected / "bad.md").exists()


def test_duplicate_revision_is_skipped_and_archived(app_config, research_file):
    processor = InboxProcessor(app_config)
    processor.process()
    duplicate = app_config.paths.inbox_pending / "duplicate.md"
    duplicate.write_text(RESEARCH_RESULT, encoding="utf-8")
    summary = processor.process()
    assert summary.skipped == 1
    assert summary.processed == 0
    assert (app_config.paths.inbox_processed / "duplicate.md").exists()
    assert len(list((app_config.paths.knowledge / "insights").glob("insight-*.md"))) == 1


def test_revision_updates_paper_without_duplicate_insight(app_config, research_file):
    processor = InboxProcessor(app_config)
    processor.process()
    revision = RESEARCH_RESULT.replace('arxiv_version: "v1"', 'arxiv_version: "v2"')
    revision = revision.replace(
        'title: "Price Discovery Across Crypto Venues"',
        'title: "Price Discovery Across Crypto Venues Revised"',
    )
    path = app_config.paths.inbox_pending / "revision.md"
    path.write_text(revision, encoding="utf-8")
    summary = processor.process()
    assert summary.revisions == 1
    metadata, _ = read_markdown(app_config.paths.knowledge / "papers" / "2608.12345.md")
    assert metadata["arxiv_version"] == "v2"
    assert len(list((app_config.paths.knowledge / "insights").glob("insight-*.md"))) == 1


def test_exact_insight_links_second_supporting_paper_and_candidates(app_config, research_file):
    processor = InboxProcessor(app_config)
    processor.process()
    second = RESEARCH_RESULT.replace("2608.12345", "2608.54321")
    second = second.replace(
        'title: "Price Discovery Across Crypto Venues"',
        'title: "A Second Price Discovery Study"',
    )
    path = app_config.paths.inbox_pending / "second.md"
    path.write_text(second, encoding="utf-8")
    summary = processor.process()
    assert summary.linked_insights == 1
    insight = (app_config.paths.knowledge / "insights" / "insight-0001.md").read_text()
    assert "[[2608.12345]]" in insight
    assert "[[2608.54321]]" in insight
    second_paper = app_config.paths.knowledge / "papers" / "2608.54321.md"
    assert "[[2608.12345]]" in second_paper.read_text()


def test_search_covers_markdown_body(app_config, research_file):
    InboxProcessor(app_config).process()
    matches = search_knowledge(app_config.paths.knowledge, "oracle lag")
    assert any("hypothesis" in str(item.path) for item in matches)


def test_validate_only_does_not_move(app_config, research_file):
    report = InboxProcessor(app_config).validate_only()
    assert report["valid"] is True
    assert research_file.exists()


def test_exact_body_keyword_creates_low_confidence_candidate(app_config):
    path = app_config.paths.knowledge / "insights" / "insight-0042.md"
    path.write_text(
        dump_markdown(
            {"type": "insight", "id": "insight-0042", "topics": ["feeds"]},
            "# Feed Update Timing\n\n## Insight\n\nAn oracle can update slowly.",
        ),
        encoding="utf-8",
    )
    result = parse_research_result_text(RESEARCH_RESULT)
    candidates = find_link_candidates(result, [path])
    assert candidates[0].target == "insight-0042"
    assert candidates[0].confidence == "low"
    assert candidates[0].reason.startswith("exact keyword")


def test_rebuild_topics_removes_stale_generated_index(app_config):
    stale = app_config.paths.knowledge / "topics" / "stale-topic.md"
    stale.write_text(
        dump_markdown({"type": "topic", "topic": "stale-topic"}, "# Stale Topic"),
        encoding="utf-8",
    )
    rebuild_topics(app_config.paths.knowledge)
    assert not stale.exists()
