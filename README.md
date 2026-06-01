# INIAD-AIO

INIAD生向けAIアシスタントプロジェクト。

講義資料・課題・大学情報をデータベース化し、自然言語で検索・質問できるシステムの開発を目指しています。

---

## 現在の状況

現在はPoC（Proof of Concept）段階です。

実装済み機能

* FastAPI バックエンド
* SQLite データベース
* Gemini API 連携
* 自然言語による検索
* Web UI
* 回答生成
* 参照データ（Sources）表示

現在の処理フロー

```text
質問
↓
SQLite検索
↓
Gemini回答生成
↓
Web UI表示
```

---

## ディレクトリ構成

```text
INIAD-AIO/

├─ backend/
│  ├─ main.py
│  ├─ ai_module.py
│  ├─ database.py
│  ├─ search_backend.py
│  └─ aio.db

├─ frontend/
│  ├─ index.html
│  └─ style.css

├─ data/
│  └─ Obsidian_lecture/

└─ README.md
```

---

## セットアップ

### 仮想環境有効化

Windows

```powershell
.\.venv\Scripts\activate
```

### サーバー起動

```powershell
cd backend
uvicorn main:app --reload
```

### アクセス

```text
http://127.0.0.1:8000
```

---

## 現在の開発段階

### v0.05

実装済み

* FastAPI
* SQLite
* Gemini API
* Frontend UI
* Sources表示
* Enter送信
* Loading表示

### v0.1

予定

* Obsidian講義ノート投入
* 実データによる検索
* デモ版完成

### v0.2

予定

* MOOCs連携
* データ投入自動化

### v0.3

予定

* Embedding導入
* ベクトル検索

### v0.4

予定

* RAG基盤構築

### v1.0

予定

* プロダクト化
* UI改善
* 安定運用

---

## 現在の課題

* Obsidianデータ投入
* データ量不足
* MOOCs連携
* Embedding設計
* メンバー募集

---

## ライセンス

開発中

```
```
