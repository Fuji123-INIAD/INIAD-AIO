# 開発版番号の対応表

更新日：2026-10-16

正式リリース前の発表版・実験版を開発版として整理するため、旧 v1.0〜v1.4 を v0.4〜v0.8 へ変更しました。機能を追加したリリースではなく、呼称と参照先の変更です。

| 旧番号 | 新番号 | 内容 |
| --- | --- | --- |
| v1.0 発表版 | v0.4 | 課題一覧・ローカルPDF検索デモ |
| v1.1 experimental | v0.5 | MCP・軽量Ontology・Context Card・検索実験 |
| v1.2 experimental | v0.6 | 課題backlog・資料snippet・MOOCs-Collect連携 |
| v1.3 experimental | v0.7 | MOOCs由来の課題候補MVP |
| v1.4 experimental | v0.8 | AI-ready context pack・Claude向け出力安定化 |

v0.3以前の番号は維持します。**将来の正式版 v1.0 という構想はそのまま残します。** 2026年6月以前のロードマップ等にある正式版v1.0と、7月の発表デモに付けていた旧v1.0は別です。初期ロードマップにある予定名「v0.4 RAG基盤」も当時の計画であり、今回のv0.4と同じ完成実績を指すものではありません。

## ブランチと履歴

新番号のブランチは、下記の元コミットを親とする改番コミットから始まります。過去のコミットSHA・メッセージ・タグは変更していません。旧ブランチは当時の記録・外部リンクとの互換性のため、その位置に残しています。現在の番号で参照する場合は新ブランチを使ってください。

| 当時のブランチ | 新番号で参照するブランチ | 改番前の先端 |
| --- | --- | --- |
| `feature/v0.3-local-mcp` | [`feature/v0.4-local-task-pdf-demo`](https://github.com/Fuji123-INIAD/INIAD-AIO/tree/feature/v0.4-local-task-pdf-demo) | `e629fe7` |
| `feature/v1.1-adventure-mcp-ontology` | [`feature/v0.5-adventure-mcp-ontology`](https://github.com/Fuji123-INIAD/INIAD-AIO/tree/feature/v0.5-adventure-mcp-ontology) | `850bdc7` |
| `feature/v1.2-mcp-chat-materials-experiment` | [`feature/v0.6-mcp-chat-materials-experiment`](https://github.com/Fuji123-INIAD/INIAD-AIO/tree/feature/v0.6-mcp-chat-materials-experiment) | `939544d` |
| `demo/v1.2-presentation-20260708` | [`demo/v0.6-presentation-20260708`](https://github.com/Fuji123-INIAD/INIAD-AIO/tree/demo/v0.6-presentation-20260708) | `939544d` |
| `feature/v1.3-moocs-real-task-sync` | [`feature/v0.7-moocs-real-task-sync`](https://github.com/Fuji123-INIAD/INIAD-AIO/tree/feature/v0.7-moocs-real-task-sync) | `601e370` |
| `feature/v1.4-ai-ready-mcp-context` | [`feature/v0.8-ai-ready-mcp-context`](https://github.com/Fuji123-INIAD/INIAD-AIO/tree/feature/v0.8-ai-ready-mcp-context) | `e995e92` |

`main`はv0.2系コードを維持し、対応表と新ブランチへの案内を追加しています。新しい実験版の機能をmainへ統合したわけではありません。凍結記録の旧「v1.2」は新「v0.6」に対応し、改番によって開発再開や凍結解除を意味しません。

## 文書ファイル名

新番号のブランチでは次の名前に変更しています。過去コミットのURLでは旧ファイル名を使用してください。日付入り引き継ぎ資料の元ブランチ・コミット引用は、当時の記録として旧表記を保持しています。

| 旧ファイル名 | 新ファイル名 |
| --- | --- |
| `docs/context/20260706_v12_demo_display_handoff.md` | `docs/context/20260706_v06_demo_display_handoff.md` |
| `docs/context/20260706_v12_search_quality_handoff.md` | `docs/context/20260706_v06_search_quality_handoff.md` |
| `docs/context/20260707_v12_mcp_demo_handoff.md` | `docs/context/20260707_v06_mcp_demo_handoff.md` |
| `docs/context/20260707_v13_moocs_task_sync_handoff.md` | `docs/context/20260707_v07_moocs_task_sync_handoff.md` |
| `docs/context/20260708_v14_ai_ready_context_handoff.md` | `docs/context/20260708_v08_ai_ready_context_handoff.md` |
| `docs/context/20260708_v14_claude_mcp_stabilization_handoff.md` | `docs/context/20260708_v08_claude_mcp_stabilization_handoff.md` |
| `docs/demo/20260707_v12_mcp_demo_runbook.md` | `docs/demo/20260707_v06_mcp_demo_runbook.md` |
| `docs/demo/20260708_v10_demo_guide.md` | `docs/demo/20260708_v04_demo_guide.md` |
| `docs/design/20260706_v11_mcp_ontology_embedding_experiment.md` | `docs/design/20260706_v05_mcp_ontology_embedding_experiment.md` |
| `docs/design/20260706_v12_chat_ai_mcp_materials_experiment.md` | `docs/design/20260706_v06_chat_ai_mcp_materials_experiment.md` |
| `docs/design/20260708_v14_ai_ready_mcp_context.md` | `docs/design/20260708_v08_ai_ready_mcp_context.md` |

## 互換性

APIパス、MCP tool名、JSONフィールド、データ形式、既存の内部識別子（例：`test_moocs_collect_v12_providers`）は維持します。画面の版番号と対応する既存テスト期待値のみ更新します。Obsidian原本や過去の公開記録は改変せず、この対応表で読み替えます。
