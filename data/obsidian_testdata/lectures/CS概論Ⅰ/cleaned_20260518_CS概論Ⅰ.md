---
domain: lecture
classification: restricted
status: reference
course: "[[CS概論Ⅰ]]"
created: 2026-05-18
updated: 2026-05-21
tags:
  - INIAD
  - lecture
  - python
  - module
  - dictionary
  - tuple
  - collection
  - datetime
  - random
  - repl
ai_scope: local_only
rag_scope: local_only
cloud_upload: false
---

# CS概論Ⅰ

## 中間試験関連

### 試験範囲の確認

- ワークシートや確認クイズはGoogle Drive上に配置済み
- 試験範囲部分まではアップロード済み
- 自主学習に活用すること

### 採点済み例題

- 例題の採点結果は確認可能
- 緑: 正解
- 赤: 不正解
- 採点プログラムは授業時間後の自主解答には未対応
- 正しいのに誤判定と思われる場合は質問可能

### 中間試験で注意する点

#### よくあるミス

- 大文字・小文字の違い
- 全角スペース混入
- 関数名ミス
- コード貼り付け範囲ミス
- 一部のみ提出される問題

#### 重要

- 動作確認後に提出内容を再確認する
- 指定された形式を厳密に守る

---

# 前回の復習

## 関数とリスト操作

### 文字列連結関数

```python
def to_juice(vegetable):
    return vegetable + "juice"
```

### ポイント

- `return` は値を返す
- 引数に文字列を渡して加工可能
- `for` 文でリストから順番に取り出せる

---

## 素数判定

### 基本方針

素数:

> 1と自分自身以外で割り切れない数

### 実装例

```python
def is_prime(x):
    for i in range(2, x):
        if x % i == 0:
            return False
    return True
```

### ポイント

- `return` した時点で関数終了
- `range(2, x)` は `2以上x未満`
- 1つでも割り切れたら素数ではない

---

## 共通要素探索

### 目的

2つのリストに共通する要素を抽出する。

### 実装方針

- 二重ループ
- 条件一致時に追加
- `break` で探索終了

### 実装例

```python
def overlap(xs, ys):
    result = []

    for x in xs:
        for y in ys:
            if x == y:
                result.append(x)
                break

    return result
```

---

# 文字カウント問題

## 問題

文字列中に特定文字が何回出現するか数える。

### 実装例

```python
def count_char(line, c):
    count = 0

    for i in line:
        if i == c:
            count += 1

    return count
```

---

## 重要パターン

### カウンター変数

```python
count = 0
```

### 条件成立時のみ増加

```python
count += 1
```

### 基本構造

```python
for 要素 in コレクション:
    条件:
        カウント増加
```

---

# REPLとHelpシステム

## REPL

Pythonを対話的に実行する環境。

### 特徴

- 即時実行
- print不要
- 電卓のように使える

### 例

```python
1 + 2
```

結果:

```python
3
```

---

## help関数

### 使用例

```python
help(list.index)
```

### 用途

- メソッド説明確認
- 引数確認
- Python標準機能調査

---

## 中間試験でのhelp利用

試験環境でも `help()` 使用可能。

例:

```python
help(list.append)
```

---

# モジュール

## モジュールとは

関数・変数などをまとめた再利用可能なプログラム部品。

## import

### 基本形

```python
import math
```

### 使用方法

```python
math.pi
math.gcd(12, 8)
```

---

## mathモジュール

### 円周率

```python
math.pi
```

### 最大公約数

```python
math.gcd(12, 8)
```

結果:

```python
4
```

---

# randomモジュール

## ランダム選択

### random.choice

```python
random.choice(list)
```

---

## おみくじ例

```python
import random

results = [
    "大吉",
    "中吉",
    "小吉",
    "凶"
]

print(random.choice(results))
```

---

# datetimeモジュール

## 現在時刻取得

### 基本形

```python
import datetime

t = datetime.datetime.now()
```

### 時刻取得

```python
t.hour
t.minute
t.second
```

---

## 実行例

```python
print(t.hour)
print(t.minute)
print(t.second)
```

---

# importの別形式

## as

### 別名指定

```python
import datetime as d
```

---

## from import

### 必要部分のみ読み込み

```python
from datetime import datetime
```

---

## 非推奨

```python
from module import *
```

### 理由

- 名前衝突
- 可読性低下
- バグ原因

---

# タプル(tuple)

## 特徴

- リストに似る
- immutable（変更不可）

## 作成

```python
t = (100, 200, 300)
```

---

## 参照

```python
t[0]
```

---

## 変更不可

```python
t[0] = 3
```

これはエラー。

---

## 用途

### 複数値のまとめ

- 座標
- 戻り値
- 固定データ

---

# 中点計算

## 実装例

```python
def midpoint(p1, p2):
    x1, y1 = p1
    x2, y2 = p2

    return (
        (x1 + x2) / 2,
        (y1 + y2) / 2
    )
```

---

# 辞書(dict)

## 概要

キーと値の対応関係を持つコレクション。

## 作成

```python
trans_data = {
    "apple": "りんご",
    "orange": "みかん"
}
```

---

## 取得

```python
trans_data["apple"]
```

結果:

```python
りんご
```

---

## get

存在しないキーでもエラー回避。

```python
trans_data.get("melon")
```

---

## 要素追加

```python
trans_data["banana"] = "バナナ"
```

---

## 削除

```python
del trans_data["banana"]
```

---

# in演算子

## 存在確認

```python
"apple" in trans_data
```

## 否定

```python
"melon" not in trans_data
```

---

# 文字出現回数カウント(dict版)

## 実装例

```python
def count_chars(s):
    result = {}

    for c in s:
        if c in result:
            result[c] += 1
        else:
            result[c] = 1

    return result
```

---

# dictの列挙

## キー列挙

```python
for k in d:
```

---

## 値列挙

```python
for v in d.values():
```

---

## 両方列挙

```python
for k, v in d.items():
```

---

# 重要ポイントまとめ

## Python重要概念

- 関数
- return
- for文
- range
- list
- tuple
- dict
- import
- module
- class
- method

---

## 特に重要

### パターン理解

- カウンター
- 探索
- 条件判定
- 二重ループ
- 辞書更新

### モジュール利用

- `math`
- `random`
- `datetime`

### デバッグ

- `print()` で途中確認
- `help()` 活用

---

## 試験向け注意

- スペルミス注意
- インデント注意
- 全角スペース注意
- 提出前確認必須