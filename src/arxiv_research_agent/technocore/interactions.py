"""Human-reviewed signed replies to stored Technocore reactions."""

import hashlib
import re
from typing import Any, Dict, List

from arxiv_research_agent.state.manager import StateManager
from arxiv_research_agent.technocore.client import TechnocoreClient
from arxiv_research_agent.technocore.identity import load_identity, sweep_text
from arxiv_research_agent.technocore.monitor import TechnocoreMonitor
from arxiv_research_agent.technocore.publisher import PublishError, extract_receipt


class InteractionManager:
    def __init__(
        self,
        client: TechnocoreClient,
        state: StateManager,
        monitor: TechnocoreMonitor,
        identity_file: Any,
        max_chars: int,
        prohibited_patterns: List[str],
    ):
        self.client = client
        self.state = state
        self.monitor = monitor
        self.identity_file = identity_file
        self.max_chars = max_chars
        self.prohibited_patterns = prohibited_patterns

    def preview(self, seq: int, text: str) -> Dict[str, Any]:
        self._ensure_target(seq)
        message = self._validate(seq, text)
        return {
            "dry_run": True,
            "room": self.client.room,
            "reply_to": seq,
            "characters": len(message),
            "text": message,
        }

    def reply(self, seq: int, text: str, passphrase: str) -> Dict[str, Any]:
        self._ensure_target(seq)
        message = self._validate(seq, text)
        key = load_identity(self.identity_file, passphrase)
        request = self.client.build_signed_request(key, message)
        response = self.client.send(request)
        receipt = extract_receipt(response, request)
        self.monitor.mark_replied(
            seq,
            receipt,
            {
                "reply_did": request.json["did"],
                "reply_nonce": request.json["nonce"],
                "reply_text_sha256": hashlib.sha256(
                    request.normalized_text.encode("utf-8")
                ).hexdigest(),
            },
        )
        return {
            "dry_run": False,
            "room": self.client.room,
            "reply_to": seq,
            "did": request.json["did"],
            "nonce": request.json["nonce"],
            "receipt": receipt,
            "permalink": (
                "%s/humans#r/%s/%s"
                % (self.client.base_url, self.client.room, receipt["seq"])
                if receipt.get("seq") is not None
                else None
            ),
        }

    def _ensure_target(self, seq: int) -> None:
        if not self.monitor.reaction_path(seq).exists():
            raise FileNotFoundError("stored Technocore reaction not found: %s" % seq)

    def _validate(self, seq: int, text: str) -> str:
        try:
            cleaned = sweep_text("[Reply to #%d] %s" % (seq, text), self.max_chars)
        except ValueError as exc:
            raise PublishError(str(exc)) from exc
        for pattern in self.prohibited_patterns:
            if re.search(pattern, cleaned, re.I):
                raise PublishError("reply contains prohibited pattern: %s" % pattern)
        return cleaned
