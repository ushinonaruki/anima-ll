"""実験 0012 の判定（事前登録の一部。測定の前にコミットする）。

判定の値の正本は protocol.yaml。README §5 のとおり：

- R ＝ 試しの窓（t0 ＋ response_window）で s_B が 1 回以上発火した割合 − s_C が 1 回以上発火した割合
  （経験の前の 20 回 → R(前)、経験の後の 20 回 → R(後)）。D ＝ R(後) − R(前)
- H1：同じ個体で D(ordered) > 0 かつ D(ordered) > D(shuffled) かつ D(ordered) > D(silent) を
      すべて満たす個体が min_seeds_all 以上なら「成り立つ」（等しいときは「大きい」に数えない）
- M ：W ＝ 経験の後の w(s_A → s_B) − w(s_A → s_C)。同じく 3 つを同時に満たす個体の数
      （「経験の後」は run.py が記録した、経験の後の最初の試しの直前 ＝ Pulse 13799 の終わりの重み）
- 操作の確認（1 つでも満たさなければ、判定は fails ではなく invalid）：
  - 試しの操作：条件ごとに、すべての試し（前・後、全個体）で s_A が t0 ＋ a_fired_at に発火した割合 ≥ min_a_fired_fraction
  - 刺激の操作：刺激の列と、本体が実際に受けた感覚の出来事の数が expected_counts と一致
  - 複製の操作：各個体・各条件の、試しなしの複製が本体と一致
  - 条件が分かれる前の一致：同じ seed の 3 条件で、identical_before_pulse より前の発火の記録・その直前の接続の状態
    （重み・痕跡）・経験の前の試しの結果が完全に一致
- 記録（判定に使わない。README §6）：重みの時間の変化、釣り合いの確認、発火の頻度、試しの窓の発火の割合、
  役の割り当てごとの D

- 動作確認（v0.3 §5.5）：smoke のデータでは、完全性・操作の確認・S1〜S3（smoke.py）だけを出す。
  **D・W・H1・M・§6 の記録は計算しない**（判定の seed の前に、結果の見込みに触れないため）。
  本番のデータでは、S1〜S3 の量も記録として出す（判定には使わない）

使い方:
  python experiments/0012_passive_world/analyze.py [data/experiments/0012]
  （同じ内容を <データのフォルダ>/report.json にも保存する）
"""

import gzip
import importlib.util
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import yaml

HERE = Path("experiments/0012_passive_world")
PROTOCOL = yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
DEFAULT_DIR = Path("data/experiments/0012")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load("alignment_0012", HERE / "alignment.py")
W = load("world_0012", HERE / "world.py")
SMOKE = load("smoke_0012", HERE / "smoke.py")
CONDITIONS = PROTOCOL["stimulus"]["conditions"]


def read(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def mean(xs) -> float | None:
    xs = list(xs)
    return statistics.fmean(xs) if xs else None


# ---- 指標 ------------------------------------------------------------------------

def window_fraction(run: dict, phase: str, role: str) -> float:
    unit = run["role_units"][role]
    probes = [p for p in run["probes"] if p["phase"] == phase]
    window = PROTOCOL["probe"]["response_window"]
    return sum(W.fired_in(p["fires"], unit, window) for p in probes) / len(probes)


def r_value(run: dict, phase: str) -> float:
    return window_fraction(run, phase, "B") - window_fraction(run, phase, "C")


def d_value(run: dict) -> float:
    return r_value(run, "post") - r_value(run, "pre")


def w_value(run: dict) -> float:
    return W.w_difference(run["weights_after_experience"], run["role_units"])


def a_fired(probe: dict, unit: str) -> bool:
    at = PROTOCOL["probe"]["a_fired_at"]
    return any(u == unit and offset == at for offset, u in probe["fires"])


def count_all_three(values: dict[int, dict[str, float]]) -> tuple[int, list[int]]:
    """同じ個体で ordered > 0 かつ ordered > shuffled かつ ordered > silent を満たす個体の数と、その seed。"""
    seeds = sorted(s for s, v in values.items()
                   if v["ordered"] > 0 and v["ordered"] > v["shuffled"] and v["ordered"] > v["silent"])
    return len(seeds), seeds


# ---- 完全性・操作の確認 ------------------------------------------------------------------

def completeness(data: dict, expected_seeds: list[int]) -> list[str]:
    problems = []
    meta = data["meta"]
    if meta["protocol"] != PROTOCOL:
        problems.append("データの protocol が今の protocol.yaml と違う")
    if meta["neuroarchitecture"] != W.manifest_raw():
        problems.append("データの設計図が今の neuroarchitecture.yaml と違う")
    got = [(r["seed"], r["condition"]) for r in data["runs"]]
    expected = {(s, c) for s in expected_seeds for c in CONDITIONS}
    if len(got) != len(set(got)) or set(got) != expected:
        problems.append(f"run の本数（{len(set(got))}/{len(expected)}）")
    tl = PROTOCOL["timeline"]
    for r in data["runs"]:
        where = f"seed {r['seed']} {r['condition']}"
        if r["pulses"] != tl["total_pulses"]:
            problems.append(f"{where}: 総 Pulse が {r['pulses']}")
        for phase in ("pre", "post"):
            t0s = [p["t0"] for p in r["probes"] if p["phase"] == phase]
            if t0s != W.probe_times(PROTOCOL, phase):
                problems.append(f"{where}: {phase} の試しの時刻が protocol と違う")
        if r["roles"] != W.role_receptors(PROTOCOL, r["seed"]):
            problems.append(f"{where}: 役の割り当てが protocol と違う")
    return problems


def manipulation(runs: list[dict]) -> tuple[list[str], dict]:
    m = PROTOCOL["judgment"]["manipulation"]
    delta = PROTOCOL["stimulus"]["delta_pulses"]
    problems: list[str] = []
    records: dict = {}

    # 試しの操作
    fractions = {}
    for c in CONDITIONS:
        probes = [(p, r["role_units"]["A"]) for r in runs if r["condition"] == c for p in r["probes"]]
        fractions[c] = sum(a_fired(p, u) for p, u in probes) / len(probes) if probes else None
        if fractions[c] is None or fractions[c] < m["min_a_fired_fraction"]:
            problems.append(f"試しの操作：{c} で s_A が t0＋{PROTOCOL['probe']['a_fired_at']} に発火した割合 {fractions[c]}")
    records["a_fired_fraction"] = fractions

    # 刺激の操作（刺激の列と、本体が実際に受けた感覚の出来事の両方）
    for r in runs:
        where = f"seed {r['seed']} {r['condition']}"
        expected = m["expected_counts"][r["condition"]]
        counts = W.stimulus_counts([tuple(s) for s in r["stimuli"]], delta)
        if {k: counts[k] for k in expected} != expected:
            problems.append(f"刺激の操作：{where} の刺激の数 {counts}")
        receptor_role = {rec: role for role, rec in r["roles"].items()}
        received = sorted([t, receptor_role[rec]] for t, rec in r["sensory"])
        if received != sorted(r["stimuli"]):
            problems.append(f"刺激の操作：{where} で本体が受けた感覚の出来事が刺激の列と違う")

    # 複製の操作
    broken = [(r["seed"], r["condition"]) for r in runs if not r["clone_identity"]["identical"]]
    if broken:
        problems.append(f"複製の操作：試しなしの複製が本体と一致しない {broken}")

    # 条件が分かれる前の一致
    split = m["identical_before_pulse"]
    by_seed = defaultdict(dict)
    for r in runs:
        by_seed[r["seed"]][r["condition"]] = r
    for seed, conds in sorted(by_seed.items()):
        views = []
        for c in CONDITIONS:
            r = conds[c]
            views.append(([a for a in r["activity"] if a[0] < split], r["connections_before_split"],
                          [p for p in r["probes"] if p["phase"] == "pre"]))
        if not all(v == views[0] for v in views[1:]):
            problems.append(f"条件が分かれる前の一致：seed {seed} の 3 条件が Pulse {split - 1} までに違う")
    return problems, records


# ---- 記録（判定に使わない） ------------------------------------------------------------

def observations(runs: list[dict], d: dict, w: dict) -> dict:
    tl = PROTOCOL["timeline"]
    w0 = {cid: v for cid, v in runs[0]["weights_initial"].items()}
    out: dict = {}

    # 釣り合いの確認：6 本の重みの w0 からの変化（経験の後の重み）
    balance = {}
    for c in CONDITIONS:
        changes = [r["weights_after_experience"][cid] - w0[cid] for r in runs if r["condition"] == c for cid in w0]
        balance[c] = {"mean_signed": mean(changes), "mean_abs": mean(abs(x) for x in changes)}
    out["balance_weight_change_from_w0"] = balance

    # 役で見た重み（経験の後・最後）
    def role_weight(r, key, a, b):
        u = r["role_units"]
        return r[key][W.connection_id(u[a], u[b])]

    pairs = [("A", "B"), ("A", "C"), ("B", "A"), ("C", "A"), ("B", "C"), ("C", "B")]
    out["role_weights_mean"] = {
        c: {key: {f"{a}->{b}": mean(role_weight(r, key, a, b) for r in runs if r["condition"] == c) for a, b in pairs}
            for key in ("weights_after_experience", "weights_end")}
        for c in CONDITIONS
    }

    # 重みの時間の変化（試しの時刻ごと、個体の平均）
    series = {}
    for c in CONDITIONS:
        rs = [r for r in runs if r["condition"] == c]
        times = [p["t0"] for p in rs[0]["probes"]]
        series[c] = {
            "t0": times,
            **{f"{a}->{b}": [mean(r["probes"][i]["weights"][W.connection_id(r["role_units"][a], r["role_units"][b])]
                                  for r in rs) for i in range(len(times))]
               for a, b in (("A", "B"), ("A", "C"), ("B", "A"))},
        }
    out["role_weight_series_mean"] = series

    # 発火の頻度（1000 Pulse あたり、役ごと、区間ごと、個体の平均）
    periods = {
        "settle": (1, tl["pre_probes"]["first"] - 1),
        "pre_probe_period": (tl["pre_probes"]["first"], tl["trials"]["first"] - 1),
        "experience": (tl["trials"]["first"], tl["post_probes"]["first"] - 1),
        "post_probe_period": (tl["post_probes"]["first"], tl["total_pulses"]),
    }
    rates = {}
    for c in CONDITIONS:
        rates[c] = {}
        for name, (lo, hi) in periods.items():
            rates[c][name] = {}
            for role in ("A", "B", "C"):
                vals = []
                for r in runs:
                    if r["condition"] != c:
                        continue
                    unit = r["role_units"][role]
                    n = sum(1 for p, u in r["activity"] if u == unit and lo <= p <= hi)
                    vals.append(1000 * n / (hi - lo + 1))
                rates[c][name][role] = mean(vals)
    out["fires_per_1000_pulses_mean"] = {"periods": periods, "by_condition": rates}

    # 試しの窓の発火の割合そのもの
    out["probe_window_fraction_mean"] = {
        c: {f"{role}_{phase}": mean(window_fraction(r, phase, role) for r in runs if r["condition"] == c)
            for phase in ("pre", "post") for role in ("B", "C")}
        for c in CONDITIONS
    }

    # 役の割り当てごとの D
    by_order = defaultdict(lambda: defaultdict(list))
    for r in runs:
        by_order[r["role_order_index"]][r["condition"]].append(d[r["seed"]][r["condition"]])
    out["d_by_role_order_mean"] = {str(k): {c: mean(v[c]) for c in CONDITIONS} for k, v in sorted(by_order.items())}
    return out


# ---- 本体 -----------------------------------------------------------------------------

def analyze_smoke(data: dict) -> dict:
    """動作確認：完全性・操作の確認・S1〜S3 だけ。D・W・H1・M は計算しない。"""
    sm = PROTOCOL["smoke"]["seeds"]
    expected_seeds = list(range(sm["first"], sm["last"] + 1))
    runs = data["runs"]
    problems = completeness(data, expected_seeds)
    manip_problems, manip_records = manipulation(runs) if not problems else ([], {})
    problems += manip_problems
    evaluation = SMOKE.evaluate(runs, PROTOCOL, W.trial_starts(PROTOCOL)) if not problems else None
    return {
        "experiment": "0012", "smoke": True,
        "note": "動作確認（README §5.5）。D・W・H1・M は計算していない",
        "git_commit": data["meta"]["git_commit"], "seeds": expected_seeds,
        "valid": not problems, "problems": problems, "manipulation": manip_records,
        "smoke_checks": evaluation,
        "smoke_passed": bool(evaluation and evaluation["passed"] and not problems),
    }


def analyze(data: dict) -> dict:
    if data["meta"].get("smoke"):
        return analyze_smoke(data)
    expected_seeds = list(range(PROTOCOL["seeds"]["first"], PROTOCOL["seeds"]["last"] + 1))
    runs = data["runs"]
    problems = completeness(data, expected_seeds)
    manip_problems, manip_records = manipulation(runs) if not problems else ([], {})
    problems += manip_problems

    d: dict[int, dict[str, float]] = defaultdict(dict)
    wv: dict[int, dict[str, float]] = defaultdict(dict)
    r_pre: dict[int, dict[str, float]] = defaultdict(dict)
    r_post: dict[int, dict[str, float]] = defaultdict(dict)
    for r in runs:
        d[r["seed"]][r["condition"]] = d_value(r)
        wv[r["seed"]][r["condition"]] = w_value(r)
        r_pre[r["seed"]][r["condition"]] = r_value(r, "pre")
        r_post[r["seed"]][r["condition"]] = r_value(r, "post")

    j = PROTOCOL["judgment"]
    h1_n, h1_seeds = count_all_three(d)
    m_n, m_seeds = count_all_three(wv)
    valid = not problems

    def verdict(n: int, need: int) -> str:
        if not valid:
            return "invalid"
        return "holds" if n >= need else "fails"

    report = {
        "experiment": "0012",
        "smoke": False,
        "git_commit": data["meta"]["git_commit"],
        "valid": valid,
        "problems": problems,
        "judgment": {
            "h1": {"status": verdict(h1_n, j["h1"]["min_seeds_all"]), "seeds_all_three": h1_n,
                   "required": j["h1"]["min_seeds_all"], "out_of": len(expected_seeds), "seeds": h1_seeds},
            "m": {"status": verdict(m_n, j["m"]["min_seeds_all"]), "seeds_all_three": m_n,
                  "required": j["m"]["min_seeds_all"], "out_of": len(expected_seeds), "seeds": m_seeds},
        },
        "manipulation": manip_records,
        "per_seed": {str(s): {"D": d[s], "W": wv[s], "R_pre": r_pre[s], "R_post": r_post[s]} for s in sorted(d)},
        "records": observations(runs, d, wv) if not completeness(data, expected_seeds) else None,
        "smoke_quantities": SMOKE.evaluate(runs, PROTOCOL, W.trial_starts(PROTOCOL)) if valid else None,  # 記録（判定に使わない）
    }
    return report


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    ALIGN.check(PROTOCOL)
    report = analyze(read(folder / "runs.json.gz"))
    (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"valid: {report['valid']}")
    for p in report["problems"]:
        print(f"  - {p}")
    if report["smoke"]:
        print("【動作確認（README §5.5）。D・W・H1・M は計算していない】")
        for name, c in (report["smoke_checks"] or {}).get("checks", {}).items():
            print(f"{name}: {'passed' if c['passed'] else 'FAILED'}  基準 {c['criterion']}")
        print(f"smoke_passed: {report['smoke_passed']}")
        print(f"saved {folder / 'report.json'}")
        return
    j = report["judgment"]
    print(f"H1: {j['h1']['status']} ({j['h1']['seeds_all_three']}/{j['h1']['out_of']}, 必要 {j['h1']['required']})")
    print(f"M : {j['m']['status']} ({j['m']['seeds_all_three']}/{j['m']['out_of']}, 必要 {j['m']['required']})")
    print(f"saved {folder / 'report.json'}")


if __name__ == "__main__":
    main()
