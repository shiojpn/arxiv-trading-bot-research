# Technocore Reaction Monitoring

## Task

Technocore投稿の証跡保存、reaction通知、手動返信、Contribution証跡、一括投稿を実装する。

## Context

既存実装はDID署名投稿を行えたが、server sequenceを保存せず、room読取や返信検出を持たなかった。

## Assumptions

- replyは通常message本文中の投稿sequence、arXiv ID、完全DIDへの明示的言及として扱う。
- public room本文は署名の有無に関係なく未信頼入力。
- notification先はmacOS Notification Center、監視間隔は10分。

## Options considered

- 自動返信: prompt injectionと誤返信の危険があるため不採用。
- 全messageをreaction扱い: spamになるため不採用。
- native reaction API: 現行公式APIに存在しないため不採用。

## Chosen approach

JSON room polling、cursor、explicit-reference matching、sequence deduplication、未信頼Markdown inbox、human-reviewed signed replyを分離した。

## Impact

- CLIに`technocore sync/inbox/reply`と`contribution export`を追加。
- `publish --all`を追加。
- package versionを0.2.0へ更新。
- 既存3投稿のsequence 4242/4246/4248をreceiptへ補完。
- 既存reply 4268を過去のlive readから未信頼reactionとして復元。

## Verification

- 23 pytest cases passed。
- live room sync succeeded at sequence 4560。
- macOS notification displayed successfully。
- LaunchAgentはmacOSのDesktopアクセス制限で失敗したため停止・退避。定期実行はDesktopへアクセスできるCodex heartbeatを採用し、Codex appの通知を使用する。
- installed CLI reports 0.2.0 and lists the new commands。

## Open questions

- GitHub公開時のlicense。
- 公式task/testnetの真正性を検証する公式DIDまたはmanifest。

## Follow-up: reply receipt

- Reply to 4268 was verified live as sequence 4623.
- Technocore selects JSON responses with `?format=json`, not the Accept header alone.
- The client now adds that query parameter to signed POST requests and stores reply permalink/DID/nonce/hash metadata.
