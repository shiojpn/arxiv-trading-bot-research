"""Generate stable local proof artifacts for public research contributions."""

import json
from pathlib import Path
from typing import Any, Dict

from arxiv_research_agent.knowledge.repository import dump_markdown, read_markdown
from arxiv_research_agent.state.manager import StateManager, utc_now


class ContributionManager:
    def __init__(self, knowledge_dir: Path, state: StateManager):
        self.knowledge_dir = knowledge_dir
        self.state = state
        self.output_dir = knowledge_dir / "contributions"

    def export(self, arxiv_id: str) -> Dict[str, str]:
        paper_path = self.knowledge_dir / "papers" / (arxiv_id + ".md")
        if not paper_path.exists():
            raise FileNotFoundError("paper not found: %s" % arxiv_id)
        record = self.state.arxiv_record(arxiv_id) or {}
        if not record.get("published_at"):
            raise ValueError("paper has no published Technocore record: %s" % arxiv_id)
        paper_metadata, _ = read_markdown(paper_path)
        proof: Dict[str, Any] = {
            "schema_version": "1.0",
            "type": "contribution_proof",
            "contribution_type": "research",
            "arxiv_id": arxiv_id,
            "title": paper_metadata.get("title", ""),
            "arxiv_url": "https://arxiv.org/abs/%s" % arxiv_id,
            "did": record.get("technocore_did"),
            "technocore_room": record.get("technocore_room"),
            "technocore_seq": record.get("technocore_seq"),
            "technocore_server_timestamp": record.get("technocore_server_timestamp"),
            "technocore_permalink": record.get("technocore_permalink"),
            "note_sha256": record.get("published_note_sha256"),
            "nonce": record.get("technocore_nonce"),
            "generated_at": utc_now(),
            "verification_status": (
                "remote-receipt-recorded" if record.get("technocore_seq") else "local-only"
            ),
        }
        self.output_dir.mkdir(parents=True, exist_ok=True)
        json_path = self.output_dir / (arxiv_id + ".json")
        markdown_path = self.output_dir / (arxiv_id + ".md")
        json_path.write_text(
            json.dumps(proof, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        body = """# {title}

## Contribution

arXiv研究結果を構造化し、検証済みResearch NoteとしてTechnocoreへDID署名付きで公開。

## Public Evidence

- arXiv: {arxiv_url}
- Technocore: {permalink}
- Room / sequence: {room} / {seq}
- DID: {did}
- Note SHA-256: {digest}

## Verification

`verification_status`: {status}
""".format(
            title=proof["title"],
            arxiv_url=proof["arxiv_url"],
            permalink=proof["technocore_permalink"] or "not recorded",
            room=proof["technocore_room"],
            seq=proof["technocore_seq"] or "not recorded",
            did=proof["did"],
            digest=proof["note_sha256"],
            status=proof["verification_status"],
        )
        markdown_path.write_text(dump_markdown(proof, body), encoding="utf-8")
        return {"markdown": str(markdown_path), "json": str(json_path)}
