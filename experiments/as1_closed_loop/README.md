# AS1 の最小の研究用の道具（② 実装）

> 契約：[`docs/as1-minimal-implementation-contract.md`](../../docs/as1-minimal-implementation-contract.md)（#147 v0.3）
> Status：**研究用の道具と契約テストだけ。事前登録（③）・正式な実験（④）ではない。** 番号付きの実験のフォルダではない。ここで使う seed（契約テストの 9001〜9004）は道具の確認用で、結果（意図の頻度・時刻差・重みの向きなど）は何も判定しない

## 何が入っているか

| 部品（`as1.py`） | 契約 | 中身 |
|---|---|---|
| `as1_manifest_raw` | §1・IC-3 | C0 の設計図（`experiments/0012_passive_world/neuroarchitecture.yaml`。0028〜0033 と同じ）をそのまま読み、`interfaces.effectors` に `effector.y1` を 1 つ、`sK.intent → effector.y1` の投射を 3 本足すだけ。力学・可塑性・接続の値は変えない |
| `assign_roles` | WC-4・K2 | 源・受・他を、名前で分けた乱数の流れ（`as1-roles-{seed}`）で個体ごとに割り当て、来歴のログの RUN に記録する |
| `IntentSourceUnit` | IC-1〜IC-6 | 源の Unit を包み、中の Unit（同じ設計図・同じ seed で組み立てた GenericCognitiveUnit）の `tick` の結果に、発火した Pulse だけ意図 `X` の提案を出力路 `intent` で 1 つ足す。中の提案（relay）は変えない。状態を持たない |
| `AS1World`・`WorldEffector`・`WorldReceptor` | W-1・WC-1〜WC-6・W-2 | 予約の正本は世界だけ（識別子つきの多重集合）。Effector は意図を世界に渡すだけ、Receptor は drain のときに世界に問い合わせるだけ（予定を持たない）。L ≥ 2 を検査する。多重度は `per_reservation`（第一候補）と `merge` の両方を持つ（どちらにするかは③で決める）。`respond=False` で意図を記録するだけの開いたループになる |
| `InterventionConnections`・`Intervention`・`transplant`・`pair_sums` | §5・CT-I1〜I6 | `ConnectionStatePort` を包む。FB-1 は伝達に渡す写しの対象だけを 0 にする（中の重みは規則どおり）。FREEZE は `apply_activity` の後に対象の重みを宣言の時点の値へ公開の `import_state` で戻す（痕跡は `advance`〔第一候補〕か `hold`）。TRANSPLANT は宣言した重みだけを置き換える |
| `clone`・`sigma` | §4・CT-Σ1〜Σ5 | M1：個体・世界・介入の部品をまとめた `AS1System` を一つの `deepcopy` で写す（来歴のログだけ新しくする）。`sigma` は比べる状態 Σ（Unit・重み・痕跡・届く途中の駆動と Delta・識別子の発行・Runtime の内部の状態・時計・世界）を書き出す。Runtime の内部の状態は読むだけで書き換えない |

## 組み立ての口（契約 §5.2 の (a) を選んだ）

`src/anima_ll/bootstrap.py` の `build_application` に、省略可能な引数 `connection_wrapper` を一つ足した。

- **理由**：今の組み立ての口は `ConnectionStore(manifest)` を中で作り、Runtime に渡す接続の状態を差し替える口がない。研究用の道具の側で `PulseRuntime` を組み立て直す (b) は、組み立ての手順を二重に持つことになり、ずれの危険がある。Runtime の私的な属性を書き換える方法は使わない
- **C0 への非干渉**：引数を渡さなければ、Runtime と Lifecycle に渡すのはこれまでと同じ `ConnectionStore` そのもの（コードの道筋が同じ）。`Application.connections` も、包んだときでも中の `ConnectionStore` のまま。全体の pytest（既存の C0 実験の契約テストを含む）が変わらず通ることと、CT-I1（何も宣言しない包み ≡ 包みなし）で確かめた
- Unit の力学・可塑性の規則・パラメータ・Runtime の Pulse の順序は変えていない

## 契約テスト（`tests/integration/test_as1_contract.py`）

| テスト | 契約 |
|---|---|
| 設計図の差は Effector と intent の投射だけ | §1・IC-3 |
| 発火 1 回に意図 1 つ、源以外から出ない、Effector と世界が全部受けた | IC-1・IC-5 |
| 意図は `intent` から Effector だけへ、中身は `X` だけ、脳の中に Delta がない | IC-3・IC-6・CT-G1b |
| 中の提案はそのままで、発火のときだけ意図が 1 つ足される | IC-2 |
| L ＝ 1 と、drain 済みの Pulse への予約を止める | W-1 |
| 結果は意図の t ＋ L − 1 に結果の Receptor へ、源の Receptor には来ない、出来事は世界の正本どおり、Receptor は予定を持たない | WC-1・WC-1b・WC-2・K1 |
| 最小の AS1 では結果の予約が同じ Pulse に重ならない（L ＝ 2・3） | W-2 |
| 源が沈黙する個体には何も来ない | WC-2 |
| 取り消しは 1 つの予約だけに効き、出来事の数は多重度の規則に従う | WC-1c |
| 意図を無視し 0012 と同じ刺激の予定を与えると、0012 の C0 実験と発火・感覚・Unit の状態・重みが一致する（出口あり・なし） | WC-6・CT-G1a |
| 外の入力のない開いたループが、外の入力のない C0 と一致する | CT-G1a |
| 介入なしの複製が本体と一致し続ける、Runtime の内部の状態が働いていない | CT-Σ1・CT-Σ4 |
| 複製を変えても本体は変わらない | CT-Σ2 |
| 走らせ直し（M2）と複製（M1）が同じ Σ | CT-Σ3 |
| G-6：e の予約だけが消え、e の出来事が 1 つ消え、ほかの感覚は最初の意図まで同じ。`merge` で同じ Pulse に外の刺激があれば出来事は残る | CT-Σ5 |
| 何も宣言しない包み ≡ 包みなし | CT-I1 |
| FB-1：対象の伝達は 0（重み 0 の駆動は残る）、対象外はその系の `ConnectionStore` の値のまま、対象の中の重みは規則どおり | CT-I2 |
| FREEZE：対象の重みは据え置き、痕跡は宣言どおり、対象外は規則どおり | CT-I3 |
| TRANSPLANT：宣言した重みだけが変わる | CT-I4 |
| 片側の FREEZE は組の和で F1 を破ったことが分かり、組の両方なら w_max のまま | CT-I5 |
| 介入は Receptor の入力の重み（1.0）と Unit の力学に触れない | CT-I6 |
| 自分の感覚の列を開いたループで再生すると、閉ループと同じ軌道（命題 G-2） | OPEN-LOOP |

## 監査 019〜021 への対応

| 監査 | 対応 | 契約テスト |
|---|---|---|
| 019 出生の乱数と Unit の差し替え | 源の中身は、同じ設計図・同じ seed で別に組み立てた個体の Unit をそのまま使う。本体の組み立ては全 Unit を同じ順で作ってから差し替えるので、出生の乱数の消費は C0 と同じ。役の割り当ては名前で分けた別の乱数の流れ | 源が s1・s2・s3 のどれでも、Pulse 0 の Unit の状態と重みが C0 と同じ。CT-G1a も 3 つの役で確かめる |
| 020 介入の Pulse 境界 | 介入は Pulse のあいだに `AS1System.declare`・`clear` で切り替え、その境界の Pulse を記録する。境界 u のあとの宣言は、Pulse u ＋ 1 の冒頭の伝達と末尾の更新から効く。`weights()`・`export_state()` の呼び出しの回数は区間に関係しない。最初の意図 τ は、源の発火（Pulse の 4）の記録から検知し、τ の処理の後で止める（`advance_until_first_intent`。τ の末尾の更新は τ の発火に効かない） | 宣言の前に成立した駆動は前の重みで届き、次の Pulse の伝達から 0。外からの観察で軌道が変わらない。τ の検知と打ち切り |
| 021 接続の状態の正本 | 正本は一つの `ConnectionStore`（`Application.connections`）。Runtime と Lifecycle は包みの部品を、道具（移植・観察）は中の Store を使う。包みの部品は中の Store の値を写すだけ | 包みの `inner` が `Application.connections` と同じ物。保存の写しが Store と同じ。複製でも同じ配線。移植した重みが次の `weights()` に出る |

## まだ決めていないこと（③ 事前登録で決める）

L の値（候補 2）、多重度の規則、FREEZE の痕跡の扱い、行動に依らない刺激を置くか、区間・H、どの介入を最初に置くか、CT-G1c の比べない欄の一覧。
