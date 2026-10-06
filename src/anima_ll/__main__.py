"""`python -m anima_ll` で起動する。

設定とデータの場所は、実行時の作業ディレクトリを基準にする
（リポジトリ直下でも、Docker コンテナの /app でも同じように動く）。

例:
  python -m anima_ll --pulses 60                 # 実時間（1 秒/Pulse）で 60 Pulse
  python -m anima_ll --pulses 200 --clock fast   # 時計だけ進めて一気に回す
"""

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from anima_ll.adapter.manifest.yaml_manifest_source import YamlManifestSource
from anima_ll.adapter.persistence.json_snapshot_store import JsonSnapshotStore
from anima_ll.adapter.persistence.jsonl_event_log import JsonlEventLog
from anima_ll.bootstrap import build_application, make_clock

DEFAULT_MANIFEST = Path("config/neuroarchitecture/minimal-v0.yaml")
DEFAULT_DATA_DIR = Path("data")


def main() -> None:
    parser = argparse.ArgumentParser(prog="anima_ll")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--pulses", type=int, default=None, help="省略すると Ctrl+C まで動き続ける")
    parser.add_argument("--interval", type=float, default=1.0, help="1 Pulse の秒数")
    parser.add_argument("--clock", choices=["realtime", "fast"], default="realtime")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    event_log = JsonlEventLog(args.data_dir / "logs" / f"run-{run_id}.jsonl")
    app = build_application(
        YamlManifestSource(args.manifest).load(),
        clock=make_clock(args.clock, args.interval),
        event_log=event_log,
        snapshot_store=JsonSnapshotStore(args.data_dir / "snapshots"),
    )
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
