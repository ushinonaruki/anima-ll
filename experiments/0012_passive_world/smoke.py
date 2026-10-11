"""実験 0012 v0.3 の動作確認 S1〜S3 の集計（README §5.5、protocol.yaml の smoke）。

run.py が保存した記録（本体の発火・感覚の出来事・試しの複製の発火）だけを読む純粋な関数。
判定の指標（D・W・H1・M）はここでは計算しない。
"""

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path

import yaml


def reliable_fraction(protocol: dict) -> float:
    """「確実に起きる」の水準。protocol の smoke.reliable_fraction が指す値（manipulation.min_a_fired_fraction）。"""
    ref = protocol["smoke"]["reliable_fraction"]
    if ref != "manipulation.min_a_fired_fraction":
        raise ValueError(f"smoke.reliable_fraction の参照先が想定と違う: {ref}")
    return float(protocol["judgment"]["manipulation"]["min_a_fired_fraction"])


def t_min(protocol: dict) -> int:
    """発火して activity が 0 に戻った Unit が、入力なしで次に発火できる最短の Pulse 数（README §5.5）。

    出生時のばらつきの範囲で最も速く戻る個体（内在的駆動 ×(1 ＋ jitter)、閾値 ×(1 − jitter)）、順応 0、
    Δt ＝ pulse_interval_seconds で、activity ← activity × decay^Δt ＋ drive × Δt が 0 から閾値に届くまでの Pulse 数。
    実装の 1 Pulse の更新で境界になることは tests/integration/test_min_spontaneous_interval_0012.py が確かめる。
    """
    dyn = yaml.safe_load(Path(protocol["brain"]["dynamics_from"]).read_text(encoding="utf-8"))["defaults"]["dynamics"]
    dt = float(protocol["timeline"]["pulse_interval_seconds"])
    step_decay = dyn["decay"] ** dt
    drive = dyn["intrinsic_drive"] * (1 + dyn["jitter"]) * dt
    threshold = dyn["threshold"] * (1 - dyn["jitter"])
    if not 0 < step_decay < 1 or drive <= 0:
        raise ValueError("T_min を決められない力学の値")
    # a_k ＝ drive × (1 − step_decay^k)／(1 − step_decay) ≥ threshold となる最小の k
    ratio = 1 - threshold * (1 - step_decay) / drive
    if ratio <= 0:
        raise ValueError("最速の個体でも自力で閾値に届かない（T_min が定義できない）")
    return math.ceil(math.log(ratio) / math.log(step_decay))


def receptor_of(protocol: dict) -> dict[str, str]:
    """s → その s につながる Receptor（1 対 1）。"""
    return {unit: receptor for receptor, unit in protocol["brain"]["receptors"].items()}


def reexcitations(firings: Iterable[tuple[int, str]], sensory: Iterable[tuple[int, str]],
                  protocol: dict, *, count_from: int = 0) -> list[dict]:
    """再興奮：同じ s が T_min 未満の間隔で 2 回発火し、あとの発火の直前の Pulse に、その s の Receptor の
    感覚の出来事がないもの。あとの発火の Pulse が count_from 以上のものだけを返す。
    """
    limit = t_min(protocol)
    to_receptor = receptor_of(protocol)
    sensory_at = {(p, r) for p, r in sensory}
    by_unit: dict[str, list[int]] = defaultdict(list)
    for p, u in firings:
        by_unit[u].append(p)
    found = []
    for unit, pulses in by_unit.items():
        pulses = sorted(pulses)
        for a, b in zip(pulses, pulses[1:]):
            if b < count_from or b - a >= limit:
                continue
            if (b - 1, to_receptor[unit]) in sensory_at:
                continue      # あとの発火は感覚の入力による
            found.append({"unit": unit, "first": a, "second": b, "interval": b - a})
    return found


def s1_fractions(runs: Iterable[dict], protocol: dict) -> dict[str, float]:
    """S1：経験の前の試し（ordered の分。3 条件は Pulse 1799 まで同じ）で、s_B・s_C が窓で発火した割合（まとめた値）。"""
    lo, hi = protocol["probe"]["response_window"]
    hits = {"B": 0, "C": 0}
    n = 0
    for r in runs:
        if r["condition"] != "ordered":
            continue
        for probe in r["probes"]:
            if probe["phase"] != "pre":
                continue
            n += 1
            for role in ("B", "C"):
                unit = r["role_units"][role]
                hits[role] += any(u == unit and lo <= off <= hi for off, u in probe["fires"])
    if n == 0:
        raise ValueError("経験の前の試しがない")
    return {role: hits[role] / n for role in hits} | {"probes": n}


def s2_reexcitations(runs: Iterable[dict], protocol: dict) -> dict:
    """S2：本体（3 条件・全 Pulse）と、経験の前の試しの複製（本体の t0 − 1 までの発火の列につないで数える）の再興奮。"""
    main, clones = [], []
    for r in runs:
        where = {"seed": r["seed"], "condition": r["condition"]}
        main += [where | x for x in reexcitations(map(tuple, r["activity"]), map(tuple, r["sensory"]), protocol)]
        if r["condition"] != "ordered":
            continue      # 経験の前の試しは 3 条件で同じなので、ordered の分だけ数える
        for probe in r["probes"]:
            if probe["phase"] != "pre":
                continue
            t0 = probe["t0"]
            history = [(p, u) for p, u in r["activity"] if p < t0]
            fires = history + [(t0 + off, u) for off, u in probe["fires"]]
            sensory = [(p, rec) for p, rec in r["sensory"] if p < t0] + [(t0, r["roles"]["A"])]
            clones += [where | {"t0": t0} | x
                       for x in reexcitations(fires, sensory, protocol, count_from=t0)]
    return {"t_min": t_min(protocol), "main": main, "pre_probe_clones": clones,
            "count": len(main) + len(clones)}


def s3_fraction(runs: Iterable[dict], protocol: dict, trial_starts: Iterable[int]) -> dict:
    """S3：順序ありの経験で、s_B と s_C が t ＋ 2 に両方発火した試行の割合（まとめた値）。"""
    starts = list(trial_starts)
    both = n = 0
    for r in runs:
        if r["condition"] != "ordered":
            continue
        fired: Mapping[int, set] = defaultdict(set)
        for p, u in r["activity"]:
            fired[p].add(u)
        units = r["role_units"]
        for t in starts:
            n += 1
            both += {units["B"], units["C"]} <= fired.get(t + 2, set())
    if n == 0:
        raise ValueError("順序ありの試行がない")
    return {"fraction": both / n, "trials": n}


def evaluate(runs: list[dict], protocol: dict, trial_starts: Iterable[int]) -> dict:
    """S1〜S3 を基準に照らす。D・W・H1・M は計算しない。"""
    reliable = reliable_fraction(protocol)
    s1 = s1_fractions(runs, protocol)
    s2 = s2_reexcitations(runs, protocol)
    s3 = s3_fraction(runs, protocol, trial_starts)
    checks = {
        "S1": {"passed": s1["B"] < reliable and s1["C"] < reliable, "value": s1, "criterion": f"B・C どちらも < {reliable}"},
        "S2": {"passed": s2["count"] <= protocol["smoke"]["checks"]["c2_no_long_reverberation"]["max_count"],
               "value": s2, "criterion": f"再興奮（間隔 < T_min ＝ {s2['t_min']}、感覚によらない）が "
                                         f"{protocol['smoke']['checks']['c2_no_long_reverberation']['max_count']} 回以下"},
        "S3": {"passed": s3["fraction"] < reliable, "value": s3, "criterion": f"< {reliable}"},
    }
    return {"reliable_fraction": reliable, "checks": checks, "passed": all(c["passed"] for c in checks.values())}
