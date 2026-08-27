"""Command-line interface for ArxivResearchAgent."""

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Optional

from arxiv_research_agent.config import AppConfig, load_config
from arxiv_research_agent.contributions import ContributionManager
from arxiv_research_agent.inbox.processor import InboxProcessor
from arxiv_research_agent.knowledge.repository import read_markdown
from arxiv_research_agent.knowledge.search import search_knowledge
from arxiv_research_agent.state.manager import StateManager
from arxiv_research_agent.technocore.client import TechnocoreClient
from arxiv_research_agent.technocore.identity import (
    IdentityError,
    create_identity,
    did_from_private_key,
    load_identity,
)
from arxiv_research_agent.technocore.publisher import PublishError, Publisher
from arxiv_research_agent.technocore.interactions import InteractionManager
from arxiv_research_agent.technocore.monitor import TechnocoreMonitor


def _passphrase(confirm: bool = False) -> str:
    from_environment = os.environ.get("TECHNOCORE_IDENTITY_PASSPHRASE")
    if from_environment:
        return from_environment
    value = getpass.getpass("Identity passphrase: ")
    if confirm:
        confirmation = getpass.getpass("Confirm identity passphrase: ")
        if value != confirmation:
            raise IdentityError("passphrases do not match")
    return value


def _publisher(config: AppConfig) -> Publisher:
    client = TechnocoreClient(
        config.technocore.base_url,
        config.technocore.room,
        config.technocore.request_timeout_seconds,
    )
    return Publisher(
        client,
        StateManager(config.paths.state),
        config.technocore.identity_file,
        config.technocore.max_note_chars,
        config.technocore.prohibited_patterns,
    )


def _pending_path(config: AppConfig, arxiv_id: str) -> Path:
    path = config.paths.knowledge / "index" / "pending_posts" / (arxiv_id + ".md")
    if not path.exists():
        raise FileNotFoundError("pending Research Note not found: %s" % arxiv_id)
    return path


def _monitor(config: AppConfig) -> TechnocoreMonitor:
    return TechnocoreMonitor(
        _publisher(config).client,
        StateManager(config.paths.state),
        config.paths.knowledge,
        config.paths.inbox_pending.parent,
        config.technocore.sync_limit,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arxiv-research-agent",
        description="Store ChatGPT Task research results as Markdown knowledge and publish reviewed notes.",
    )
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    commands = parser.add_subparsers(dest="command", required=True)

    process = commands.add_parser("process", help="process inbox/pending Markdown")
    process.add_argument("file", nargs="?", type=Path)

    validate = commands.add_parser("validate", help="validate inbox without moving files")
    validate.add_argument("file", nargs="?", type=Path)

    search = commands.add_parser("search", help="search local Markdown knowledge")
    search.add_argument("query")

    identity = commands.add_parser("identity", help="manage Technocore identity")
    identity.add_argument("action", choices=("create", "show"))

    publish = commands.add_parser("publish", help="publish a reviewed Research Note")
    publish.add_argument("arxiv_id", nargs="?")
    publish.add_argument("--all", dest="all_posts", action="store_true")
    publish.add_argument("--dry-run", action="store_true")

    commands.add_parser("pending", help="list pending Technocore posts")

    technocore = commands.add_parser("technocore", help="sync and reply to Technocore")
    tc_commands = technocore.add_subparsers(dest="technocore_command", required=True)
    sync = tc_commands.add_parser("sync", help="sync explicit reactions from the room")
    sync.add_argument("--notify", dest="notify", action="store_true", default=None)
    sync.add_argument("--no-notify", dest="notify", action="store_false")
    inbox = tc_commands.add_parser("inbox", help="list stored reactions")
    inbox.add_argument("--all", dest="show_all", action="store_true")
    reply = tc_commands.add_parser("reply", help="send a reviewed signed reply")
    reply.add_argument("seq", type=int)
    reply.add_argument("--text", required=True)
    reply.add_argument("--dry-run", action="store_true")

    contribution = commands.add_parser("contribution", help="manage contribution proofs")
    contribution_commands = contribution.add_subparsers(
        dest="contribution_command", required=True
    )
    export = contribution_commands.add_parser("export", help="export proof artifacts")
    export.add_argument("arxiv_id")
    return parser


def run_cli(args: argparse.Namespace, config: AppConfig) -> int:
    if args.command == "process":
        summary = InboxProcessor(config).process(args.file)
        print(json.dumps(summary.as_dict(), ensure_ascii=False, indent=2))
        return 0 if not summary.errors else 1

    if args.command == "validate":
        report = InboxProcessor(config).validate_only(args.file)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["valid"] else 1

    if args.command == "search":
        matches = search_knowledge(config.paths.knowledge, args.query)
        for item in matches:
            relative = item.path.relative_to(config.paths.root)
            print("%s:%d: %s" % (relative, item.line, item.excerpt))
        return 0 if matches else 1

    if args.command == "identity":
        if args.action == "create":
            did = create_identity(config.technocore.identity_file, _passphrase(confirm=True))
        else:
            key = load_identity(config.technocore.identity_file, _passphrase())
            did = did_from_private_key(key)
        print("Agent DID:\n%s" % did)
        return 0

    if args.command == "publish":
        publisher = _publisher(config)
        if bool(args.arxiv_id) == bool(args.all_posts):
            raise ValueError("provide one arXiv ID or --all")
        if args.all_posts:
            directory = config.paths.knowledge / "index" / "pending_posts"
            candidates = []
            for path in sorted(directory.glob("*.md")):
                metadata, _ = read_markdown(path)
                if metadata.get("status") == "pending":
                    candidates.append((str(metadata.get("arxiv_id", path.stem)), path))
            passphrase = None if args.dry_run or not candidates else _passphrase()
            results = []
            errors = []
            for arxiv_id, post_path in candidates:
                try:
                    value = (
                        publisher.preview(arxiv_id, post_path)
                        if args.dry_run
                        else publisher.publish(arxiv_id, post_path, str(passphrase))
                    )
                    results.append({"arxiv_id": arxiv_id, "result": value})
                except (ValueError, FileNotFoundError) as exc:
                    errors.append({"arxiv_id": arxiv_id, "error": str(exc)})
            result = {"count": len(results), "results": results, "errors": errors}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1 if errors else 0
        post_path = _pending_path(config, args.arxiv_id)
        result = (
            publisher.preview(args.arxiv_id, post_path)
            if args.dry_run
            else publisher.publish(args.arxiv_id, post_path, _passphrase())
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "technocore":
        monitor = _monitor(config)
        if args.technocore_command == "sync":
            notify = (
                config.technocore.notify_on_reaction
                if args.notify is None
                else args.notify
            )
            print(json.dumps(monitor.sync(notify=notify), ensure_ascii=False, indent=2))
            return 0
        if args.technocore_command == "inbox":
            reactions = monitor.list_reactions(unread_only=not args.show_all)
            print(json.dumps(reactions, ensure_ascii=False, indent=2))
            return 0
        if args.technocore_command == "reply":
            manager = InteractionManager(
                monitor.client,
                StateManager(config.paths.state),
                monitor,
                config.technocore.identity_file,
                config.technocore.max_note_chars,
                config.technocore.prohibited_patterns,
            )
            result = (
                manager.preview(args.seq, args.text)
                if args.dry_run
                else manager.reply(args.seq, args.text, _passphrase())
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

    if args.command == "contribution":
        if args.contribution_command == "export":
            result = ContributionManager(
                config.paths.knowledge, StateManager(config.paths.state)
            ).export(args.arxiv_id)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

    if args.command == "pending":
        directory = config.paths.knowledge / "index" / "pending_posts"
        count = 0
        for path in sorted(directory.glob("*.md")):
            try:
                metadata, _ = read_markdown(path)
            except ValueError:
                continue
            if metadata.get("status") == "pending":
                print("%s\t%s" % (metadata.get("arxiv_id", path.stem), path))
                count += 1
        print("Pending posts: %d" % count)
        return 0
    return 2


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        return run_cli(args, config)
    except (FileNotFoundError, ValueError, IdentityError, PublishError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
