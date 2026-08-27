from pathlib import Path

import httpx

from arxiv_research_agent.contributions import ContributionManager
from arxiv_research_agent.knowledge.repository import dump_markdown, read_markdown
from arxiv_research_agent.state.manager import StateManager
from arxiv_research_agent.technocore.client import TechnocoreClient
from arxiv_research_agent.technocore.interactions import InteractionManager
from arxiv_research_agent.technocore.monitor import TechnocoreMonitor


DID = "did:key:z6MkfvRrzpX5PH3FQrqVhT7Vq7yzJpxtS8Jz9rd5fPyUVJE9"


class RoomClient(TechnocoreClient):
    def __init__(self, messages):
        super().__init__("https://technocore.invalid", "crypto")
        self.messages = messages

    def read_room(self, since=None, limit=200):
        values = [item for item in self.messages if since is None or item["seq"] > since]
        return {
            "room": "crypto",
            "first_seq": values[0]["seq"] if values else None,
            "last_seq": 43,
            "messages": values,
        }


def prepare_monitor(app_config):
    state = StateManager(app_config.paths.state)
    state.record_arxiv(
        "2608.12345",
        {
            "published_at": "2026-08-27T00:00:00Z",
            "published_note_sha256": "abc",
            "technocore_room": "crypto",
            "technocore_did": DID,
            "technocore_nonce": "123",
        },
    )
    post = app_config.paths.knowledge / "index" / "pending_posts" / "2608.12345.md"
    post.write_text(
        dump_markdown(
            {"type": "technocore_post", "arxiv_id": "2608.12345", "status": "published"},
            "# Technocore Research Note\n\narXiv:2608.12345",
        ),
        encoding="utf-8",
    )
    messages = [
        {
            "seq": 42,
            "ts": "2026-08-27T00:00:00Z",
            "from": DID,
            "text": "Research Note arXiv:2608.12345",
            "nonce": 123,
        },
        {
            "seq": 43,
            "ts": "2026-08-27T00:01:00Z",
            "from": "did:key:z6MkOther",
            "text": "Reply to 42: this is useful",
        },
    ]
    monitor = TechnocoreMonitor(
        RoomClient(messages),
        state,
        app_config.paths.knowledge,
        app_config.paths.inbox_pending.parent,
    )
    return state, monitor


def test_sync_backfills_receipt_and_deduplicates_reaction(app_config):
    state, monitor = prepare_monitor(app_config)
    first = monitor.sync(notify=False)
    assert first["receipts_backfilled"] == 1
    assert len(first["new_reactions"]) == 1
    assert first["new_reactions"][0]["seq"] == 43
    assert state.arxiv_record("2608.12345")["technocore_seq"] == 42
    assert monitor.reaction_path(43).exists()
    metadata, _ = read_markdown(monitor.reaction_path(43))
    assert metadata["trusted"] is False

    second = monitor.sync(notify=False)
    assert second["new_reactions"] == []
    assert second["cursor_gap"] is False


def test_interaction_preview_requires_stored_reaction(app_config):
    state, monitor = prepare_monitor(app_config)
    monitor.sync(notify=False)
    manager = InteractionManager(
        monitor.client,
        state,
        monitor,
        app_config.technocore.identity_file,
        4096,
        [],
    )
    result = manager.preview(43, "Thank you for the evidence.")
    assert result["dry_run"] is True
    assert result["text"].startswith("[Reply to #43]")


def test_contribution_export_writes_markdown_and_json(app_config):
    state, monitor = prepare_monitor(app_config)
    monitor.sync(notify=False)
    paper = app_config.paths.knowledge / "papers" / "2608.12345.md"
    paper.write_text(
        dump_markdown(
            {"type": "paper", "arxiv_id": "2608.12345", "title": "A Paper"},
            "# A Paper",
        ),
        encoding="utf-8",
    )
    result = ContributionManager(app_config.paths.knowledge, state).export("2608.12345")
    assert Path(result["markdown"]).exists()
    assert Path(result["json"]).exists()
    assert "#r/crypto/42" in Path(result["markdown"]).read_text()


def test_read_room_uses_json_shape():
    def handler(request):
        assert request.url.params["format"] == "json"
        assert request.url.params["since"] == "40"
        return httpx.Response(
            200,
            json={"room": "crypto", "last_seq": 41, "messages": []},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = TechnocoreClient(
            "https://technocore.invalid", "crypto", http_client=http_client
        )
        result = client.read_room(since=40, limit=200)
    assert result["last_seq"] == 41
