"""0012 の事後の解析 A：読み出し（試しの窓の発火）の感度。範囲外の seed（1001〜1020）だけを使う。

A1 応答曲線：刺激なしの個体の、経験の前の試しの時刻で複製を作り、複製の上でだけ w(s_A→s_B)・w(s_A→s_C) を
   値 v に置き換えて（ConnectionStore の export_state → import_state。本体は触らない）、試しを行う。
   v ごとに、s_B・s_C が窓で発火した割合を数える
A2 試しを密にする：本番と同じ手順の個体で、経験の前・後の区間（各 1200 Pulse）に、試しを every Pulse ごとに置く
   （本番は 60 ごとに 20 回）。D と、H1 と同じ形の個体数を数える
使い方: python experiments/0012_passive_world/post/readout.py <出力フォルダ> [every]
"""

import gzip
import importlib.util
import json
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import yaml

EXP = Path("experiments/0012_passive_world")
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))
SEEDS = list(range(1001, 1021))
VALUES = [0.0, 0.0025, 0.005, 0.0075, 0.01]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = load("world_0012", EXP / "world.py")
A = load("analyze_0012", EXP / "analyze.py")
WINDOW = PROTOCOL["probe"]["response_window"]


def probe_with_weights(app, log, roles, units, t0, v):
    copied, clog = W.clone(app, log)
    state = copied.connections.export_state()
    for target in ("B", "C"):
        state[W.connection_id(units["A"], units[target])]["weight"] = v
    copied.connections.import_state(state)
    copied.receptors[roles["A"]].inject(t0)
    W.advance_to(copied, t0 - 1 + PROTOCOL["probe"]["clone_pulses"])
    fires = [[p - t0, u] for p, u in clog.activity()]
    return {t: W.fired_in(fires, units[t], WINDOW) for t in ("B", "C")}


def curve_seed(seed: int) -> dict:
    roles, units = W.role_receptors(PROTOCOL, seed), W.role_units(PROTOCOL, seed)
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, "silent", seed, log)
    hits = {v: {"B": 0, "C": 0} for v in VALUES}
    n = 0
    for t0 in W.probe_times(PROTOCOL, "pre"):
        W.advance_to(app, t0 - 1)
        n += 1
        for v in VALUES:
            res = probe_with_weights(app, log, roles, units, t0, v)
            for t in ("B", "C"):
                hits[v][t] += res[t]
    return {"seed": seed, "n": n, "hits": {str(v): h for v, h in hits.items()}}


def dense_seed(args) -> list[dict]:
    seed, every = args
    roles, units = W.role_receptors(PROTOCOL, seed), W.role_units(PROTOCOL, seed)
    out = []
    span = PROTOCOL["timeline"]["pre_probes"]
    pre = list(range(span["first"], PROTOCOL["timeline"]["trials"]["first"] - PROTOCOL["probe"]["clone_pulses"] + 1, every))
    post_first = PROTOCOL["timeline"]["post_probes"]["first"]
    post = list(range(post_first, PROTOCOL["timeline"]["total_pulses"] - PROTOCOL["probe"]["clone_pulses"] + 2, every))
    for condition in PROTOCOL["stimulus"]["conditions"]:
        log = W.ExperimentLog()
        app = W.build(PROTOCOL, condition, seed, log)
        frac = {}
        for phase, times in (("pre", pre), ("post", post)):
            hits = {"B": 0, "C": 0}
            for t0 in times:
                W.advance_to(app, t0 - 1)
                fires = W.probe(PROTOCOL, app, log, roles["A"], t0)
                for t in ("B", "C"):
                    hits[t] += W.fired_in(fires, units[t], WINDOW)
            frac[phase] = {t: hits[t] / len(times) for t in hits}
        D = (frac["post"]["B"] - frac["post"]["C"]) - (frac["pre"]["B"] - frac["pre"]["C"])
        out.append({"seed": seed, "condition": condition, "n_pre": len(pre), "n_post": len(post), "frac": frac, "D": D})
    return out


def main() -> None:
    folder = Path(sys.argv[1])
    every = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    with ProcessPoolExecutor() as pool:
        curve = list(pool.map(curve_seed, SEEDS))
        dense = [r for rs in pool.map(dense_seed, [(s, every) for s in SEEDS]) for r in rs]
    tot = {v: {"B": 0, "C": 0} for v in map(str, VALUES)}
    n = sum(c["n"] for c in curve)
    for c in curve:
        for v, h in c["hits"].items():
            for t in h:
                tot[v][t] += h[t]
    response = {v: {t: tot[v][t] / n for t in tot[v]} for v in tot}
    d = defaultdict(dict)
    for r in dense:
        d[r["seed"]][r["condition"]] = r["D"]
    h1_like, seeds = A.count_all_three(d)
    report = {"seeds": SEEDS, "every": every, "response_curve": {"probes": n, "fraction_fired_in_window": response},
              "dense": {"h1_like": h1_like, "seeds": seeds,
                        "D_mean": {c: sum(v[c] for v in d.values()) / len(d) for c in PROTOCOL["stimulus"]["conditions"]},
                        "D_ordered_positive": sum(v["ordered"] > 0 for v in d.values()),
                        "per_seed": {str(s): v for s, v in sorted(d.items())},
                        "n_pre": dense[0]["n_pre"], "n_post": dense[0]["n_post"]}}
    (folder / f"readout_every{every}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("response_curve",)} | {"dense": {k: v for k, v in report["dense"].items() if k != "per_seed"}}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
