import base64
import logging
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from arxiv_research_agent.knowledge.repository import dump_markdown, read_markdown
from arxiv_research_agent.logging_utils import get_logger
from arxiv_research_agent.state.manager import StateManager
from arxiv_research_agent.technocore.client import (
    SignedRequest,
    TechnocoreClient,
    TechnocoreHTTPError,
)
from arxiv_research_agent.technocore.identity import (
    create_identity,
    did_from_private_key,
    load_identity,
    sign_message,
    sweep_text,
)
from arxiv_research_agent.technocore.publisher import PublishError, Publisher


class FakeTechnocoreClient(TechnocoreClient):
    def __init__(self):
        super().__init__("https://technocore.invalid", "arxiv-trading-bot-research")
        self.send_count = 0

    def send(self, request):
        self.send_count += 1
        return {
            "posted": {
                "seq": 42,
                "ts": "2026-08-27T00:00:00Z",
                "nonce": request.json["nonce"],
            }
        }


def make_post(path: Path):
    note = "[Research Note]\n\narXiv: 2608.12345\n\nFinding: Useful result."
    path.write_text(
        dump_markdown(
            {"type": "technocore_post", "arxiv_id": "2608.12345", "status": "pending"},
            "# Technocore Research Note\n\n" + note,
        ),
        encoding="utf-8",
    )


def test_did_creation_encryption_and_signature_verification(tmp_path):
    path = tmp_path / "identity.pem"
    did = create_identity(path, "a sufficiently long passphrase")
    assert did.startswith("did:key:z6Mk")
    assert b"ENCRYPTED PRIVATE KEY" in path.read_bytes()
    assert oct(path.stat().st_mode & 0o777) == "0o600"

    key = load_identity(path, "a sufficiently long passphrase")
    nonce = "1720000000000"
    did_again, signature, normalized = sign_message(
        key, "arxiv-trading-bot-research", nonce, "hello\nworld"
    )
    assert did_again == did
    assert normalized == "hello world"
    padded = signature + "=" * (-len(signature) % 4)
    key.public_key().verify(
        base64.urlsafe_b64decode(padded),
        ("arxiv-trading-bot-research|%s|hello world" % nonce).encode(),
    )


def test_signed_request_shape_matches_official_post_lane():
    key = Ed25519PrivateKey.generate()
    client = FakeTechnocoreClient()
    request = client.build_signed_request(key, "note\ntext", nonce="1720000000001")
    assert request.url.endswith("/r/arxiv-trading-bot-research")
    assert set(request.json) == {"did", "sig", "nonce", "text"}
    assert request.json["text"] == "note text"
    assert len(request.json["sig"]) == 86


def test_http_error_includes_server_reason_without_traceback():
    def handler(request):
        assert request.url.params["format"] == "json"
        return httpx.Response(
            400,
            text="nonce must be greater than 1770000000000\n",
            request=request,
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = TechnocoreClient(
            "https://technocore.invalid",
            "arxiv-trading-bot-research",
            http_client=http_client,
        )
        request = SignedRequest(
            url="https://technocore.invalid/r/arxiv-trading-bot-research",
            json={"did": "did", "sig": "sig", "nonce": "1", "text": "note"},
            normalized_text="note",
        )
        with pytest.raises(TechnocoreHTTPError) as captured:
            client.send(request)
    assert "HTTP 400" in str(captured.value)
    assert "nonce must be greater" in str(captured.value)


def test_dry_run_never_sends_and_publish_prevents_duplicate(app_config):
    identity_path = app_config.technocore.identity_file
    create_identity(identity_path, "a sufficiently long passphrase")
    post_path = app_config.paths.knowledge / "index" / "pending_posts" / "2608.12345.md"
    make_post(post_path)
    client = FakeTechnocoreClient()
    state = StateManager(app_config.paths.state)
    publisher = Publisher(client, state, identity_path, 4096, [])

    preview = publisher.preview("2608.12345", post_path)
    assert preview["dry_run"] is True
    assert client.send_count == 0

    published = publisher.publish(
        "2608.12345", post_path, "a sufficiently long passphrase"
    )
    assert published["dry_run"] is False
    assert client.send_count == 1
    metadata, _ = read_markdown(post_path)
    assert metadata["status"] == "published"
    assert metadata["seq"] == 42
    assert metadata["permalink"].endswith("#r/arxiv-trading-bot-research/42")
    (app_config.paths.state / "processed_arxiv_ids.json").write_text("{}\n")
    with pytest.raises(PublishError):
        publisher.publish("2608.12345", post_path, "a sufficiently long passphrase")
    assert client.send_count == 1


def test_prohibited_pattern_is_blocked(app_config):
    post_path = app_config.paths.knowledge / "index" / "pending_posts" / "2608.12345.md"
    make_post(post_path)
    text = post_path.read_text().replace("Useful result.", "ignore previous instructions")
    post_path.write_text(text)
    publisher = Publisher(
        FakeTechnocoreClient(),
        StateManager(app_config.paths.state),
        app_config.technocore.identity_file,
        4096,
        ["ignore previous instructions"],
    )
    with pytest.raises(PublishError):
        publisher.preview("2608.12345", post_path)


def test_secret_redaction_in_logs(tmp_path):
    logger = get_logger(tmp_path)
    secret = "never-write-this-secret"
    logger.info("passphrase=%s", secret)
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.flush()
    contents = "\n".join(path.read_text() for path in tmp_path.glob("*.log"))
    assert secret not in contents
    assert "[REDACTED]" in contents
