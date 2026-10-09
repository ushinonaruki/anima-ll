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
import hashlib
import os
import subprocess
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

DEFAULT_NEUROARCHITECTURE = Path("config/neuroarchitecture/minimal-v3.yaml")  # 現行基準（v0〜v2 は凍結した比較基準）
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
    parser.add_argument("--state-log-interval", type=int, default=0,
                        help="Unit の内部状態を何 Pulse ごとにログに残すか（0 は残さない。観察用）")
    parser.add_argument("--log-group", default="", help="ログを data/logs/<group>/ に分ける（例: 0002/l1）")
    args = parser.parse_args()

    birth = YamlBirthStateSource(args.individual).load()
    if args.seed is not None:
        birth = replace(birth, seed=args.seed)

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_dir = args.data_dir / "logs" / args.log_group if args.log_group else args.data_dir / "logs"
    event_log = JsonlEventLog(log_dir / f"run-{run_id}-{birth.individual_id}-s{birth.seed}.jsonl")
    config_files = {
        "neuroarchitecture": args.neuroarchitecture,
        "environment": args.environment,
        "individual": args.individual,
    }
    app = build_application(
        YamlNeuroarchitectureSource(args.neuroarchitecture).load(),
        YamlEnvironmentSource(args.environment).load(),
        birth,
        clock=make_clock(args.clock, args.interval),
        event_log=event_log,
        snapshot_store=JsonSnapshotStore(args.data_dir / "snapshots"),
        run_metadata={
            "run_id": run_id,
            "config_files": {k: str(v) for k, v in config_files.items()},
            "config_sha256": {k: _sha256(v) for k, v in config_files.items()},
            "seed_overridden": args.seed is not None,
            "clock": args.clock,
            "interval_seconds": args.interval,
            "git_commit": _git_commit(),
            "state_log_interval": args.state_log_interval,
        },
        state_sample_interval=args.state_log_interval,
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git_commit() -> str:
    """コードの版。Docker 内には .git がないので、環境変数 ANIMA_GIT_COMMIT で渡す。"""
    from_env = os.environ.get("ANIMA_GIT_COMMIT", "").strip()
    if from_env:
        return from_env
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


if __name__ == "__main__":
    main()
