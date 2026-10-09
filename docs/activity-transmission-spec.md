# 活動の伝達・感覚の駆動・中身の運搬の境界 仕様 v0.2（案）

> 作成：2026-10-10（v0.2：ChatGPT レビュー反映。C2 を「接続・外界から入る外からの駆動は ActivityEvent・SensoryEvent からだけ」に直し、内部の力学（内在的駆動・減衰・順応）と分けた。中身の出どころを出力の部品と Receptor の両方とした。Effector には活動の駆動を届けない、を §7 で固定した。T3 を実装の形ではなく、運び方の意味が同じことに直した）。Status：**境界の仕様の案。実装はまだしない。値は決めない**
> 前提：
> - 可塑性の規則・安定化・受け身の人工世界の監査（`docs/plasticity-rule-audit.md` v0.2）§4.4：(c2)「活動の伝達と中身の運搬を分ける」を最有力とし、可塑性の実験（0012）とは分けて先に仕様・実装・新しい基準の測定を行う
> - 接続の状態と発火の出来事の境界 仕様（`docs/connection-state-spec.md` v0.2）：B1〜B3、重みは伝達の成立時点で凍結、学習は遡らない
> - ActionIntent の境界（`docs/action-intent-boundary.md`）、計算資源境界 仕様（`docs/compute-boundary-spec.md`）
>
> この文書が答える問い：**Unit を動かすもの（駆動）と、Unit に届く材料（中身）を分けたとき、外界・Unit・Runtime はそれぞれ何を成立させ、何を運び、何をしないか**

---

## 1. いま（minimal-v2）の実装の事実

| 項目 | 今の実装 |
|---|---|
| Unit を動かすもの | 前の Pulse に届いた Delta の数 × 重み（`GenericCognitiveUnit.tick`）。Delta が「中身」と「駆動」を兼ねている |
| 感覚の入口 | Receptor が `ExternalEvent`（receptor_id・payload）を出し、Runtime の `ExternalEventIntake` が中身の Delta に変える。その Delta が届いた数で、最初の Unit が動く |
| Unit の発火の外への出方 | 出力の部品しだい。relay は届いた Delta の数だけ中身を転送する（届いていなければ何も出さない）。kernel_request は計算を要求し、結果が戻った Pulse に中身の Delta を出す |
| Kernel の結果 | 中身の Delta として出て、届いた先の Unit を **駆動もする** |

(c2) を採ると、「Delta が駆動を兼ねる」ところがなくなる。そのとき、上の表の **感覚の入口** と **Kernel の結果** の扱いも同時に決め直す必要がある。

## 2. 3 つの流れを分ける

```text
Unit → Unit        … 活動の伝達：ActivityEvent × 接続の重み → 受け手の activity を駆動
Receptor → Unit    … 感覚の駆動：SensoryEvent × 接続の重み → 受け手の activity を駆動
Delta              … 中身・材料を運ぶだけ。受け手を駆動しない
```

| 番号 | 契約 |
|---|---|
| **C1** | **Delta は受け手を駆動しない**。Unit の刺激の計算に、Delta の数・重み・中身を使わない。Delta は受容野に届き、出力の部品（relay の転送、kernel_request の入力）が材料として使うだけ |
| **C2** | **接続・外界から入る外からの駆動は、送り手の側で成立した出来事からだけ生じる**：Unit の ActivityEvent（Neuroarchitecture で成立）と、Receptor の SensoryEvent（Environment で成立）。どちらも、成立した側が決める。Runtime は作らない。**Unit の内部の力学（内在的駆動・減衰・順応）は、これとは別に今までどおり働く**（下の図） |
| **C3** | **Runtime は、どれが刺激かを意味で判断しない**。成立済みの出来事を、接続に沿って機械的に運ぶ。「Receptor 由来だから刺激」「この Delta は大事だから刺激」のような判断はしない |
| **C4** | **Kernel の結果は駆動しない**。結果は中身の Delta としてだけ出る（C1）。Kernel が返ったことで受け手が動く、という経路はなくなる。今は LLM が空の出力・待ち時間・失敗の 3 つを通じて活動の力学に入っているが、(c2) では **LLM は活動の力学に入らなくなり、中身（受け手の kernel_request の入力）にだけ影響する**。これは (c2) の直接の帰結として新しい基準の測定で確かめる |

Unit の activity を動かすものの切り分け：

```text
Unit の activity
├─ 内部の力学（Unit の中で完結。外から何も来なくても働く）
│   ├─ 内在的駆動（intrinsic_drive）
│   ├─ 減衰（decay）
│   └─ 順応（adaptation）
│
└─ 外からの駆動（接続・外界から入る）
    ├─ ActivityEvent × 接続の重み（Unit → Unit）
    └─ SensoryEvent × 接続の重み（Receptor → Unit）
```

Delta（中身）は、このどちらにも入らない（C1）。

## 3. 大きな論点：感覚の駆動と活動の伝達を、同じ抽象で扱うか

### 3.1 候補

| | 案 X：まったく同じ型にする | **案 Y：成立する型は分け、運び方は一つにする（採る案）** | 案 Z：型も運び方も分ける |
|---|---|---|---|
| 成立する場所 | Receptor も「発火」する（Receptor を Unit のように扱う） | ActivityEvent は Neuroarchitecture、SensoryEvent は Environment で成立 | 同左 |
| 運び方 | 一つ | **一つ**：「送り手で成立した出来事 × 接続の重み → 受け手の駆動」 | 二つ（感覚の駆動の経路と、Unit どうしの経路） |
| 受け手から見て | 区別なし | **区別なし**（どちらも、接続を通って届いた駆動） | 区別あり |
| 問題 | Receptor は力学（activity・閾値）を持たない。「発火」と呼ぶと、外界の層に Neuroarchitecture の概念を持ち込む | 型が 2 つ要る | Runtime が経路を出どころで分けることになり、C3 の「出どころで判断しない」に近づく。受け手の Unit も 2 種類の駆動を区別して足す必要が出る |

### 3.2 案 Y を採る理由

- **成立する層が違うものは、違う型にする**：Unit の発火は Neuroarchitecture の認知の出来事（境界の仕様 B2）。感覚の出来事は Environment の Receptor が外界を受け取った事実（ActionIntent の境界の AI6・AI7 と同じく、外界の側の出来事）。同じ型にすると、どちらかの層に、もう一方の層の意味が漏れる
- **運び方を一つにすれば、Runtime は出どころで分岐しない**：Runtime がするのは「出来事の送り手 ID から接続を引き、成立時点の重みを凍結して、次の Pulse に受け手へ届ける」だけで、送り手が Unit か Receptor かで処理を変えない（C3）
- **受け手の Unit は区別しない**：受け手にとっては「接続を通って、重み付きの駆動が届いた」だけ。感覚か内部かは、どの接続から来たかという配線の違いであって、Unit の力学の違いではない（Unit に役割を持たせない、という今の方針と同じ）

### 3.3 運び方（共通）

```text
Pulse t
  ├─ 送り手で出来事が成立（Unit の ActivityEvent、または Receptor の SensoryEvent）
  ├─ Runtime：送り手 ID から接続を引き、Pulse t 冒頭に固定した ConnectionState の重みで凍結
  │            → 伝わる駆動（届く先・凍結した重み・成立した Pulse）を記録
  └─ 境界で確定
Pulse t＋1
  └─ 受け手：届いた駆動の重みの合計を刺激にして、力学を進める
```

- 届くまでの遅れは、今の Delta と同じ 1 Pulse（Pulse の境界）
- 重みの凍結と学習が遡らないことは、境界の仕様 §5 のとおり
- 中身の Delta も、同じ接続に沿って今までどおり運ばれる（§5）

## 4. 感覚の駆動（Receptor → Unit）の境界

### 4.1 どこで成立するか

```text
外界
  ↓
Receptor（Environment）が外界を受け取る
  → その時点で SensoryEvent が成立する（Environment の出来事）
  → 中身がある場合は、中身（material）も一緒に渡す
  ↓
Runtime：SensoryEvent を §3.3 の運び方で運ぶ。中身があれば、中身の Delta として運ぶ
```

- **SensoryEvent を成立させるのは Receptor（Environment）**。Runtime の `ExternalEventIntake` が「この入力は刺激にする／しない」を判断して作るのではない
- **中身があるかどうかも Receptor が決める**。人工世界の Receptor は中身なしで SensoryEvent だけを出してよい。console の Receptor は SensoryEvent と、入力された文章（中身）を出す。Runtime は、渡された中身をそのまま Delta にするだけで、中身から駆動を作ったり、駆動から中身を作ったりしない
- Receptor の出来事の型（今の `ExternalEvent`）を、「SensoryEvent と、任意の中身」に分ける形が候補。具体的なデータの形は実装のときに決める

### 4.2 SensoryEvent が持つもの

```text
SensoryEvent
├─ receptor_id
└─ pulse（成立した Pulse）
```

- 最初は ActivityEvent と同じく「起きた／起きない」だけにする
- **感覚の強さ**（同じ Receptor でも強い入力・弱い入力）を持たせるかは未決定（§8 の 1）。持たせるなら、強さを決めるのは Environment の側で、Runtime ではない

### 4.3 Receptor → Unit の接続

- 接続の状態（ConnectionState）としては、Unit → Unit と同じ形で持つ（重みは「感覚の駆動の結合の強さ」）
- 可塑性の対象にするかは別の問い。受け身の人工世界の実験では対象にしない（監査 §4.3）。これは学習の問題であって、駆動の問題はこの仕様で解決している

## 5. 中身の運搬（Delta）

- 中身（material）の出どころは 2 つ：

  ```text
  中身の出どころ
  ├─ Unit の出力の部品（relay の転送、kernel_request の結果）
  └─ Receptor（SensoryEvent に添えた、任意の中身。§4.1）
  ```

- Runtime は、どちらの中身も **意味を解釈せず**、確定（canonicalize：ID・発信元・Pulse・来歴を付ける）して、Manifest の接続に沿って運ぶ（route）だけ。受け手の受容野に届く
- 受容野・保持期間（delta_ttl_pulses）・根拠の照合（cited_delta_ids）は変えない
- 変わるのは、**受け手の刺激の計算に使われなくなる** ことだけ（C1）
- `StateDelta.projection_weight` は刺激に使われなくなる。記録として残すか外すかは実装のときに決める

## 6. 出力路（port）と活動の伝達

今の接続は「送り手 ID ＋ 出力路（port）→ 受け手」で定義されている。出力路は、出力の部品が中身をどこへ出すかの区別である。

- **発火は Unit 全体の出来事であって、出力路ごとの出来事ではない**。そこで案として、**ActivityEvent は、その Unit を送り手とするすべての接続に沿って伝わる**（出力路を問わない）とする
- 中身の Delta は、今までどおり出力路ごとに運ばれる
- 今の設計図では、すべての Unit の出力路は `main` の 1 つなので、この区別で振る舞いは変わらない。将来、出力路が複数になったとき、「活動の接続と中身の接続を別に宣言できるか」をあらためて決める（§8 の 3）

## 7. Effector への接続

**固定する：活動の駆動（ActivityEvent・SensoryEvent）は Unit にだけ届く。Unit の発火を、直接 Effector に流して行動にしない。**

```text
活動の駆動     → Unit だけ
Effector に届くもの → 中身（今の足場）／将来の ActionIntent
```

- Effector は力学（activity）を持たないので、駆動を受け取る意味がない
- それ以上に、`Unit の発火 → Effector` という経路を作ると、ActionIntent の境界で決めた `内部の状態 → ActionIntent → Effector`（AI1）を迂回する別の行動の経路になってしまう。これを防ぐために、ここで固定する
- 行動の意図（ActionIntent）がどう成立するかは、ActionIntent の境界のとおり未決定。この仕様では変えない

## 8. 未決定の問い（この文書では決めない）

1. **出来事に強さを持たせるか**：ActivityEvent の発火の強さ、SensoryEvent の感覚の強さ。最初はどちらも持たせない
2. **中身の Delta だけが届き、駆動が届かない Unit**：たとえば kernel_request の Unit は、自分が動かされなければ届いた中身を使わない。中身が届いたことを Unit が知る経路を別に作るかは、作らない（駆動と中身は別、を守る）。ただし、新しい基準の測定で何が起きたかを記録する
3. **活動の接続と中身の接続を別に宣言できるか**：今は同じ接続が両方を運ぶ（§6）

## 9. 実装するときに確かめること（契約テストの候補）

| 番号 | 確かめること |
|---|---|
| T1 | Delta の数・重み・中身を変えても、Unit の刺激が変わらない（C1） |
| T2 | 1 回の発火で、その Unit を送り手とする接続ごとに、ちょうど 1 つの駆動が届く（relay が中身を何も出さない発火でも届く） |
| T3 | 送り手が Unit でも Receptor でも、**運び方の意味が同じ**：接続に沿って届く、1 Pulse の遅れ、成立時点の重みの凍結（C3）。内部の実装で型を変換する場所に分岐があっても、Runtime が認知の意味を判断していなければ契約違反ではない |
| T8 | 活動の駆動が Effector に届かない（§7） |
| T4 | SensoryEvent は Receptor からだけ成立する。Runtime が中身から SensoryEvent を作らない（C2） |
| T5 | Kernel の結果が戻っても、受け手に駆動が届かない（C4） |
| T6 | 中身なしの SensoryEvent でも、受け手が駆動される。中身ありのときは、中身の Delta が今までどおり受容野に届く |
| T7 | 重みは伝達の成立時点で凍結される（境界の仕様 T7 と同じ） |

## 10. このあと

1. この仕様をレビューしてもらう
2. 実装する（minimal-v2 の設計図・力学のパラメータは変えない。変わるのは駆動の経路だけ）
3. **可塑性なしで、新しい基準（baseline）を測る**。0007〜0010 と同じ指標（入力なしで落ち着くか、発火の頻度、Unit ごとの発火）を、旧の結果と並べて記録する。旧の結果に合わせて値を調整しない。実験 0011（`experiments/0011_c2_baseline/`）として、実装の前に事前登録した
4. そのあと、可塑性の規則・安定化・人工世界を決めて 0012 を事前登録する（監査 §5）
