# INIAD-AIO

INIAD-AIO は、INIAD（東洋大学情報連携学部）向けの AI 情報アクセス基盤です。

MOOCs を中心とした講義・課題・資料情報を収集・整理し、自然言語で検索・参照できる環境の構築を目的としています。

現在は **v1.0 発表版** の準備中です。

---

## はじめに

このリポジトリは現在も大きく構造変更中です。

初見の場合、ソースコードを直接読む前に、まず Overview 系ドキュメントを参照してください。

---

## AI に読ませる場合

このリポジトリを AI アシスタントに説明・編集・解析させる場合は、GeeKEN Discord で共有されている Overview / Context documents を読ませてください。

これらには以下が定義されています。

- INIAD-AIO の目的
- 現在の実装状況
- 未実装範囲
- プロジェクト固有語彙
- 初心者向け説明方針

特定機能について扱う場合は、対応する Node Overview / Node Vocabulary も追加で参照してください。

ファイル名やディレクトリ構造のみから推測せず、Overview を優先的なコンテキストとして扱ってください。

---

## 現在の状態（v1.0 発表版）

現在実装・検証中の主な要素:

- FastAPI backend
- COT101 / COT105 / SEM101 の課題候補一覧
- 課題 status のローカルJSON永続化
- MOOCs-Collect が保存したPDFのローカル discovery
- PDFテキストレイヤー抽出と `data/local/text_cache/` 保存
- ローカルPDF検索API
- 課題一覧とPDF検索の最小UI

発表版では、ローカルで確実に動く課題確認とPDF資料検索を優先しています。

---

## 未完成・未安定な要素

以下は未完成、または実験段階です。

- Embedding 検索
- OCR
- MCP 連携
- 本格 Ontology
- 本格 RAG
- 本番認証基盤
- 大規模 multi-source ingestion
- 安定 UI
- 権限管理

---

## 開発

```bash
docker compose up --build
```

API:

```txt
http://localhost:8000
```

---

## ドキュメント方針

README は入口のみを担当します。

詳細説明・意味構造・開発意図・変更履歴は以下に分離されています。

- Overview
- ACV (Atlas Compressed Vocabulary)
- CEL（Concrete Edit Log）

大規模変更時は README を肥大化させるのではなく、対応する Overview または CEL を更新してください。
