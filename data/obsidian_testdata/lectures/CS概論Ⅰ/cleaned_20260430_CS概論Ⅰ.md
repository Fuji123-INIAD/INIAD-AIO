---
domain: lecture
classification: restricted
status: reference
course: "[[CS概論Ⅰ]]"
created: 2026-04-30
updated: 2026-04-30
tags:
  - INIAD
  - lecture
  - python
  - function
  - list
  - collection
  - iteration
  - mutable
ai_scope: local_only
rag_scope: local_only
cloud_upload: false
---

# CS概論Ⅰ

## 関数の戻り値

関数は、処理した結果を **戻り値（return value）** として返せる。

基本形：

> def 関数名(引数):  
> 　　return 計算結果

例：

> def average(x, y):  
> 　　return (x + y) / 2

使用例：

> print(average(10, 20))

---

## 単位変換関数

計算結果を返す関数の例。

### ドル→円

> def dollar_to_yen(d):  
> 　　return d * 111.2

---

### km→mile

1 mile = 1.609 km

> def km_to_mile(d):  
> 　　return d / 1.609

---

## 燃費変換

アメリカ：

> MPG（mile per gallon）

日本：

> km/L

変換に必要な情報：

- 1 mile = 1.609 km
- 1 gallon = 3.785 L

変換：

> def mpg_to_kmpl(mpg):  
> 　　return mpg * 1.609 / 3.785

---

## 文字列を返す関数

return は数値だけでなく文字列も返せる。

例：

姓名を連結する。

> def full_name(first_name, family_name):  
> 　　return first_name + " " + family_name

使用例：

> print(full_name("Ken", "Sakamura"))

---

## 二次方程式の解

大きい方の解を返す。

公式：


::contentReference[oaicite:0]{index=0}


例：

> def larger_root(a, b, c):  
> 　　x1 = (-b + (b**2 - 4*a*c)**0.5) / (2*a)  
> 　　x2 = (-b - (b**2 - 4*a*c)**0.5) / (2*a)  
> 　　return max(x1, x2)

注意：

関数内部で `print()` するのではなく、

**return で返すこと。**

---

# コレクション

複数の値をまとめて扱う仕組み。

代表例：

- list

---

## リスト

複数の値を順番に格納する。

> fruits = ["apple", "banana", "orange"]

---

## 添字（index）

リストの要素を取り出す。

Pythonは **0始まり（0-origin）**。

> print(fruits[0])

結果：

> apple

---

## 月名変換

> def month_str(m):  
> 　　months = [  
> 　　　　"January", "February", "March",  
> 　　　　"April", "May", "June",  
> 　　　　"July", "August", "September",  
> 　　　　"October", "November", "December"  
> 　　]  
> 　　return months[m - 1]

注意：

人間の月は1始まりだが、リストは0始まり。

そのため：

> m - 1

---

## リストの要素変更

> fruits = ["apple", "banana", "orange"]  
> fruits[1] = "grape"

結果：

> ["apple", "grape", "orange"]

---

## リストの長さ

> len(fruits)

---

## 最大・最小・合計

> max(nums)  
> min(nums)  
> sum(nums)

---

## 平均

> def average(nums):  
> 　　return sum(nums) / len(nums)

---

# 二次元リスト

リストの中にリストを入れられる。

> scores = [  
> 　　[72, 60, 84],  
> 　　[67, 91, 80]  
> ]

アクセス：

> scores[1][0]

結果：

> 67

---

# 列挙（for）

リストから1つずつ取り出す。

基本形：

> for x in list:  
> 　　処理

例：

> for fruit in fruits:  
> 　　print(fruit)

結果：

> apple  
> banana  
> orange

---

## 文字列連結

> def concat_words(words):  
> 　　result = ""  
> 　　for word in words:  
> 　　　　result += word  
> 　　return result

重要パターン：

1. 空の変数を用意
2. forで取り出す
3. 追加していく

---

## 奇数抽出

> def odd_numbers(nums):  
> 　　result = []  
> 　　for n in nums:  
> 　　　　if n % 2 == 1:  
> 　　　　　　result.append(n)  
> 　　return result

重要パターン：

> 空リストを作る → 条件に合うものを append

かなり頻出。

---

# リスト操作メソッド

## append

末尾追加。

> nums.append(4)

---

## pop

取り出して削除。

> nums.pop(1)

---

## index

位置検索。

> nums.index(3)

---

## copy

複製。

> b = a.copy()

---

# Mutable（可変）

リストは **mutable（可変）**。

中身を書き換えられる。

---

## aliasing

> a = [1, 2, 3]  
> b = a

これはコピーではない。

同じリストに別名を付けている。

そのため：

> b[1] = 4

すると、

> a

も変化する。

結果：

> [1, 4, 3]

---

## 独立コピー

> b = a.copy()

これなら独立。

---

## 気づき

- 関数は print ではなく return が本質
- リストは Pythonで最重要のコレクション
- 0-origin に慣れる必要がある
- for による列挙は頻出
- 「空リスト＋append」は定番パターン
- mutable と aliasing はバグの原因になりやすい
