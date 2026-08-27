"""Minimal, atomic JSON state management."""

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateManager:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.processed_arxiv_path = state_dir / "processed_arxiv_ids.json"
        self.processed_inbox_path = state_dir / "processed_inbox_files.json"
        self.last_run_path = state_dir / "last_run.json"
        self.technocore_sync_path = state_dir / "technocore_sync.json"
        for path in (
            self.processed_arxiv_path,
            self.processed_inbox_path,
            self.last_run_path,
            self.technocore_sync_path,
        ):
            if not path.exists():
                self._write(path, {})

    def _read(self, path: Path) -> Dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write(self, path: Path, value: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def arxiv_record(self, arxiv_id: str) -> Optional[Dict[str, Any]]:
        value = self._read(self.processed_arxiv_path).get(arxiv_id)
        return value if isinstance(value, dict) else None

    def arxiv_records(self) -> Dict[str, Any]:
        return self._read(self.processed_arxiv_path)

    def record_arxiv(self, arxiv_id: str, values: Dict[str, Any]) -> None:
        state = self._read(self.processed_arxiv_path)
        existing = state.get(arxiv_id, {})
        if not isinstance(existing, dict):
            existing = {}
        existing.update(values)
        state[arxiv_id] = existing
        self._write(self.processed_arxiv_path, state)

    def record_inbox(self, source_name: str, source_hash: str, outcome: str) -> None:
        state = self._read(self.processed_inbox_path)
        state[source_name] = {
            "sha256": source_hash,
            "outcome": outcome,
            "processed_at": utc_now(),
        }
        self._write(self.processed_inbox_path, state)

    def record_last_run(self, summary: Dict[str, Any]) -> None:
        value = dict(summary)
        value["finished_at"] = utc_now()
        self._write(self.last_run_path, value)

    def technocore_sync_state(self) -> Dict[str, Any]:
        return self._read(self.technocore_sync_path)

    def room_cursor(self, room: str) -> int:
        rooms = self.technocore_sync_state().get("rooms", {})
        value = rooms.get(room, {}) if isinstance(rooms, dict) else {}
        try:
            return int(value.get("last_seq", 0))
        except (TypeError, ValueError):
            return 0

    def record_room_cursor(self, room: str, last_seq: int) -> None:
        state = self.technocore_sync_state()
        rooms = state.setdefault("rooms", {})
        rooms[room] = {"last_seq": int(last_seq), "synced_at": utc_now()}
        self._write(self.technocore_sync_path, state)

    @staticmethod
    def file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
