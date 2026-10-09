# 接続の状態（ConnectionState）と発火の出来事（ActivityEvent）の境界 仕様 v0.1（案）

> 作成：2026-10-10。Status：**境界の仕様の案。実装はまだしない。可塑性の規則の式・値は決めない**
> 前提：価値を使わない可塑性の設計監査（`docs/value-free-plasticity-audit.md` v0.2.1）§3 の 1・2、§5 の 2・3。内部表現の原則（`docs/internal-representation-principles.md`）R1〜R6
> 似た文書：計算資源境界 仕様（`docs/compute-boundary-spec.md`）、ActionIntent の境界（`docs/action-intent-boundary.md`）
> この文書が答える問い：**変わる重みを誰が持ち、いつ読まれ、接続ごとの可塑性は送り手・受け手の活動をどう参照するか。そのあいだ Runtime は何をして、何をしないか**

---

## 1. いま（minimal-v2）の実装の事実

仕様の前に、今のコードで重みと発火がどう流れているかを書く。

| 項目 | 今の実装 |
|---|---|
| 重みの置き場所 | 脳の設計図（Manifest）の `ProjectionSpec.weight`。個体の状態には無い |
| 重みを読む瞬間 | **送り手が Delta を出した Pulse t**。Runtime の `DeltaCanonicalizer` が Manifest から重みを読み、`StateDelta.projection_weight` に書き込む |
| 重みが効く瞬間 | **Pulse t＋1**。受け手の Unit が `new_deltas()`（前の Pulse に確定した Delta）の `projection_weight` を足して刺激にする |
| 発火の情報 | Unit の中の `ActivityDynamics.advance` が返す `Firing`。**Unit の外には出ない**（出力の部品に渡され、部品が何を出すかを決める） |
| 発火と Delta の関係 | 同じではない。relay は「新しく届いた Delta の数」だけ Delta を出す（届いた数が 0 なら、発火しても何も出ない。内在的駆動だけで発火したときがこれ）。kernel_request は発火で Kernel を呼び、Delta は結果が戻ったあとに別の Pulse で出る |
| 個体の保存 | `IndividualSnapshot.units`（Unit の私的な状態）だけ。接続の状態は無い |

つまり今は、**重みは Runtime が設計図から読んで配っており、発火は Unit の外から見えない**。可塑性を入れるには、この 2 つを変える必要がある（監査 §4）。

## 2. 最初に固定すること（3 点）

| 番号 | 固定すること |
|---|---|
| **B1** | **接続の状態（ConnectionState）は、個体の Neuroarchitecture に属する**。Life History として変わり、個体と一緒に保存される。Unit には属さない。Runtime にも属さない |
| **B2** | **発火の出来事（ActivityEvent）は、Neuroarchitecture の中で成立する認知の出来事**。Unit の力学が「発火した」と決めた時点で成立する。Runtime・Kernel・Environment が判定したり生成したりしない |
| **B3** | **Runtime は、どちらの意味も判断せず、更新もしない**。必要なら、決まった手順で機械的に運ぶ・渡す・記録するだけ |

## 3. 接続の状態（ConnectionState）

### 3.1 何を持つか

```text
ConnectionState
├─ connection_id    … 接続を指す ID（送り手 ID・送り手の出力路・受け手 ID の組から決まる）
├─ weight           … 今の重み（Life History で変わる）
└─ rule_state       … 可塑性の規則が使う、接続ごとの状態（例：発火の痕跡）。中身は規則が決める
```

- 接続の **ID は意味の名前を持たない**（今の Projection と同じ。送り手と受け手の ID の組だけ）
- 重みの初期値・可塑性の規則・規則のパラメータは **脳の設計図に書く**。個体が生まれるときに、設計図から ConnectionState を作る
- 規則のパラメータは、隠れた既定値を置かない（`MissingParameter` の方針と同じ）。時間に関するものは秒で書く（台帳 §3.9）

### 3.2 置き場所

```text
Manifest（脳の設計図。変わらない）
├─ 初期の配線（topology）
├─ 初期の重み
└─ 可塑性の規則とそのパラメータ
個体の Neuroarchitecture の状態（Life History で変わる）
├─ Unit の状態（activity・順応 など。今もある）
└─ 接続の状態（ConnectionState。新しく足す）
Runtime
└─ 決まった手順で運ぶだけ
```

### 3.3 保存

- `IndividualSnapshot` に `connections`（ConnectionState の一覧）を足す
- 保存から再開したとき、重みは **設計図の初期値ではなく、保存された値** を使う
- 可塑性が無い（規則が「変えない」）ときは、保存された値は初期値のまま。今のスナップショットとの互換は、`connections` が無ければ設計図の初期値で作る、で保つ

## 4. 発火の出来事（ActivityEvent）

### 4.1 何を持つか

```text
ActivityEvent
├─ source_id   … 発火した Unit
└─ pulse       … 発火した Pulse
```

- **中身（payload）を持たない**。何に反応して発火したかも持たない
- 発火の強さ（`Firing.strength`）を含めるかは未決定（§8 の 2）。最初は「起きた／起きない」と Pulse だけにする

### 4.2 どこで成立するか

```text
Unit の力学（ActivityDynamics.advance）が発火を返す
  ↓
その時点で、Neuroarchitecture の中で ActivityEvent が成立する
  ↓
Unit は、その Pulse の結果（UnitStepResult）に「発火した」ことを含めて返す
  ↓
Runtime は、それを受け取り、決まった手順で、可塑性の仕組みに渡し、記録する
```

- **出力の部品とは独立に成立する**。relay が何も出さなかった発火（届いた Delta が 0）も、kernel_request で結果がまだ戻っていない発火も、同じく 1 つの ActivityEvent になる。§1 の「発火と Delta は同じではない」を解消するため
- Runtime は「この Delta が来たから発火だろう」と推測しない。Unit が返した発火の事実をそのまま使う

### 4.3 Delta との関係（方式の決定）

監査 §5 の 3 で「出力の部品として足すか、Runtime の配送で運ぶか」を未決定にしていた。ここでは **Delta とは別の経路にする** 案をとる。

| | 案 A：出力の部品が中身のない Delta を出す | **案 B：Delta とは別の ActivityEvent（採る案）** |
|---|---|---|
| 発火との対応 | 部品ごとに違いうる。relay と組み合わせると、1 回の発火が「届いた数」の Delta になる | 1 回の発火 ＝ 1 つの出来事 |
| 受け手の刺激への影響 | 中身のない Delta も `new_deltas()` に入り、**刺激が変わる**（minimal-v2 の振る舞いが変わる） | 刺激の計算に入らないので、**可塑性を無効にすれば今と同じ振る舞い** |
| Delta の意味 | 「内容を運ぶもの」と「発火を知らせるもの」が混ざる | Delta は内容、ActivityEvent は活動、と分かれる |

案 B にすると、「発火の出来事を刺激（受け手を駆動するもの）にも使うか」という別の問いが残る（§8 の 1）。これは力学そのものの変更なので、この仕様では決めず、**今の刺激（Delta の数 × 重み）を変えない**。

## 5. 重みをいつ読むか

### 5.1 案

**重みは、受け手が刺激を計算する Pulse に、その Pulse の冒頭で固定した接続の状態から読む**（読む瞬間を「送り手が Delta を出したとき」から「受け手が受け取ったとき」に移す）。

```text
Pulse t
  ├─ 冒頭：BrainState と ConnectionState をまとめて固定（スナップショット）
  ├─ 各 Unit：届いた Delta × 固定した重み で刺激を計算し、力学を進める
  │           発火したら ActivityEvent が成立する
  └─ 境界：可塑性の規則が ActivityEvent を使って ConnectionState を更新する
           更新は Pulse t＋1 の冒頭の固定から見える
```

### 5.2 理由

- **同じ Pulse の中で順番に依存しない**：重みの更新は境界で一度だけ反映する。Unit を処理する順番で結果が変わらない（今の Pulse の境界の考え方と同じ）
- **Delta が認知の状態を持たない**：重みは接続の状態であって、送られた内容の属性ではない。今の `StateDelta.projection_weight` は、記録のために残すか、外すかを実装のときに決める（残すなら「送られた Pulse の重み」の記録であり、刺激の計算には使わない）
- **可塑性が無いとき、今と同じ**：重みが変わらなければ、どちらの瞬間に読んでも値は同じ。minimal-v2 の結果は変わらない（§7 の契約テスト）

### 5.3 Runtime がすること・しないこと

- する：Pulse の冒頭に ConnectionState を固定する、受け手の View を作るときにその Unit への接続の重みを一緒に渡す、境界で可塑性の仕組みを呼ぶ、変化を記録する
- しない：重みの値を決める・変える、どの接続を変えるか選ぶ、ActivityEvent を作る・消す・選ぶ

これは今、Runtime が Unit の `tick` を呼ぶが Unit の中身を決めないのと同じ関係である。

## 6. 接続ごとの可塑性は何を参照するか

### 6.1 読んでよいもの

ある接続（送り手 S → 受け手 T）の規則が読んでよいのは、次だけ。

| 読むもの | 由来 |
|---|---|
| S の ActivityEvent（いつ発火したか） | Neuroarchitecture |
| T の ActivityEvent（いつ発火したか） | Neuroarchitecture |
| この接続の ConnectionState（weight・rule_state） | Neuroarchitecture |
| 経過時間（Pulse の数、または秒） | Pulse の時計 |

### 6.2 読んではいけないもの

- Delta の中身（payload）・種類（kind）
- Runtime の状態（列・待ち時間・Kernel の速さ・失敗）
- 環境のラベル、Unit や接続の名前
- ほかの接続の状態（**ただし**、安定化の方式によっては「T に入る接続の重みの合計」などを読む必要が出る。これは T にとって局所的な情報なので、安定化を決めるときに、許すかどうかをあらためて決める。§8 の 4）

### 6.3 時間の差の定義

- 「前」「後」は **S と T の ActivityEvent の Pulse を直接比べる**。Delta がいつ届いたかでは比べない（§1 のとおり、発火と Delta は一致しないため）
- 今の配送では、S が Pulse t に出した Delta は t＋1 に T に届く。したがって **S の発火が T の発火の原因になりうる最短の差は 1 Pulse**。同じ Pulse の発火（差 0）は、この接続を通った因果ではない
- P1（相関）を「差 0 を含む窓」、P2（順序）を「差 1 以上の向きのある窓」とみるか、一つの窓にまとめるかは、規則を決めるときに決める（監査 §5 の 1）

## 7. 契約テストの候補（実装するとき）

| 番号 | 確かめること |
|---|---|
| T1 | **可塑性を無効にすると、今の minimal-v2 と同じ結果になる**（同じ seed で Delta の列・発火の列が一致。実験 0007・0010 の再現） |
| T2 | ActivityEvent は Unit の力学の発火からだけ生まれる。発火の数と ActivityEvent の数が一致する（relay が何も出さない発火も含む） |
| T3 | Runtime のモジュールが ConnectionState の値を書き換えない（アーキテクチャのテスト：書き込みは可塑性の仕組みからだけ） |
| T4 | 同じ Pulse の中で Unit の処理の順番を入れ替えても、重みの更新の結果が変わらない |
| T5 | 可塑性の規則に Delta の payload・Runtime の状態が渡らない（規則の入力の型で保証する） |
| T6 | 保存して再開すると、重みが保存された値から続く |

## 8. 未決定の問い（この文書では決めない）

1. **発火の出来事を、受け手の刺激にも使うか**：使うなら、内容を運ぶ Delta と、駆動を運ぶ活動、という分け方になる。力学の変更なので、事前登録した実験で比べてから決める
2. **ActivityEvent に発火の強さを含めるか**：最初は含めない
3. **Receptor から来る接続の「送り手の活動」**：Receptor は Unit ではなく、力学の発火を持たない。感覚の Delta が生まれたことを、送り手の活動とみなすかを、受け身の人工世界を設計するときに決める
4. **安定化の方式**：上限・正規化・ゆっくり戻る など。受け手に入る接続をまとめて見る方式を許すかも、ここで決める
5. **Effector への接続**：受け手に力学が無いので、可塑性の対象にしない（と思われる）。ActionIntent の設計と一緒に確定する
6. **接続の生成・消滅**：対象外。ConnectionState の形は、将来それを扱えるようにしておく（vault「経験依存の Unit 構造変化（仮案）」）
