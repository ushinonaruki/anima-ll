"""実験 0014 の実行（事前登録 v0.3 に従う。測定の前にコミットする）。

条件・個体・手順の値は protocol.yaml から読む。設計図は 0012 v0.3 のもの（protocol の brain.manifest）。
1 個体（seed）ごとに、順序あり・順序を崩した の 2 条件：
  1. 出生時の Unit の状態を記録する
  2. 札が最初に違う Pulse d の直前（d − 1 の終わり）の Unit・接続の状態を記録する（分かれる前の一致の材料）
  3. probes.first − 1（W_post）の終わりの接続の状態を記録し、そこで何も変えない複製を 1 つ作って総 Pulse まで進める
     （複製の一致の材料）
  4. 各試しの時刻 t0 で、world.probe（README §3.3 の手順）を行い、試しの元の感覚の出来事・2 腕の分けた直後の状態・
     2 腕の発火を記録する。本体を t0 まで進める
  5. 本体を総 Pulse まで進め、本体の発火・感覚の出来事・最後の接続の状態を記録する
判定の量（p・w）は analyze.py が計算する。ここでは計算しない。

使い方（リポジトリ直下で）:
  python experiments/0014_order_to_activity/run.py                         # 本番（seed 4001〜4020）
  python experiments/0014_order_to_activity/run.py --smoke --out <scratch>  # 動作確認（seed 5001〜5006）
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

HERE = Path("experiments/0014_order_to_activity")
PROTOCOL = yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
OUT_DIR = Path("data/experiments/0014")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load("alignment_0014", HERE / "alignment.py")
W = load("world_0014", HERE / "world.py")


def run_condition(seed: int, condition: str, diverge: int | None) -> dict:
    total = PROTOCOL["timeline"]["total_pulses"]
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, condition, seed, log)
    birth = W.unit_states(app)
    before = None
    if diverge is not None:
        W.advance_to(app, diverge - 1)
        before = W.snapshot(app)
    post = W.w_post_pulse(PROTOCOL)
    W.advance_to(app, post)
    connections_post = app.connections.export_state()
    twin, twin_log = W.clone(app, log)
    probes = []
    for t0 in W.probe_times(PROTOCOL):
        W.advance_to(app, t0 - 1)
        probes.append(W.probe(PROTOCOL, app, log, seed, t0))
    W.advance_to(app, total)
    W.advance_to(twin, total)
    return {
        "birth": birth,
        "before_divergence": before,
        "connections_post": connections_post,
        "activity": log.activity(),
        "sensory": log.sensory(),
        "connections_end": app.connections.export_state(),
        "clone": {"from": post, "activity": twin_log.activity(), "connections_end": twin.connections.export_state()},
        "probes": probes,
    }


def run_seed(seed: int) -> dict:
    diverge = W.first_divergence(PROTOCOL, seed)
    return {"seed": seed, "first_divergence": diverge,
            "roles": {"receptors": W.role_receptors(PROTOCOL, seed), "units": W.role_units(PROTOCOL, seed)},
            "conditions": {c: run_condition(seed, c, diverge) for c in PROTOCOL["stimulus"]["conditions"]}}


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
    data = {"meta": {"experiment": "0014", "smoke": args.smoke, "git_commit": git_commit(), "protocol": PROTOCOL,
                     "manifest": W.manifest_raw(PROTOCOL), "seeds": seeds},
            "runs": runs}
    with gzip.open(out / "runs.json.gz", "wt", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"saved {out / 'runs.json.gz'} ({len(runs)} individuals, {time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
