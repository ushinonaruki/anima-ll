"""実験 0013 の実行（事前登録の一部。測定の前にコミットする）。

条件・個体・手順の値は protocol.yaml から読む。設計図は protocol の brain（可塑性あり・なしの双子）。
1 個体（seed）ごとに：
  1. 可塑性なし（N）：出生時の状態を記録し、総 Pulse まで進める。全接続の重みが最初と最後で同じかを記録する
  2. 可塑性あり（P）：出生時の状態を記録し、weight_sample_every ごとに接続の状態（重み・痕跡）を記録しながら進める
  3. 介入（README §3.3）：P を intervention.at_pulse の終わりで 2 つ複製する。
     as_is はそのまま、reset_to_w0 は複製の上でだけ 6 本の重みを w0 に戻す（痕跡はそのまま）。両方を総 Pulse まで進める。
     as_is の複製と本体の比較が、複製の操作の確認（発火の記録・接続の状態の完全な一致）を兼ねる
  4. 操作の確認の材料：最初に重みが変わる Pulse（それより前は P と N で発火の記録が一致するはず）、
     再生の計算（experiments/0012_passive_world/post/replay.py）と記録の重みの差
本体・複製の発火の記録（activity の出来事）はすべて保存する。判定の量は analyze.py が計算する。

使い方（リポジトリ直下で）:
  python experiments/0013_self_amplified_asymmetry/run.py                         # 本番（seed 2001〜2020）
  python experiments/0013_self_amplified_asymmetry/run.py --smoke --out <scratch>  # 動作確認（seed 3001〜3006）
"""

import argparse
import gzip
import importlib.util
import itertools
import json
import os
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import yaml

HERE = Path("experiments/0013_self_amplified_asymmetry")
PROTOCOL = yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
OUT_DIR = Path("data/experiments/0013")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load("alignment_0013", HERE / "alignment.py")
W = load("world_0013", HERE / "world.py")
REPLAY = load("replay_0012_post", Path("experiments/0012_passive_world/post/replay.py"))


def all_weights(app) -> dict[str, float]:
    """全接続の今の重み（可塑性の対象でない接続も含む）。"""
    return {f"{s}.{port}->{t}": w for (s, port, t), w in app.connections.weights().items()}


def replay_error(activity: list[list], weights_end: dict[str, float], manifest: dict) -> float:
    spec = W.parse_neuroarchitecture(manifest).plasticity
    spikes = {u: [p for p, v in activity if v == u] for u in PROTOCOL["brain"]["units"]}
    w0 = [p["weight"] for p in manifest["projections"] if p.get("plastic")][0]
    err = 0.0
    for a, b in itertools.permutations(PROTOCOL["brain"]["units"], 2):
        w, _ = REPLAY.replay(spikes[a], spikes[b], w0=w0, w_max=spec.w_max, amplitude=spec.amplitude,
                             tau=spec.trace_tau_seconds, dt=PROTOCOL["timeline"]["pulse_interval_seconds"],
                             end=PROTOCOL["timeline"]["total_pulses"])
        err = max(err, abs(w - weights_end[f"{a}.main->{b}"]))
    return err


def run_seed(seed: int) -> dict:
    tl, iv = PROTOCOL["timeline"], PROTOCOL["intervention"]
    total, every, at = tl["total_pulses"], tl["weight_sample_every"], iv["at_pulse"]

    # 可塑性なし
    log_n = W.ExperimentLog()
    n = W.build(PROTOCOL, "nonplastic", seed, log_n)
    birth_n = W.birth_state(n)
    weights_n_start = all_weights(n)
    W.advance_to(n, total)

    # 可塑性あり
    log_p = W.ExperimentLog()
    p = W.build(PROTOCOL, "plastic", seed, log_p)
    birth_p = W.birth_state(p)
    w0 = p.connections.export_state()[next(iter(p.connections.export_state()))]["weight"]
    samples = {0: p.connections.export_state()}
    for t in range(every, at + 1, every):
        W.advance_to(p, t)
        samples[t] = p.connections.export_state()
    W.advance_to(p, at)
    state_at = p.connections.export_state()

    # 介入：複製を 2 つ
    as_is, log_as_is = W.clone(p, log_p)
    reset, log_reset = W.clone(p, log_p)
    W.reset_weights(reset, w0)
    reset_start = reset.connections.export_state()
    W.advance_to(as_is, total)
    W.advance_to(reset, total)

    for t in range(at + every, total + 1, every):
        W.advance_to(p, t)
        samples[t] = p.connections.export_state()
    W.advance_to(p, total)

    act_p, act_n = log_p.activity(), log_n.activity()
    first = W.first_weight_change(act_p)
    weights_end_p = W.weights_of(p)
    window = iv["window"]
    return {
        "seed": seed,
        "birth": {"plastic": birth_p, "nonplastic": birth_n},
        "eligible_pairs": W.eligible_pairs(birth_p, PROTOCOL["brain"]["units"]),
        "rho": {u: W.rho(s) for u, s in birth_p.items()},
        "activity": {"plastic": act_p, "nonplastic": act_n,
                     "as_is": log_as_is.activity(), "reset_to_w0": log_reset.activity()},
        "weight_samples": {str(t): s for t, s in sorted(samples.items())},
        "connections_at_intervention": state_at,
        "reset_start": reset_start,
        "weights_end": {"plastic": weights_end_p, "as_is": W.weights_of(as_is), "reset_to_w0": W.weights_of(reset)},
        "checks": {
            "nonplastic_weights_unchanged": weights_n_start == all_weights(n),
            "identical_birth_state": birth_p == birth_n,
            "first_weight_change_pulse": first,
            "identical_until_first_weight_change": W.identical_until_first_weight_change(act_p, act_n),
            "clone_identity": ([a for a in act_p if window[0] <= a[0] <= window[1]] == log_as_is.activity()
                               and p.connections.export_state() == as_is.connections.export_state()),
            "reset_weights_are_w0": all(v["weight"] == w0 for v in reset_start.values()),
            "reset_traces_kept": all(reset_start[c]["pre_trace"] == state_at[c]["pre_trace"]
                                     and reset_start[c]["post_trace"] == state_at[c]["post_trace"] for c in state_at),
            "replay_error": replay_error(act_p, weights_end_p, W.manifest_raw(PROTOCOL, "plastic")),
        },
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
    data = {"meta": {"experiment": "0013", "smoke": args.smoke, "git_commit": git_commit(), "protocol": PROTOCOL,
                     "manifests": {c: W.manifest_raw(PROTOCOL, c) for c in PROTOCOL["conditions"]}, "seeds": seeds},
            "runs": runs}
    with gzip.open(out / "runs.json.gz", "wt", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"saved {out / 'runs.json.gz'} ({len(runs)} individuals, {time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
