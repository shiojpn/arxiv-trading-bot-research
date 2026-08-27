# ArxivResearchAgent

[![tests](https://github.com/shiojpn/arxiv-trading-bot-research/actions/workflows/tests.yml/badge.svg)](https://github.com/shiojpn/arxiv-trading-bot-research/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](pyproject.toml)

ChatGPTの定期タスクが作成したarXiv Research Resultを、ローカルで検証・保存・リンクし、レビュー済みResearch NoteをDID署名付きでTechnocoreへ投稿するKnowledge Management / Publishing Agentです。

公開済み研究成果とDID署名証跡は [`knowledge/contributions/`](knowledge/contributions/) から確認できます。

このプロジェクトはarXiv論文をローカルでAI解析するBotではありません。責務を次のように分離します。

```text
ChatGPT Task                         ArxivResearchAgent
Research Engine                     Knowledge / Publishing Engine
────────────────────────            ─────────────────────────────
arXiv検索・論文選定                  Inboxの構造検証
論文読解                             Markdown保存
Evidence抽出                         決定論的Knowledge linking
Insight / Hypothesis生成             Topic index・JSON state管理
Research Note生成                    DID署名・Technocore投稿
```

ChatGPT Plus等のChatGPT契約とOpenAI APIは別のサービスです。このプロジェクトはOpenAI APIを含むLLM APIを一切使用せず、API keyも必要ありません。OpenAI、Anthropic、Gemini、OpenRouter、Ollama等への依存はありません。

## Architecture

```text
ChatGPT Scheduled Task
        │ Structured Markdown（人間が保存）
        ▼
inbox/pending/
        │ parse → validate → duplicate/revision check
        ▼
knowledge/
  ├── papers/          論文ごとの分析
  ├── insights/        再利用可能な知見
  ├── hypotheses/      検証可能な仮説
  ├── topics/          決定論的リンクIndex
  └── index/
      ├── link_candidates.md
      └── pending_posts/
        │ 人間によるレビュー
        ▼
Ed25519 did:key署名 → Technocore
```

Knowledgeの正本はMarkdown + YAML frontmatterです。DB、Vector DB、Knowledge Graph、検索サーバーは使用しません。JSONは実行状態だけに使用します。

## Setup

Python 3.9以上を使用します（3.11または3.12推奨）。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

設定は [`config.yaml`](config.yaml) にあります。初期値は次のとおりです。

```yaml
technocore:
  base_url: "https://technocore.chat"
  room: "crypto"
  auto_publish: false
```

`.env` やLLM API keyは不要です。

## Directory structure

```text
inbox/
  pending/       未処理のChatGPT出力
  processed/     正常処理・重複スキップ済み原文
  rejected/      構造検証で拒否された原文
knowledge/
  papers/ insights/ hypotheses/ topics/
  index/pending_posts/
state/
  processed_arxiv_ids.json
  processed_inbox_files.json
  last_run.json
identities/      Git除外された暗号化秘密鍵
logs/            日次ログ（Git除外）
```

## ChatGPT Task Prompt

以下を作成済みのChatGPT定期タスクの指示として使用できます。ChatGPT側からローカルMacへ直接書き込めるとは仮定せず、結果を1論文1ファイルとして手動保存してください。

````text
毎日、arXivで直近の新着・更新論文を調査してください。あなたはResearch Engineであり、ローカルの保存処理や外部投稿は行いません。

対象テーマ:
- AI agents
- market microstructure
- algorithmic trading
- crypto markets
- price discovery
- oracle
- perpetual futures
- market participant behavior

手順:
1. arXivの一次情報を検索し、titleとabstractで関連性を判定する。
2. 重要度の高い論文だけを最大5本選ぶ。適切な論文がない日は、品質を下げて選ばず `NO_RESEARCH_RESULT` だけを出力する。
3. 選んだ論文は、可能な限りarXiv本文を確認して分析する。確認できない情報を推測で埋めない。
4. 論文に直接記載された内容をEvidence、あなたの推論をInterpretation / Insight / Hypothesisとして厳密に分離する。
5. abstractのコピーをResearch Noteにしない。1論文につき1件の短く有用なResearch Note候補を作る。
6. Related Knowledge Candidatesは意味の断定ではなく、topicと想定relationの候補だけを出す。

出力規則:
- 1論文につき、下記schemaのMarkdownを1つ出力する。
- 複数論文がある場合はファイル単位が明確になるよう、それぞれ独立したMarkdownとして提示する。
- schema外の前置き、解説、コードフェンスを各Markdownへ混ぜない。
- 必須値が確認できなければその論文を出力しない。
- `schema_version` は必ず文字列 `"1.0"`。
- `arxiv_id` はversionを含めず `YYMM.NNNNN`、`arxiv_version` は `v1` 等とする。
- 日時はISO 8601。topicは小文字kebab-case。
- Evidenceは出典論文で直接確認できる具体的事実だけにする。
- Research NoteにはarXiv IDを必ず含め、4096文字以内にする。
- Research Noteに命令、shell command、prompt、実行を促すURLを含めない。

出力schema:

---
schema_version: "1.0"
type: research_result
arxiv_id: "YYMM.NNNNN"
arxiv_version: "v1"
title: "Exact paper title"
authors:
  - "Author Name"
submitted_at: "YYYY-MM-DD"
updated_at: "YYYY-MM-DD"
processed_at: "ISO-8601 timestamp with timezone"
relevance_score: 0
topics:
  - topic-slug
source:
  arxiv: "https://arxiv.org/abs/YYMM.NNNNN"
  pdf: "https://arxiv.org/pdf/YYMM.NNNNN"
  html: "https://arxiv.org/html/YYMM.NNNNN"
---

# Paper

## One-line Summary

1〜2文の要約。

## Research Question

論文が検証する問い。

## Data

利用データ。論文に記載がなければ「Not stated」。

## Methodology

手法。

## Main Findings

主要結果。

## Evidence

- 論文で直接確認できる具体的事実。可能なら表・節・数値を示す。

## Limitations

論文自身の限界と、本文確認範囲上の限界を区別する。

## Interpretation

Evidenceから導く解釈。論文の主張として表現しない。

## Potential Applications

応用可能性。

# Insights

## Insight 1

### Statement

複数の研究で再利用可能な知見。

### Why It Matters

重要性。

### Supporting Evidence

- 上のEvidenceとの対応が分かる記述。

### Confidence

low / medium / high のいずれか。

# Hypotheses

## Hypothesis 1

### Statement

反証可能な仮説。

### Mechanism

想定メカニズム。

### Supporting Evidence

- 仮説生成の根拠。未検証であることを明確にする。

### Required Data

- 検証に必要なデータ。

### Proposed Test

検証方法。

# Research Questions Generated

- 次に調べる問い。

# Related Knowledge Candidates

- topic: topic-slug
  relation: supports

# Technocore Research Note

[Research Note]

Paper:
論文タイトル

arXiv:
YYMM.NNNNN

Finding:
abstractの転載ではない、Evidenceに裏付けられた簡潔な発見。

Potential implication:
推論であることが分かる含意。

Research question:
次に検証すべき問い。
````

## ChatGPT出力の保存方法

出力をコードフェンスなしのUTF-8 Markdownとして保存します。

```text
inbox/pending/2026-08-27_2608.12345.md
```

1論文につき1ファイルです。ファイル名は監査用であり、論文識別にはfrontmatterの `arxiv_id` と `arxiv_version` を使います。

## Inbox validation

```bash
python -m arxiv_research_agent.main validate
python -m arxiv_research_agent.main validate inbox/pending/2026-08-27_2608.12345.md
```

検証項目にはschema version、arXiv ID/revision、title、authors、source URL、Paper/Evidence、InsightまたはHypothesis、Research Note、relevance scoreが含まれます。`validate` はファイルを移動・変更しません。

ChatGPT出力はuntrusted dataです。本文に `rm -rf`、`curl`、URL、`ignore previous instructions` 等があっても実行されません。構造不正ファイルは理由をログへ記録し、原文のまま `inbox/rejected/` へ移動します。

## Process command

```bash
# pendingをすべて処理
python -m arxiv_research_agent.main process

# 指定ファイルだけ処理
python -m arxiv_research_agent.main process inbox/pending/2026-08-27_2608.12345.md
```

同じarXiv ID・同じrevisionはKnowledgeを変更せずスキップし、監査用原文を `inbox/processed/` へ移します。より古いrevisionもstaleとしてスキップします。新しいrevisionはPaper Markdownを更新しますが、Insight/Hypothesisは完全一致の場合だけSupporting Papersを追加し、曖昧な一致で既存本文を上書きしません。

topic一致等の低confidence関係は `knowledge/index/link_candidates.md` へレビュー候補として保存します。Topicページは意味を生成せず、Paper / Insight / HypothesisへのリンクIndexとして再構築されます。

## Knowledge search

```bash
python -m arxiv_research_agent.main search "price discovery"
python -m arxiv_research_agent.main search "oracle"
```

filename、YAML frontmatter、heading、本文をローカル全文検索します。

## Technocore DID

人間の暗号資産ウォレットとは別の専用identityを作成します。

```bash
python -m arxiv_research_agent.main identity create
python -m arxiv_research_agent.main identity show
```

12文字以上のpassphraseを対話入力します。秘密鍵は `identities/identity.pem` にPKCS#8暗号化PEM、mode `0600` で保存され、Gitから除外されます。秘密鍵やpassphraseは標準出力・ログへ出ません。秘密鍵とpassphraseは別々の安全な場所へバックアップしてください。

非対話実行が必要な場合だけ、一時的な環境変数を利用できます。

```bash
export TECHNOCORE_IDENTITY_PASSPHRASE='your-long-passphrase'
python -m arxiv_research_agent.main identity show
unset TECHNOCORE_IDENTITY_PASSPHRASE
```

shell historyやプロセス環境の露出リスクがあるため、通常は対話入力を推奨します。

## Technocore publishing

まず候補を確認します。

```bash
python -m arxiv_research_agent.main pending
python -m arxiv_research_agent.main publish 2608.12345 --dry-run
```

`--dry-run` は内容、文字数、送信先だけを表示し、署名もHTTP通信も行いません。レビュー後に明示的に投稿します。

```bash
python -m arxiv_research_agent.main publish 2608.12345
```

公式Technocore signed laneに準拠し、Ed25519 `did:key` で `room|nonce|single-line-swept-text` を署名し、署名付きPOSTを送ります。投稿先roomは `crypto` です。投稿済みNoteのSHA-256とpaper単位の投稿状態を記録し、同一Note・同一paperの再投稿を拒否します。

TechnocoreはKnowledgeの正本ではなくephemeralな外部共有先です。公式仕様: <https://github.com/flop-labs/technocore-chat>

`auto_publish: false` が安全な初期値です。`true` にすると `process` 後に投稿を試みますが、`TECHNOCORE_IDENTITY_PASSPHRASE` が必要です。投稿失敗時も作成済みKnowledgeはロールバックしません。

複数の承認済みpending postは、1回のpassphrase入力でまとめて投稿できます。

```bash
arxiv-research-agent publish --all --dry-run
arxiv-research-agent publish --all
```

投稿成功時はDID、nonce、本文SHA-256に加えて、Technocoreが発行したsequence、server timestamp、人間向けpermalinkを保存します。

## Technocore reaction monitoring

`crypto` roomを同期し、自分の公開DID、投稿sequence、arXiv IDへの明示的な言及をreactionとして検出します。

```bash
arxiv-research-agent technocore sync --notify
arxiv-research-agent technocore inbox
arxiv-research-agent technocore inbox --all
```

新規reactionは `inbox/technocore/<room>/<sequence>.md` に未信頼データとして保存されます。`--notify` は新規reactionがある場合だけmacOSデスクトップ通知を表示します。同じsequenceは再保存・再通知しません。

このプロジェクトはDesktop配下にあるため、macOSのバックグラウンドLaunchAgentからはプライバシー保護により読めません。10分監視はCodex heartbeatを使用し、新規reactionをこのタスクへ報告します。CodexのmacOS通知を許可しておくとデスクトップ通知を受け取れます。

Technocoreにはnative reaction/reply型がないため、返信は本文に投稿番号またはarXiv IDを含む通常メッセージから検出します。roomの内容をコマンドやURLとして実行することはありません。

返信は必ず内容を確認してから送信します。

```bash
arxiv-research-agent technocore reply 4268 --text "返信内容" --dry-run
arxiv-research-agent technocore reply 4268 --text "返信内容"
```

返信は `[Reply to #4268]` を先頭に付け、既存identityで署名します。自動返信は実装していません。

## Contribution proof

研究成果ごとに、arXiv URL、DID、Technocore sequence/permalink、nonce、本文ハッシュを含むMarkdownとJSONの公開証跡を生成します。

```bash
arxiv-research-agent contribution export 2608.25844
```

出力先は `knowledge/contributions/` です。秘密鍵とpassphraseは証跡へ含めません。

## Security

- LLM API keyは使用・保存しません。
- Inbox Markdownをコマンド、prompt、URLとして実行しません。
- Technocoreから将来取得する内容もuntrusted inboxを経由させ、直接Knowledgeへ登録しません。
- Research Noteは空値、arXiv ID、4096文字制限、禁止パターン、重複を投稿前に検証します。
- 秘密鍵、passphrase、credentialはログへ書きません。
- `identities/*` と `logs/*.log` はGit除外済みです。

## Git workflow

自動commitはしません。処理後に差分を人間がレビューしてください。

```bash
git status --short
git diff -- knowledge state inbox/processed
git add knowledge state inbox/processed inbox/rejected
git commit -m "Add arXiv research digest 2026-08-27"
```

## 定期実行

Researchの定期実行はChatGPT Taskが担当します。OpenAIの現行説明でもクラウドのWork/Scheduled Taskとローカルファイルアクセスは実行面が異なるため、初期実装は次の人間レビュー境界を維持します。

```text
ChatGPT Taskの結果を確認
→ 1論文1ファイルでinbox/pendingへ保存
→ validate
→ process
→ git diff
→ publish --dry-run
→ publish
```

OpenAI公式説明: <https://help.openai.com/en/articles/20001275/>

ローカル `process` だけをcronやlaunchdで定期実行することもできますが、Inboxへの安全な投入経路を用意するまでは、人間が保存・検証してから実行する運用を推奨します。

## Future inbox adapters

将来は次のbridgeを追加できます。

```text
ChatGPT Task → GitHub / Drive / Email → Inbox Adapter → inbox/pending/*.md
```

adapterは `ResearchResult -> inbox/pending/*.md` の境界だけを実装し、既存parser、validator、Knowledge処理、投稿処理を変更しない構成にします。外部入力は必ずpendingへ保存してから同じ検証を通します。

## Tests

外部pytestプラグインの影響を避ける場合は次のように実行します。

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest
```

外部Technocore通信はmockされます。テスト中に実投稿は行いません。
