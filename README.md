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

`minimal-v0.yaml` は脳の仮説ではなく、配線と来歴を確かめるための動作テスト用の設計図。

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

3. そのほか

   ```bash
   # L0 の動作テスト（偽 Kernel・台本入力。Ollama は使わない）
   docker compose run --rm --no-deps anima python -m anima_ll \
       --environment config/environment/l0-fake.yaml --pulses 120 --clock fast

   # テスト
   docker compose run --rm test
   ```

- `config/` はコンテナに読み取り専用でマウントされる。設定を書き換えたらビルドし直さずに反映される
- ログは `data/logs/run-<日時>-<個体>-s<seed>.jsonl`（来歴をすべて記録）、個体のスナップショットは `data/snapshots/`
- Ollama やモデルがなくても本体は止まらない（Kernel のエラーとして記録され、Pulse は進み続ける）
- 入力なしで LLM を呼んだ計算はログで `without_evidence: true` になる（L1 では禁止せずに観察する）

Docker を使わずに動かす場合は、リポジトリ直下で `pip install -e ".[dev]"` のあと `pytest`。
L1 環境の Ollama の場所は `config/environment/l1-ollama-console.yaml` の `base_url` で変えられる。

## 段階

- **L0**（済）：Runtime と偽 Kernel。記録は `experiments/0001_minimal_runtime/`
- **L1**：Ollama とコンソール入出力、設定の 3 分割。実験 `experiments/0002_periodicity_with_llm/`
- L2：学習（適格性トレース・調節信号）、長期記憶、内受容、「何も起きなかった」の情報化
- L3：睡眠（Replay・恒常性）
