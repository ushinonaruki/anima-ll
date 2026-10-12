"""実験 0017 の実行（事前登録 v0.3 に従う。測定の前にコミットする）。

1 個体（seed）ごとに：
  1. ordered・shuffled の 2 条件の本体を作り、出生時の Unit の状態を記録する
  2. 札が最初に違う Pulse の直前・経験の終わり（12000）・終端（24000）まで両方の本体を進め、状態を記録する
  3. 終端で、両条件それぞれに何も変えない複製を 1 つ作り、総 Pulse まで進める（複製の一致の材料）
  4. 各試しの時刻 t0（24001〜24300）で、両方の本体の t0 − 1 の終わりから独立に試しを行い（world.probe_series）、
     受け手・提供側の試しの元の感覚の出来事、提供側の 4 本、2 腕の分けた直後の状態、2 腕の発火（t0 ＋ 1〜t0 ＋ read_at）、
     両方の本体の t0 の終わりの重みを記録する
  5. 両方の本体の発火・感覚の出来事・最後の接続の状態を記録する
判定の量（E・S）・移植の差（D・Δm・4 本それぞれの差・違った本数）は analyze.py が計算する。ここでは計算しない。

使い方（リポジトリ直下で）:
  python experiments/0017_target_weight_transplant/run.py                         # 本番（seed 10001〜10020）
  python experiments/0017_target_weight_transplant/run.py --smoke --out <scratch>  # 動作確認（seed 10101〜10106）
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

HERE = Path("experiments/0017_target_weight_transplant")
PROTOCOL = yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
OUT_DIR = Path("data/experiments/0017")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load("alignment_0017", HERE / "alignment.py")
W = load("world_0017", HERE / "world.py")


def run_seed(seed: int) -> dict:
    end, ep, total = W.experience_end(PROTOCOL), W.endpoint(PROTOCOL), W.total_pulses(PROTOCOL)
    diverge = W.first_divergence(PROTOCOL, seed)
    apps, logs, out = {}, {}, {}
    for c in W.CONDITIONS:
        logs[c] = W.ExperimentLog()
        apps[c] = W.build(PROTOCOL, c, seed, logs[c])
        out[c] = {"birth": W.unit_states(apps[c]), "before_divergence": None}
    for t in sorted({end, ep} | ({diverge - 1} if diverge is not None else set())):
        for c in W.CONDITIONS:
            W.advance_to(apps[c], t)
            if diverge is not None and t == diverge - 1:
                out[c]["before_divergence"] = W.snapshot(apps[c])
            if t == end:
                out[c]["connections_experience_end"] = apps[c].connections.export_state()
            if t == ep:
                out[c]["connections_endpoint"] = apps[c].connections.export_state()
    twins = {c: W.clone(apps[c], logs[c]) for c in W.CONDITIONS}
    probes = W.probe_series(PROTOCOL, apps["ordered"], logs["ordered"], apps["shuffled"], logs["shuffled"],
                            seed, W.probe_times(PROTOCOL))
    for c in W.CONDITIONS:
        W.advance_to(apps[c], total)
        twin, twin_log = twins[c]
        W.advance_to(twin, total)
        out[c] |= {"activity": logs[c].activity(), "sensory": logs[c].sensory(),
                   "connections_end": apps[c].connections.export_state(),
                   "clone": {"from": ep, "activity": twin_log.activity(),
                             "connections_end": twin.connections.export_state()}}
    return {"seed": seed, "first_divergence": diverge,
            "roles": {"receptors": W.role_receptors(PROTOCOL, seed), "units": W.role_units(PROTOCOL, seed)},
            "conditions": out, "probes": probes}


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
    data = {"meta": {"experiment": "0017", "smoke": args.smoke, "git_commit": git_commit(), "protocol": PROTOCOL,
                     "manifest": W.manifest_raw(PROTOCOL), "seeds": seeds},
            "runs": runs}
    with gzip.open(out / "runs.json.gz", "wt", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"saved {out / 'runs.json.gz'} ({len(runs)} individuals, {time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
