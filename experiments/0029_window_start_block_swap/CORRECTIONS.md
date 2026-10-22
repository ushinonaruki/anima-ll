# 実験 0029 の事前登録への技術的な訂正（測定の前。README v0.2・protocol.yaml v0.2 に対して）

> 種別：**確定した事前登録（#127、merge `ec0fe034`）への技術的な訂正**。README・protocol.yaml は書き換えない（どちらも #127 のマージのまま。§0〜§14 も変えない）。この文書は、その 2 つのうちの食い違い・書き方の誤りを、**本番の測定の前に**どう読むかを固定する
> 作成：2026-10-23（Claude）。きっかけ：PR #128（道具）への ChatGPT の独立レビュー `5616356808`（修正必須 1 点と、非ブロッキングの 1 点）
> 適用：実験 0029 の本番（22001〜22020）・smoke（22101〜22106）・合成（22201〜22299）のすべての raw と report。**研究の問い・量・介入・判定の事象・閾値・水準・操作の確認の項目は変えない**
> Status：ChatGPT のレビュー待ち。この訂正の取り扱いが確定（PR #128 のマージ）するまで、本番の seed は実行しない

---

## C1. τ がある個体の raw の `swap.events`（README §2.6 の raw の表の `events` の行）

### 食い違い

| 箇所（#127 のまま） | 書いてあること |
|---|---|
| README §2.6 の raw の表、`events`（8 つの主の事象）の行 | τ がある：「§4.1 の真偽」、τ がない：「8 つすべて `false`。`not_outside_reason: "no_tau"` を付ける」 |
| README §9 の smoke の seed | 「操作の確認だけで、**判定の量は計算・表示・保存しない**。現象に関する数値（…τ の値…）も見ない」 |
| README §7 の冒頭（常設チェック D2） | 「必須の確認が 1 つでも成り立たなければ、実験全体を invalid とし、8 つの判定をどれもしない。**判定の量は計算も表示もしない**」。D2：操作の確認は「保存した真偽値ではなく、保存した生の記録から再検証する」 |
| protocol.yaml の `execution.per_seed.no_partial_judgment_quantities: true`・`aggregate_only_after: all_20_seeds_have_...` | 20 個体がそろい、記録が確かめられるまで判定の量を作らない |

§2.6 の表の `events` の行を「測定のときに raw に §4.1 の真偽を書く」と読むと、**smoke の raw に判定の量を保存する**ことになり（§9 に反する）、**操作の確認の前に判定の量を計算する**ことになる（§7・D2 に反する）。§2.6 は v0.2 で、τ がない個体の契約を足すために書いた表で、その `events` の行は、raw に書く値と、解析が個体ごとに記録する値を一つの列に混ぜていた（Claude の書き方の誤り）。

### 訂正（読み方の固定）

| | raw（world.py が測定のときに書く） | report（analyze.py が書く） |
|---|---|---|
| **τ がある個体** | `swap.events` ＝ **`null`**（測定では判定の量を計算しない） | すべての個体のすべての操作の確認が成り立った後に、**本番・合成のときだけ** §4.1 の真偽を計算し、`per_seed.<seed>.individual.events`（Wt・U の 8 つ）に書く。`not_outside_reason` は `null`。smoke・invalid のときは計算も表示もしない |
| **τ がない個体** | `swap.events` ＝ 8 つすべて `false` と `not_outside_reason: "no_tau"`（README §2.6 のまま。定義から決まり、現象の値を使わない） | 同じ 8 つの `false` と `no_tau` を `per_seed.<seed>.individual` に書く（本番・合成のとき） |

- README §2.6 の表の「§4.1 の真偽」は、**report の個体ごとの事象**の値を指すと読む。raw の `events` の形は上の表で固定し、analyze.py は raw がこの形であることを確かめる（τ があるのに raw の `events` が `null` でない raw は、§2.6 の「対応から外れた raw」として invalid）
- **変えないもの**：§4.1 の事象の定義（厳密な不等号・一方向と向きを問わない区別・等号と凍結は「外にない」）、§4.2〜§5 の判定と閾値（Wt 4・4・4・2、U 6・6・6・3）と水準、τ がない個体を分母 20 に残して 8 事象を「外にない」に数えること、§7 の操作の確認の項目、smoke で判定の量も現象の値も見ないこと

### この読み方を選ぶ理由

- §7・§9・D2・`no_partial_judgment_quantities` は、0013 以来の常設の規律（判定の量は確認の後で、生の記録から一度だけ作る）で、0023〜0028 の道具もすべてこの分け方（raw に判定の量を書かない）をとっている
- 逆の読み方（raw に §4.1 の真偽を書く）をとると、§9・§7 のほうを訂正しなければならず、smoke の盲検と invalid のときの規律が弱くなる

## C2. protocol.yaml の `clopper_pearson_95_of_h_over_20` の置き場所

- protocol.yaml（#127 のまま）では、`quantities.auxiliary.clopper_pearson_95_of_h_over_20`（8 つの h／20）が `quantities.auxiliary.when_no_tau` の下に入っている。v0.2 で `when_no_tau` を書き足したときの位置の誤り（Claude）で、v0.1 では `quantities.auxiliary.across_individuals` の下にあった
- **意味は README §6 の補助の表のとおり**：τ の有無に依らず、本番・合成で 8 つの判定の h／20 について Clopper–Pearson の 95% 区間を記録する（独立・同じ確率の二項モデルの前提に依る参考値。判定に使わない）。analyze.py は家族の判定ごとに `clopper_pearson_95_of_h_over_n` として書く
- alignment.py は protocol.yaml をそのままの形で照合する（protocol.yaml は書き換えない）

## 測定の前であること・既に見たもの・seed

- **本番の seed 22001〜22020 は、どれも実行していない**。本番の raw・判定の量は誰も見ていない
- **smoke 22101〜22106**：道具の commit `254ec02`（PR #128 の head）で実行済み（6 個体 completed）。raw の `events` はこの訂正の形（τ がある個体は `null`）で保存されている。解析は smoke のモードで、操作の確認の結果（fail・ok だけ。pass と not_applicable を区別しない）しか表示していない。判定の量も、τ の値・τ の有無・発火の数などの現象の値も、計算・表示していない
- **合成 22201〜22250・22299**：契約テストの小さな Plan（SMALL・NOTAU）での値で、本番の Plan ではない
- この訂正は、見た値（smoke の操作の確認の結果、合成の値）を見て選んだものではない。きっかけは道具のレビューで、raw の形と文書の食い違いを指摘されたこと
- **新しい seed の範囲・新しい事前登録の版は要しない**と判断する：訂正は raw と report のどちらにどの値を書くかだけで、測定の手順・量・判定の規則・どの seed の値にも影響しない。本番は未実行で、smoke の raw はこの訂正の形と同じなので、smoke もやり直さない（world.py・run.py・guard.py は `254ec02` から変えていない）

## 道具の側

- world.py・run.py・guard.py：`254ec02` のまま（C1 の raw の形はもともとこの形）
- analyze.py：raw の形の確認は C1 のとおり（変更なし）。report に、適用した訂正（この文書のパスと SHA-256）を `preregistration_corrections` として書く
- alignment.py：この文書の SHA-256 を固定値と照合する（マージの後に書き換えたら、実行・解析が止まる）
- 契約テスト：この文書があること、report に記録されること、τ がある個体の raw の `events` が `null` で report の `events` が §4.1 の真偽になること、smoke の report に事象がないことを確かめる
