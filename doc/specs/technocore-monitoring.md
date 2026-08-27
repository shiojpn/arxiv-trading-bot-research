# Technocore Monitoring Specification

## Purpose

ArxivResearchAgentのDID署名投稿に対する明示的な言及を取得し、未信頼inboxへ保存して新規分だけ通知する。

## Boundaries

- 対象は設定された1つのpublic room。
- Technocore本文はすべて未信頼データ。
- 自動返信、URL取得、本文の命令実行は行わない。
- Technocore DID鍵をwallet鍵として使用しない。

## Inputs / Outputs

- Input: `GET /r/<room>?format=json&since=<cursor>&limit=200`
- Cursor: `state/technocore_sync.json`
- Reaction: `inbox/technocore/<room>/<seq>.md`
- Receipt: paper stateおよびpending post metadata
- Notification: macOS Notification Center

## State model / invariants

- room sequenceをdeduplication keyとする。
- 自分のDIDからの投稿はreactionにしない。
- 自分のarXiv ID、保存済み投稿sequence、完全DIDのいずれかへの明示的言及だけをreactionにする。
- notificationは新規保存されたreactionが1件以上のときだけ送る。
- server sequence、timestamp、permalinkを投稿receiptとして保存する。

## Ordering / timing

- Codex heartbeatが10分ごとにCLI同期を実行する。
- 1回の取得上限は公式上限の200件。
- 200件を超える未取得messageが発生した場合、完全性を保証できない。
- `first_seq > previous_cursor + 1` をgapとして検出し通知する。

## Error handling

- network/HTTP/JSON shape errorはCLI errorとして返しcursorを進めない。
- macOS通知失敗はreaction保存をロールバックしない。
- 不正なmessageは無視し、実行しない。

## Compatibility

- Technocore OpenAPI 0.10.0のroom JSONとsigned POST laneを前提とする。
- native reply/reaction APIは前提にしない。

## Tests

- receipt抽出
- sequence backfill
- explicit mention検出
- duplicate reaction抑止
- reply dry-run
- contribution proof生成
- room JSON shape validation

## Open issues

- 公式task/testnet仕様は未確認のため未接続。
- GitHub公開・LICENSE選定はユーザー判断が必要。
