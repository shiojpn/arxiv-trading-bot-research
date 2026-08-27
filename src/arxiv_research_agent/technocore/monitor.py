"""Read Technocore as untrusted data and detect explicit reactions."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from arxiv_research_agent.knowledge.repository import dump_markdown, read_markdown
from arxiv_research_agent.notifications import notify_macos
from arxiv_research_agent.state.manager import StateManager, utc_now
from arxiv_research_agent.technocore.client import TechnocoreClient


class TechnocoreMonitor:
    def __init__(
        self,
        client: TechnocoreClient,
        state: StateManager,
        knowledge_dir: Path,
        inbox_dir: Path,
        sync_limit: int = 200,
    ):
        self.client = client
        self.state = state
        self.knowledge_dir = knowledge_dir
        self.inbox_dir = inbox_dir / "technocore" / client.room
        self.sync_limit = min(200, max(1, sync_limit))

    def sync(self, notify: bool = False) -> Dict[str, Any]:
        cursor = self.state.room_cursor(self.client.room)
        response = self.client.read_room(since=cursor or None, limit=self.sync_limit)
        messages = [item for item in response.get("messages", []) if isinstance(item, dict)]
        cursor_gap = self._cursor_gap(response, cursor)
        records = self.state.arxiv_records()
        backfilled = self._backfill_receipts(messages, records)
        records = self.state.arxiv_records()
        own_dids = {
            str(value.get("technocore_did"))
            for value in records.values()
            if isinstance(value, dict) and value.get("technocore_did")
        }
        new_reactions: List[Dict[str, Any]] = []
        for message in messages:
            reaction = self._reaction(message, records, own_dids)
            if reaction and self._save_reaction(reaction):
                new_reactions.append(reaction)

        last_seq = self._last_seq(response, messages, cursor)
        self.state.record_room_cursor(self.client.room, last_seq)
        notified = False
        if notify and (new_reactions or cursor_gap):
            if new_reactions:
                first = new_reactions[0]
                extra = len(new_reactions) - 1
                detail = "#%s: %s" % (first["seq"], first["text"][:120])
                if extra:
                    detail += "（ほか%d件）" % extra
                title = "ArxivResearchAgent: 新しいreaction"
            else:
                title = "ArxivResearchAgent: 監視gap"
                detail = "200件を超えるmessageが流れたため未取得範囲があります"
            notified = notify_macos(title, detail)
        return {
            "room": self.client.room,
            "previous_cursor": cursor,
            "last_seq": last_seq,
            "messages_read": len(messages),
            "cursor_gap": cursor_gap,
            "receipts_backfilled": backfilled,
            "new_reactions": new_reactions,
            "notification_sent": notified,
        }

    @staticmethod
    def _cursor_gap(response: Dict[str, Any], cursor: int) -> bool:
        if cursor <= 0 or response.get("first_seq") is None:
            return False
        try:
            return int(response["first_seq"]) > cursor + 1
        except (TypeError, ValueError):
            return False

    def list_reactions(self, unread_only: bool = True) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for path in sorted(self.inbox_dir.glob("*.md")):
            try:
                metadata, body = read_markdown(path)
            except ValueError:
                continue
            if unread_only and metadata.get("status") != "unread":
                continue
            item = dict(metadata)
            item["text"] = body.strip()
            item["path"] = str(path)
            results.append(item)
        return results

    def reaction_path(self, seq: int) -> Path:
        return self.inbox_dir / ("%010d.md" % seq)

    def mark_replied(
        self, seq: int, receipt: Dict[str, Any], details: Optional[Dict[str, Any]] = None
    ) -> None:
        path = self.reaction_path(seq)
        metadata, body = read_markdown(path)
        reply_seq = receipt.get("seq")
        metadata.update(
            {
                "status": "replied",
                "replied_at": utc_now(),
                "reply_seq": reply_seq,
                "reply_timestamp": receipt.get("ts"),
                "reply_permalink": (
                    "%s/humans#r/%s/%s"
                    % (self.client.base_url, self.client.room, reply_seq)
                    if reply_seq is not None
                    else None
                ),
            }
        )
        if details:
            metadata.update(details)
        path.write_text(dump_markdown(metadata, body), encoding="utf-8")

    def _backfill_receipts(
        self, messages: List[Dict[str, Any]], records: Dict[str, Any]
    ) -> int:
        count = 0
        for arxiv_id, record in records.items():
            if not isinstance(record, dict) or not record.get("published_at"):
                continue
            did = str(record.get("technocore_did", ""))
            match = next(
                (
                    item
                    for item in messages
                    if str(item.get("from", "")) == did
                    and arxiv_id in str(item.get("text", ""))
                ),
                None,
            )
            if not match or match.get("seq") is None:
                continue
            seq = int(match["seq"])
            permalink = "%s/humans#r/%s/%d" % (
                self.client.base_url,
                self.client.room,
                seq,
            )
            if record.get("technocore_seq") != seq:
                self.state.record_arxiv(
                    arxiv_id,
                    {
                        "technocore_seq": seq,
                        "technocore_server_timestamp": match.get("ts"),
                        "technocore_permalink": permalink,
                    },
                )
                self._update_pending_post(arxiv_id, seq, match.get("ts"), permalink)
                count += 1
        return count

    def _update_pending_post(
        self, arxiv_id: str, seq: int, timestamp: Any, permalink: str
    ) -> None:
        path = self.knowledge_dir / "index" / "pending_posts" / (arxiv_id + ".md")
        if not path.exists():
            return
        metadata, body = read_markdown(path)
        metadata.update(
            {"seq": seq, "server_timestamp": timestamp, "permalink": permalink}
        )
        path.write_text(dump_markdown(metadata, body), encoding="utf-8")

    def _reaction(
        self,
        message: Dict[str, Any],
        records: Dict[str, Any],
        own_dids: set,
    ) -> Optional[Dict[str, Any]]:
        try:
            seq = int(message["seq"])
        except (KeyError, TypeError, ValueError):
            return None
        sender = str(message.get("from", ""))
        text = str(message.get("text", ""))
        if not text or sender in own_dids:
            return None
        matched_arxiv: List[str] = []
        matched_sequences: List[int] = []
        matched_dids: List[str] = []
        for arxiv_id, record in records.items():
            if not isinstance(record, dict) or not record.get("published_at"):
                continue
            if arxiv_id in text:
                matched_arxiv.append(arxiv_id)
            own_seq = record.get("technocore_seq")
            if own_seq is not None and re.search(r"(?<!\d)%s(?!\d)" % re.escape(str(own_seq)), text):
                matched_sequences.append(int(own_seq))
            did = str(record.get("technocore_did", ""))
            if did and did in text:
                matched_dids.append(did)
        if not (matched_arxiv or matched_sequences or matched_dids):
            return None
        return {
            "type": "technocore_reaction",
            "room": self.client.room,
            "seq": seq,
            "server_timestamp": message.get("ts"),
            "sender": sender,
            "matched_arxiv_ids": sorted(set(matched_arxiv)),
            "matched_sequences": sorted(set(matched_sequences)),
            "matched_dids": sorted(set(matched_dids)),
            "received_at": utc_now(),
            "status": "unread",
            "trusted": False,
            "permalink": "%s/humans#r/%s/%d"
            % (self.client.base_url, self.client.room, seq),
            "text": text,
        }

    def _save_reaction(self, reaction: Dict[str, Any]) -> bool:
        path = self.reaction_path(int(reaction["seq"]))
        if path.exists():
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        metadata = {key: value for key, value in reaction.items() if key != "text"}
        path.write_text(dump_markdown(metadata, reaction["text"]), encoding="utf-8")
        return True

    @staticmethod
    def _last_seq(
        response: Dict[str, Any], messages: List[Dict[str, Any]], cursor: int
    ) -> int:
        try:
            return max(cursor, int(response.get("last_seq", cursor)))
        except (TypeError, ValueError):
            valid = []
            for item in messages:
                try:
                    valid.append(int(item.get("seq", 0)))
                except (TypeError, ValueError):
                    pass
            return max([cursor] + valid)
