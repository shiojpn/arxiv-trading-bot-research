"""Research Note validation, preview, duplicate prevention, and publishing."""

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from arxiv_research_agent.knowledge.repository import dump_markdown, read_markdown
from arxiv_research_agent.state.manager import StateManager, utc_now
from arxiv_research_agent.technocore.client import TechnocoreClient
from arxiv_research_agent.technocore.identity import load_identity, sweep_text


class PublishError(ValueError):
    pass


def note_hash(note: str) -> str:
    return hashlib.sha256(note.encode("utf-8")).hexdigest()


def extract_note(path: Path) -> str:
    _, body = read_markdown(path)
    match = re.search(r"^#\s+Technocore Research Note\s*$\n(.*)\Z", body, re.M | re.S)
    return match.group(1).strip() if match else body.strip()


def extract_receipt(response: Dict[str, Any], request: Any) -> Dict[str, Any]:
    candidates: List[Dict[str, Any]] = []
    for key in ("posted", "message"):
        value = response.get(key)
        if isinstance(value, dict):
            candidates.append(value)
    messages = response.get("messages", [])
    if isinstance(messages, list):
        candidates.extend(value for value in messages if isinstance(value, dict))
    nonce = str(request.json["nonce"])
    for value in reversed(candidates):
        if str(value.get("nonce", "")) == nonce:
            return {"seq": value.get("seq"), "ts": value.get("ts")}
    return {"seq": None, "ts": None}


class Publisher:
    def __init__(
        self,
        client: TechnocoreClient,
        state: StateManager,
        identity_file: Path,
        max_chars: int,
        prohibited_patterns: List[str],
    ):
        self.client = client
        self.state = state
        self.identity_file = identity_file
        self.max_chars = max_chars
        self.prohibited_patterns = prohibited_patterns

    @staticmethod
    def _ensure_not_published(post_path: Path) -> None:
        metadata, _ = read_markdown(post_path)
        if metadata.get("status") == "published":
            raise PublishError("this Research Note is already marked as published")

    def validate(self, arxiv_id: str, note: str) -> str:
        try:
            cleaned = sweep_text(note, self.max_chars)
        except ValueError as exc:
            raise PublishError(str(exc)) from exc
        if arxiv_id not in cleaned:
            raise PublishError("Research Note must contain the arXiv ID")
        for pattern in self.prohibited_patterns:
            if re.search(pattern, cleaned, re.I):
                raise PublishError("Research Note contains prohibited pattern: %s" % pattern)
        record = self.state.arxiv_record(arxiv_id) or {}
        if record.get("published_note_sha256") == note_hash(cleaned):
            raise PublishError("this Research Note has already been published")
        if record.get("published_at"):
            raise PublishError("a Research Note for this paper has already been published")
        return cleaned

    def preview(self, arxiv_id: str, post_path: Path) -> Dict[str, Any]:
        self._ensure_not_published(post_path)
        note = self.validate(arxiv_id, extract_note(post_path))
        return {
            "dry_run": True,
            "url": "%s/r/%s" % (self.client.base_url, self.client.room),
            "room": self.client.room,
            "characters": len(note),
            "note": note,
        }

    def publish(self, arxiv_id: str, post_path: Path, passphrase: str) -> Dict[str, Any]:
        self._ensure_not_published(post_path)
        note = self.validate(arxiv_id, extract_note(post_path))
        key = load_identity(self.identity_file, passphrase)
        request = self.client.build_signed_request(key, note)
        response = self.client.send(request)
        receipt = extract_receipt(response, request)
        digest = note_hash(request.normalized_text)
        permalink = None
        if receipt.get("seq") is not None:
            permalink = "%s/humans#r/%s/%s" % (
                self.client.base_url,
                self.client.room,
                receipt["seq"],
            )
        self.state.record_arxiv(
            arxiv_id,
            {
                "published_at": utc_now(),
                "published_note_sha256": digest,
                "technocore_room": self.client.room,
                "technocore_nonce": request.json["nonce"],
                "technocore_did": request.json["did"],
                "technocore_seq": receipt.get("seq"),
                "technocore_server_timestamp": receipt.get("ts"),
                "technocore_permalink": permalink,
            },
        )
        metadata, body = read_markdown(post_path)
        metadata.update(
            {
                "status": "published",
                "published_at": utc_now(),
                "room": self.client.room,
                "note_sha256": digest,
                "did": request.json["did"],
                "nonce": request.json["nonce"],
                "seq": receipt.get("seq"),
                "server_timestamp": receipt.get("ts"),
                "permalink": permalink,
            }
        )
        post_path.write_text(dump_markdown(metadata, body), encoding="utf-8")
        return {
            "dry_run": False,
            "did": request.json["did"],
            "nonce": request.json["nonce"],
            "room": self.client.room,
            "response": response,
            "receipt": receipt,
            "permalink": permalink,
        }
