"""`python -m anima_ll` で起動する。

設定とデータの場所は、実行時の作業ディレクトリを基準にする
（リポジトリ直下でも、Docker コンテナの /app でも同じように動く）。

設定は 3 つに分かれている（v1.4 §3）:
  --neuroarchitecture  脳の設計図（Unit・配線・力学）
  --environment        実行環境（Kernel・Receptor・Effector の実装）
  --individual         個体（個体 ID と seed）

例:
  python -m anima_ll                                              # L1：Ollama とコンソール
  python -m anima_ll --environment config/environment/l0-fake.yaml --pulses 200 --clock fast
  python -m anima_ll --seed 43 --pulses 1800                      # 個体の seed だけ変える（実験用）
"""

import argparse
import asyncio
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from anima_ll.adapter.config.yaml_config_source import (
    YamlBirthStateSource,
    YamlEnvironmentSource,
    YamlNeuroarchitectureSource,
)
from anima_ll.adapter.persistence.json_snapshot_store import JsonSnapshotStore
from anima_ll.adapter.persistence.jsonl_event_log import JsonlEventLog
from anima_ll.bootstrap import build_application, make_clock

DEFAULT_NEUROARCHITECTURE = Path("config/neuroarchitecture/minimal-v0.yaml")
DEFAULT_ENVIRONMENT = Path("config/environment/l1-ollama-console.yaml")
DEFAULT_INDIVIDUAL = Path("config/individual/anima.yaml")
DEFAULT_DATA_DIR = Path("data")


def main() -> None:
    parser = argparse.ArgumentParser(prog="anima_ll")
    parser.add_argument("--neuroarchitecture", type=Path, default=DEFAULT_NEUROARCHITECTURE)
    parser.add_argument("--environment", type=Path, default=DEFAULT_ENVIRONMENT)
    parser.add_argument("--individual", type=Path, default=DEFAULT_INDIVIDUAL)
    parser.add_argument("--seed", type=int, default=None, help="個体の seed を上書きする（実験用）")
    parser.add_argument("--pulses", type=int, default=None, help="省略すると Ctrl+C まで動き続ける")
    parser.add_argument("--interval", type=float, default=1.0, help="1 Pulse の秒数")
    parser.add_argument("--clock", choices=["realtime", "fast"], default="realtime")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()

    birth = YamlBirthStateSource(args.individual).load()
    if args.seed is not None:
        birth = replace(birth, seed=args.seed)

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    event_log = JsonlEventLog(
        args.data_dir / "logs" / f"run-{run_id}-{birth.individual_id}-s{birth.seed}.jsonl"
    )
    app = build_application(
        YamlNeuroarchitectureSource(args.neuroarchitecture).load(),
        YamlEnvironmentSource(args.environment).load(),
        birth,
        clock=make_clock(args.clock, args.interval),
        event_log=event_log,
        snapshot_store=JsonSnapshotStore(args.data_dir / "snapshots"),
    )
    print(f"[anima_ll] individual: {birth.individual_id} (seed {birth.seed})")
    print(f"[anima_ll] environment: {args.environment}")
    print(f"[anima_ll] log: {event_log.path}")
    try:
        asyncio.run(app.lifecycle.run(max_pulses=args.pulses))
    except KeyboardInterrupt:
        pass
    finally:
        event_log.close()
        print(f"[anima_ll] stopped at pulse {app.lifecycle.pulse}")


if __name__ == "__main__":
    main()
