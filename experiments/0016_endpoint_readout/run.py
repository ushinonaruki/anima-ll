"""実験 0016 の実行（事前登録 v0.2 に従う。測定の前にコミットする）。

1 個体（seed）ごとに（順序ありの条件だけ）：
  1. 出生時の Unit の状態を記録し、経験（0015 と同じ）→ 無入力で本体を進める
  2. 経験の終わり（12000）・終端（24000）の接続の状態を記録する
  3. 終端で何も変えない複製を 1 つ作り、総 Pulse まで進める（複製の一致の材料）
  4. 各試しの時刻 t0（24001〜24300）で、本体の t0 − 1 の終わりから独立に試しを行い（0014 v0.3 の手順）、
     試しの元の感覚の出来事・2 腕の分けた直後の状態・2 腕の発火（t0 ＋ 1〜t0 ＋ read_at）を記録する
  5. 本体を総 Pulse まで進め、本体の発火・感覚の出来事・最後の接続の状態を記録する
判定の量（E・S）は analyze.py が計算する。ここでは計算しない。

使い方（リポジトリ直下で）:
  python experiments/0016_endpoint_readout/run.py                         # 本番（seed 8001〜8020）
  python experiments/0016_endpoint_readout/run.py --smoke --out <scratch>  # 動作確認（seed 8101〜8106）
"""

import argparse
import gzip
import importlib.util
import json
import os
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import yaml

HERE = Path("experiments/0016_endpoint_readout")
PROTOCOL = yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
OUT_DIR = Path("data/experiments/0016")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load("alignment_0016", HERE / "alignment.py")
W = load("world_0016", HERE / "world.py")


def run_seed(seed: int) -> dict:
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, seed, log)
    birth = W.unit_states(app)
    end, ep, total = W.experience_end(PROTOCOL), W.endpoint(PROTOCOL), W.total_pulses(PROTOCOL)
    W.advance_to(app, end)
    connections_experience_end = app.connections.export_state()
    W.advance_to(app, ep)
    connections_endpoint = app.connections.export_state()
    twin, twin_log = W.clone(app, log)
    probes = []
    for t0 in W.probe_times(PROTOCOL):
        W.advance_to(app, t0 - 1)
        probes.append(W.probe(PROTOCOL, app, log, seed, t0))
    W.advance_to(app, total)
    W.advance_to(twin, total)
    return {
        "seed": seed,
        "roles": {"receptors": W.role_receptors(PROTOCOL, seed), "units": W.role_units(PROTOCOL, seed)},
        "birth": birth,
        "connections_experience_end": connections_experience_end,
        "connections_endpoint": connections_endpoint,
        "activity": log.activity(),
        "sensory": log.sensory(),
        "connections_end": app.connections.export_state(),
        "clone": {"from": ep, "activity": twin_log.activity(), "connections_end": twin.connections.export_state()},
        "probes": probes,
    }


def git_commit() -> str:
    env = os.environ.get("ANIMA_GIT_COMMIT", "").strip()
    if env:
        return env
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="範囲外の smoke.seeds だけで動作確認する（README §7）")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    if args.smoke and args.out is None:
        raise SystemExit("--smoke のときは --out に作業用のフォルダを指定する（本番のデータと混ぜない）")
    out = args.out or OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    ALIGN.check(PROTOCOL)
    s = PROTOCOL["smoke"]["seeds"] if args.smoke else PROTOCOL["seeds"]
    seeds = list(range(s["first"], s["last"] + 1))
    started = time.time()
    with ProcessPoolExecutor(max_workers=min(len(seeds), os.cpu_count() or 1)) as pool:
        runs = []
        for seed, result in zip(seeds, pool.map(run_seed, seeds)):
            runs.append(result)
            print(f"seed {seed} done / {time.time() - started:.0f}s", flush=True)
    data = {"meta": {"experiment": "0016", "smoke": args.smoke, "git_commit": git_commit(), "protocol": PROTOCOL,
                     "manifest": W.manifest_raw(PROTOCOL), "seeds": seeds},
            "runs": runs}
    with gzip.open(out / "runs.json.gz", "wt", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"saved {out / 'runs.json.gz'} ({len(runs)} individuals, {time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
