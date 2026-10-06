# AnIma-ll

生活空間の隣で継続して存在する AI 生命体 / AI 隣人。

設計の正本は Obsidian vault の `【プログラム】Anima-ll/設計書/` を参照。
現在の実装は最軽量版 L0（Python 3.11 以上、外部依存は PyYAML のみ）。

## 構成（src/anima_ll）

```text
bootstrap.py   全部品を組み立てる唯一の場所（Manifest の kind → 実装の対応表）
domain/        AnIma-ll の概念だけ（Delta, Claim, View, Unit, Port）。外部技術を知らない
runtime/       Pulse を回す「考えない部分」（View 生成・来歴確定・統合・資源配分・非同期タスク）
unit/          唯一の Unit 実装 GenericCognitiveUnit と、その部品（dynamics, output）
adapter/       外部技術（Kernel, Receptor, Effector, 保存, Manifest 読み込み, 時計）
```

依存の向きは `tests/architecture` で自動検査している。

## 動かす

```bash
pip install -e ".[dev]"

# 偽 Kernel で 120 Pulse を一気に回す（実時間は待たない）
python -m anima_ll --pulses 120 --clock fast

# 実時間（1 秒 / Pulse）。Ctrl+C で止める
python -m anima_ll

pytest
```

ログは `data/logs/run-*.jsonl`（来歴をすべて記録）、個体のスナップショットは `data/snapshots/`。

## 脳の設計図

`config/neuroarchitecture/minimal-v0.yaml`。Unit に役割（`role: memory` など）は書けない。違いは配線とパラメータだけで表す。

## 段階

- **L0**（済）：Runtime と偽 Kernel。記録は `experiments/0001_minimal_runtime/`
- **L1**：Ollama（Llama-3.2-3B-Instruct-Q5_K_M を暫定利用）とコンソール入出力
- L2：学習（適格性トレース・調節信号）、長期記憶、内受容
- L3：睡眠（Replay・恒常性）
