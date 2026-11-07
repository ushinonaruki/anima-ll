# AS2b の最小の研究用の道具（②a）

> 契約：`docs/as2b-minimal-implementation-contract.md`（#176、main `6ccec47`。以下「契約」）
> 契約テスト：`tests/integration/test_as2b_contract.py`
>
> Status：**道具と契約テストだけ。** 正式な実験・前方の関門・事前登録・seed の実行ではない。Core（Unit の力学・可塑性の規則・確定したパラメータ・Pulse の順序）は変えていない

## 1. 部品と契約の対応

| 部品 | 中身 | 契約 |
|---|---|---|
| `I2Decider` | 二つの源が共有する I2 の決定の部品。Pulse ごとの発火の有無の報告が二つそろったら対称に決め、勝ちなら「翌 Pulse に勝った源の口が出す」を予定する。層 A の記録を持つ | EC-2〜EC-5・EC-7・EC-10、§2.5・§2.8 |
| `CompetitionTap` | 源を包む競合の口。中の Unit の tick → 予定があれば意図を 1 つ足す → 発火の有無を報告する | EC-1・EC-5・EC-6・EC-8 |
| `AS2bWorld` | 手がかりの予約、規則 c が指す行動 ID の意図にだけ手がかりの Receptor へ結果、層 B の記録（Delta の識別子・出どころ・Pulse・行動 ID） | WB-1〜WB-9 |
| `AS2bEffector` | 意図の Delta を世界に渡すだけ | EC-9 |
| `TrialSchedule` | 手がかりと窓を一つの予定から作る。命題 T-4 を組み立ての時に調べる | WB-2・WB-5・CT-W2 |
| `build`・`clone`・`sigma`・`replay_schedule` | 組み立て、丸ごとの複製（M1）、Σ（AS1 の Σ ＋ 出口）、再生の予定 | §4・§5・§6 |
| `audit` | 層 A と層 B の外部の突合。脳にも世界にも戻さない | CT-E10 |

AS1 の道具から、接続の口の包み（FB-1・FREEZE）・移植・来歴のログ・再生の予定・Σ の違いを、そのまま使う。

## 2. 契約テストの対応

| 契約テスト | テストの関数 |
|---|---|
| CT-E1（呼び出しの順） | `test_ct_e1_*`（台本と、乱数で作った 300 の台本を両方の順で） |
| CT-E2（鏡像） | `test_ct_e2_*` |
| CT-E3（余分な意図なし） | `test_ct_e3_*`（独立に書いた手順と照合） |
| CT-E4（中の Unit を変えない） | `test_ct_e4_*`（本物の Unit） |
| CT-E5・E6・E8 | `test_ct_e5_e6_e8_*`、`test_ct_e6_*` |
| CT-E7（乱数） | `test_ct_e7_*`、`test_roles_*` |
| CT-E9（報告の完全性・読むもの） | `test_ct_e9_*` |
| CT-E10（二層の突合）・EC-1 | `test_ec1_ct_e10_*`、`test_ct_e10_*` |
| CT-W1〜W5 | `test_ct_w1_*`〜`test_ct_w5_*`、`test_w1_*` |
| CT-Σ1〜Σ5・CT-ΣE1〜ΣE4 | `test_ct_sigma*` |
| CT-G1a′〜c′ | `test_ct_g1a_prime_*`〜`test_ct_g1c_prime_*` |
| LC1・空の介入 | `test_lc1_*`、`test_ci1_*` |

- 道具の確認の seed は 9101〜9106。予定は道具の確認用（窓が広い）で、関門の宣言（`experiments/0038_as2b_forward_gate/gate_declaration.json`）の値では走らせない
- テストは構造だけを確かめ、選択の数・割合・時間の変化・規則 c の違う本体の差を計算も表示もしない
