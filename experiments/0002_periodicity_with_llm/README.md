# 0002 実際の LLM を入れても、自発活動の周期性は残るか

> 種別：**検証（事前登録）**。このファイルと `analyze.py` は、L1 での測定を始める前にコミットする
> 登録日：2026-10-06
> 構成：脳 `neuroarchitecture/minimal-v0.yaml`（動作テスト用の設計図）／個体 `individual/anima.yaml`（seed は下記で上書き）

## 背景

L0（偽 Kernel、遅延 3 秒固定）では、入力がないと Unit がほぼ一定の間隔で発火し、発話も一定間隔になった（0001 §3）。
「決まった間隔で喋るタイマー」は避けたい振る舞いそのもの。実際の LLM では推論時間も出力（黙る・失敗する）もばらつくので、それだけで周期性が崩れるのかを確かめる。

## ベースライン（L0 偽 Kernel、事前に測定済み）

L1 と同じ条件（入力なし・1800 Pulse・seed 42/43/44）を、偽 Kernel で回した結果。偽 Kernel は時計だけで動くので `--clock fast` でも実時間と同じ結果になる。

```bash
for s in 42 43 44; do
  docker compose run --rm --no-deps -T anima python -m anima_ll \
      --environment config/environment/l0-fake-silent.yaml --clock fast --pulses 1800 \
      --seed $s --log-group 0002/l0
done
python experiments/0002_periodicity_with_llm/analyze.py data/logs/0002/l0/*.jsonl
```

| seed | u1 CV | u2 CV | u3 CV | 発話 CV（回数） | H1 | H2 |
|---|---|---|---|---|---|---|
| 42 | 0.014 | 0.014 | 0.095 | 0.000（148） | 周期的 | 周期的 |
| 43 | 0.000 | 0.000 | 0.070 | 0.070（120） | 周期的 | 周期的 |
| 44 | 0.107 | 0.439 | 0.285 | 0.283（167） | 周期的でない | 周期的でない |

**分かったこと**：偽 Kernel でも、seed 44 では周期性が崩れている。周期性は「L0 なら必ず起きる」ものではなく、個体（初期値）によって出たり出なかったりする。
そのため、判定は **3 seed をまとめた全体** ではなく、**同じ seed の L0 と L1 を比べる** 形にする。

## 仮説

ベースラインで周期的だった個体（seed 42, 43）について：

- **H1**：実際の LLM が入っても、各 Unit（u1, u2, u3）の発火間隔はほぼ周期的なまま残る
- **H2**：実際の LLM が入っても、`effector.console` への発話の間隔はほぼ周期的なまま残る

H1 と H2 は別物として判定する。発話は `utter` の「黙る」と Kernel の失敗で間引かれるので、発火が周期的でも発話は周期的でないことがありうる。

seed 44 は参考として同じ指標を記録する（LLM が入って周期的に「なる」ことがあるかを見る）。

## 操作

- 環境：`config/environment/l1-ollama-silent.yaml`（Ollama、モデル `anima-llm`、sampling は seed 0・temperature 0.3 で固定。入力は何も出さない台本入力）
- 入力：一切与えない
- 時間：1800 Pulse（1 Pulse = 1 秒、**実時間**。実際の LLM は時計と無関係に時間がかかるので `--clock fast` は使えない）
- 個体の seed：42, 43, 44（1 本ずつ、順番に。合計約 90 分）
- 実行前に `docker compose logs ollama` で、モデルが登録済みであること・GGUF の SHA-256・Ollama のバージョンを記録する
- ログは `data/logs/0002/l1/` に分ける。各ログの先頭には、設定ファイルのパスと SHA-256、実行環境（モデル・sampling）、個体の seed、コードの版（git commit）が記録される

Windows（PowerShell）：

```powershell
$env:ANIMA_GIT_COMMIT = git rev-parse HEAD
docker compose up -d ollama
foreach ($s in 42, 43, 44) {
  docker compose run --rm -T anima python -m anima_ll `
    --environment config/environment/l1-ollama-silent.yaml --pulses 1800 --seed $s --log-group 0002/l1
}
docker compose run --rm --no-deps anima sh -c "python experiments/0002_periodicity_with_llm/analyze.py data/logs/0002/l1/*.jsonl"
```

mac / Linux：

```bash
export ANIMA_GIT_COMMIT=$(git rev-parse HEAD)
docker compose up -d ollama
for s in 42 43 44; do
  docker compose run --rm -T anima python -m anima_ll \
    --environment config/environment/l1-ollama-silent.yaml --pulses 1800 --seed $s --log-group 0002/l1
done
python experiments/0002_periodicity_with_llm/analyze.py data/logs/0002/l1/*.jsonl
```

## 集計（`analyze.py`）

- seed と実行環境は、ファイル名ではなくログ先頭の run 記録から読む（run 記録のないログは集計しない）
- 仮説の判定に使うのは `--primary-seeds`（既定 42 43）の run だけ。seed 44 は表示するが判定には入れない
- 次の場合は判定しない：実行環境（Kernel・モデル）の違う run が混ざっている／受容器からの入力がある／判定用の seed がちょうど 1 本ずつそろっていない
- Kernel の失敗が started の 1 割以上の run は無効とし、その run の H1・H2 は判定不能にする

## 指標

| 指標 | 定義 |
|---|---|
| H1 | u1, u2, u3 それぞれの claim（＝発火して計算を要求した）間隔の変動係数（標準偏差 / 平均） |
| H2 | effector への出力の間隔の変動係数 |
| 補助 | 壁時計での発火・発話間隔の変動係数と、Pulse 間隔の最大値（Pulse が遅れていないかの確認。判定には使わない） |
| 参考 | 根拠なしの計算の割合、外からの根拠のない発話の割合（この実験では入力がないので 100% のはず）、Kernel の失敗数 |

## 判定（seed ごと）

- **H1**：u1, u2, u3 の変動係数がすべて 0.2 未満なら「周期的」
- **H2**：発話が 5 回以上あり、発話間隔の変動係数が 0.2 未満なら「周期的」。5 回未満なら「判定不能」
- 仮説が **支持** されるのは、seed 42 と 43 の両方で「周期的」のとき

## 結果の扱い

- **支持された** → 周期性は Kernel のばらつきでは崩れない。L2 の前に対処方針を決める（0001 §3 の候補から）
- **支持されなかった** → 「偽 Kernel 特有の現象だった」とは結論しない。どの要素が周期性を崩したかを、1 つずつ確かめる（アブレーション）：
  - a. ベースライン（上の表）がそのまま再現するか
  - b. 偽 Kernel の遅延をばらつかせる（`l0-fake-silent.yaml` の `delay_jitter_seconds`）。推論時間のばらつきだけで崩れるか
  - c. `utter` テンプレートから「黙る」を外す。発話の間引きだけで H2 が崩れているのか
- **Kernel の失敗が多い**（started の 1 割以上）場合は、その run を無効とし（`analyze.py` が判定不能にする）、原因を直してやり直す

## 評価の対象外

発話の **内容**（質・人格らしさ）は評価しない。入力なしの条件なので、発話はほぼすべて根拠なしの計算と cognitive leakage（LLM の事前分布による穴埋め）になる見込みで、0002 が見るのは時間構造だけである（0003 の観察を参照）。

## 登録内容の修正（測定前）

- 2026-10-06：レビュー（ChatGPT）を受けて `analyze.py` を修正。判定を seed 42/43 だけに限定（seed 44 が判定に混ざるバグ）、seed と実行環境をログの run 記録から読む、実行環境の混在を拒否、Kernel の失敗率 1 割以上を無効に。ログの置き場所を `data/logs/0002/l0|l1/` に分けた。仮説・指標・閾値は変えていない
- 2026-10-06：L1 初回起動の観察（0003）とレビュー（ChatGPT）を受けて、(1) 入力なしの条件を標準入力に頼らず作るため環境を `l1-ollama-silent.yaml` に変更（LLM と sampling は同じ）、(2) 補助指標として壁時計での間隔の変動係数と Pulse 間隔の最大値を追加、(3) 発話内容を評価対象外と明記。仮説・判定基準・閾値は変えていない

## 結果

（測定後に追記する。上の内容は書き換えない）
