# AnIma-ll

生活空間の隣で継続して存在する AI 生命体 / AI 隣人。

設計の正本は Obsidian vault の `【プログラム】Anima-ll/設計書/` を参照。
現在の実装は最軽量版 L1（Python 3.11 以上、外部依存は PyYAML と httpx。ローカル LLM は Ollama）。

## 構成（src/anima_ll）

```text
bootstrap.py   全部品を組み立てる唯一の場所（設定の kind → 実装の対応表）
domain/        AnIma-ll の概念だけ（Delta, Claim, View, Unit, Port）。外部技術を知らない
runtime/       Pulse を回す「考えない部分」（View 生成・来歴確定・統合・資源配分・非同期タスク）
unit/          唯一の Unit 実装 GenericCognitiveUnit と、その部品（dynamics, output）
adapter/       外部技術（Kernel, Receptor, Effector, 保存, 設定の読み込み, 時計）
```

依存の向きは `tests/architecture` で自動検査している。

## 設定（config/）

変わる理由が違うので、3 つに分けている。

| フォルダ | 何を表すか |
|---|---|
| `neuroarchitecture/` | 脳の設計図：Unit・配線・力学。外とつながる口は ID だけを宣言する。Unit に役割（`role: memory` など）は書けない |
| `environment/` | 実行環境：口にどの実装（偽 Kernel／Ollama、台本／コンソール）をつなぐか |
| `individual/` | 個体（Birth State）：個体 ID と seed |
| `io_templates/` | Kernel への入出力の形式だけ（人格・口調・振る舞いは書かない） |

脳の設計図は版ごとに積み上げる。配線はどれも動作テスト用で、脳についての主張は込めていない。どの仕組み・値が仮説で、どれが足場かは `docs/arbitrariness-audit.md` にまとめている。

| 版 | 中身 | 使いどころ |
|---|---|---|
| `minimal-v0` | 基礎の力学（減衰・内在的駆動・閾値・不応期） | L0・L1・実験 0001〜0005 の比較基準。**凍結**（書き換えない） |
| `minimal-v1` | v0 ＋ 発火履歴への順応（L2-1、参照値 α=0.01・τ_a=300 秒、実験 0004・0005） | 比較の基準。**凍結** |
| `minimal-v2` | v1 ＋ 不応期の除去（恣意性監査 §3.2、実験 0009） | 比較の基準。**凍結** |
| `minimal-v3` | v2 と値は同じ。活動の伝達の経路（c2：発火 × 重みが駆動し、Delta は中身だけ）で解釈する（`docs/activity-transmission-spec.md`、実験 0011） | **現行基準（既定）** |

v0〜v2 は、旧の経路（Delta が駆動する）で測った版である。今のコードで動かすと旧の結果とは違う振る舞いになるので、旧の結果はそれぞれの測定の commit とデータで再現する。

## 動かす（Docker）

本体も Ollama も Docker で動かす。手元に Python も Ollama も不要。

1. モデルファイルを置く（Git 管理外）

   ```text
   models/Llama-3.2-3B-Instruct-Q5_K_M.gguf
   ```

2. 起動する

   ```bash
   docker compose build
   docker compose up -d ollama          # 初回は GGUF からモデル anima-llm を登録する（数分）
   docker compose logs -f ollama        # 「登録しました」「登録済みです」が出れば準備完了

   docker compose run --rm anima        # 話しかける（1 行入力して Enter）。Ctrl+C で止める
   docker compose down                  # Ollama も止める
   ```

3. 初回だけ、モデルの動作を確かめる

   ```bash
   docker compose exec ollama ollama show anima-llm --verbose | findstr add_bos_token   # true なら文頭トークンは自動で付く（mac/Linux は grep）
   docker compose exec ollama ollama run anima-llm "こんにちは"                        # 日本語で普通に返れば OK
   ```

   返答に `<|eot_id|>` などの特殊トークンが混ざる、同じ文を繰り返す、何も返らない、などがあれば
   チャット形式（`docker/ollama/Modelfile.base`）の問題なので知らせてほしい。

4. そのほか

   ```bash
   # L0 の動作テスト（偽 Kernel・台本入力。Ollama は使わない）
   docker compose run --rm --no-deps anima python -m anima_ll \
       --environment config/environment/l0-fake.yaml --pulses 120 --clock fast

   # テスト
   docker compose run --rm test
   ```

- `config/` はコンテナに読み取り専用でマウントされる。設定を書き換えたらビルドし直さずに反映される
- ログは `data/logs/run-<日時>-<個体>-s<seed>.jsonl`（来歴をすべて記録。先頭に設定・実行環境・seed・コードの版）。`--log-group 0002/l1` で `data/logs/0002/l1/` に分けられる
- 個体のスナップショットは `data/snapshots/`
- GGUF を同じファイル名のまま差し替えても、中身（SHA-256）の違いを見て登録し直す
- Ollama やモデルがなくても本体は止まらない（Kernel のエラーとして記録され、Pulse は進み続ける）
- 入力なしで LLM を呼んだ計算はログで `without_evidence: true` になる（L1 では禁止せずに観察する）

Docker を使わずに動かす場合は、リポジトリ直下で `pip install -e ".[dev]"` のあと `pytest`。
L1 環境の Ollama の場所は `config/environment/l1-ollama-console.yaml` の `base_url` で変えられる。

## 段階

- **L0**（済）：Runtime と偽 Kernel。記録は `experiments/0001_minimal_runtime/`
- **L1**（済）：Ollama とコンソール入出力、設定の 3 分割。観察 `experiments/0003_first_l1_session/`、実験 `experiments/0002_periodicity_with_llm/`
- **L2**（進行中）
  - L2-1 発火履歴に依存する順応（済）：実験 `0004_adaptation/`（入力なしで落ち着く）、`0005_response_threshold/`（発火に必要な入力が上がる）→ `minimal-v1`
  - L2-2 計算の要求の持ち越し（**不採用**）：実験 `0006_pending_compute/`。実行基盤の制約を認知状態に写していたため
  - 恣意性監査（`docs/arbitrariness-audit.md`、§3.1〜3.9 済み）。L0〜L2-1 のすべての仕組みと値を、仮説か足場かで棚卸しした。まとめは §6
    - §3.1 計算資源の取り合い（済）：仕様 `docs/compute-boundary-spec.md`。実行基盤は意図を黙って捨てない。実装確認は実験 `0007_compute_boundary/`、新基盤での baseline は `0008_baseline_new_runtime/`
    - §3.2 不応期（済）：独立した根拠がないため除去 → `minimal-v2`。影響範囲の確認は実験 `0009_refractory_removal/`
    - §3.3 内在的駆動（済）：原理は残し、値 0.08 は根拠なし。知見の ρ 依存は実験 `0010_drive_regime/`
    - §3.4〜3.9（済）：材料の窓・内部表現とテンプレート・配線・基本の力学について、項目ごとに足場・採用する原理・未解決の問いを整理した（例：減衰の仕組みは条件付きで採用、閾値の絶対値は単位の選び方、決定論的な発火は独立の未解決の問い）。方向として「内部の思考 ≠ LLM の文章のループ」「行動の選択は Neuroarchitecture」を採用
  - **次：** 足場を引き取る本設計（言語ではない内部表現・記憶・可塑性・行動の意図）。進め方は検討中
- L3：睡眠（Replay・恒常性）
