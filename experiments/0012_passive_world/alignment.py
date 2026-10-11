"""protocol.yaml（事前登録の正本）と、0012 用の設計図・人工世界の道具が同じ条件かを機械的に確かめる。

値を書き直すためではなく、ズレていたら実行・分析を止めるため。run.py と analyze.py の両方が最初に呼ぶ。
"""

import importlib.util
import itertools
from pathlib import Path

import yaml

from anima_ll.adapter.config.yaml_config_source import parse_neuroarchitecture

HERE = Path(__file__).resolve().parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(protocol: dict) -> None:
    W = _load("align_world_0012", HERE / "world.py")
    problems: list[str] = []

    def expect(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    brain = protocol["brain"]
    raw = W.manifest_raw()
    base = yaml.safe_load(Path(brain["dynamics_from"]).read_text(encoding="utf-8"))

    # 設計図：力学は minimal-v3 と同じ
    expect(raw["defaults"]["dynamics"] == base["defaults"]["dynamics"],
           f"設計図の defaults.dynamics が {brain['dynamics_from']} と違う")
    expect(raw["delta_ttl_pulses"] == base["delta_ttl_pulses"], "delta_ttl_pulses が minimal-v3 と違う")
    expect(all("dynamics" not in u for u in raw["units"]), "Unit ごとに力学を上書きしている")

    manifest = parse_neuroarchitecture(raw)
    sensory = list(brain["sensory_units"])
    expect([u.unit_id for u in manifest.units] == sensory, "設計図の Unit が sensory_units と違う")
    expect(all(u.output.kind == "relay" for u in manifest.units), "relay でない Unit がある")
    expect(not manifest.resource_classes and not manifest.effector_ids, "resources・effectors がある")
    expect(sorted(manifest.receptor_ids) == sorted(brain["receptors"]), "Receptor の口が protocol と違う")

    # 接続：Receptor → s は 1 対 1・receptor_weight・可塑性なし。s のあいだは 6 本すべて可塑性の対象
    projections = {(p.source_id, p.target_id): p for p in manifest.projections}
    expected_pairs = {(r, s) for r, s in brain["receptors"].items()}
    expected_pairs |= set(itertools.permutations(sensory, 2))
    expect(set(projections) == expected_pairs, "接続の組が protocol の想定（Receptor → s の 1 対 1 と s のあいだの 6 本）と違う")
    expect(all(p.source_port == "main" for p in manifest.projections), "main 以外の出力路がある")
    for r, s in brain["receptors"].items():
        p = projections.get((r, s))
        expect(p is not None and p.weight == brain["receptor_weight"] and not p.plastic,
               f"{r} → {s} が receptor_weight・可塑性なし ではない")

    # 可塑性：設計図の値が protocol と同じ。w0 ＝ w_max／2
    pl = dict(brain["plasticity"])
    w0_rule = pl.pop("w0")
    expect(raw["plasticity"] == pl, "設計図の plasticity が protocol の brain.plasticity と違う")
    expect(w0_rule == "half_w_max", f"w0 の決め方が half_w_max ではない（{w0_rule}）")
    spec = manifest.plasticity
    for a, b in itertools.permutations(sensory, 2):
        p = projections.get((a, b))
        expect(p is not None and p.plastic and spec is not None and p.weight == spec.w_max / 2,
               f"{a} → {b} が可塑性の対象・初期の重み w_max／2 ではない")

    # 人工世界：式の文字列は world.py が実装しているもの
    st = protocol["stimulus"]
    expect(st["role_assignment"] == W.ROLE_ASSIGNMENT, "role_assignment の式が world.py と違う")
    expect(st["rng_ordered"] == W.RNG_ORDERED, "rng_ordered の式が world.py と違う")
    expect(st["rng_shuffle"] == W.RNG_SHUFFLE, "rng_shuffle の式が world.py と違う")
    expect(st["conditions"] == ["ordered", "shuffled", "silent"], "conditions が ordered・shuffled・silent ではない")
    orders = [tuple(o) for o in st["role_orders"]]
    expect(len(orders) == 6 and len(set(orders)) == 6
           and all(sorted(o) == sorted(brain["receptors"]) for o in orders),
           "role_orders が 3 つの Receptor の 6 通りの並べ方になっていない")

    # 時間の流れ：試しの複製の期間が刺激と重ならない・総 Pulse の中に収まる
    tl, pr = protocol["timeline"], protocol["probe"]
    delta = st["delta_pulses"]
    stim_pulses = set()
    for t in W.trial_starts(protocol):
        stim_pulses |= {t, t + delta}
    for phase in ("pre", "post"):
        for t0 in W.probe_times(protocol, phase):
            span = set(range(t0, t0 + pr["clone_pulses"]))
            expect(not (span & stim_pulses), f"{phase} の試し t0={t0} の複製の期間に刺激がある")
            expect(t0 + pr["clone_pulses"] - 1 <= tl["total_pulses"], f"{phase} の試し t0={t0} が総 Pulse を超える")
    expect(max(W.probe_times(protocol, "pre")) < tl["trials"]["first"], "経験の前の試しが経験の開始より後にある")
    expect(min(W.probe_times(protocol, "post")) > max(stim_pulses), "経験の後の試しが最後の刺激より前にある")
    lo, hi = pr["response_window"]
    expect(pr["a_fired_at"] < lo <= hi < pr["clone_pulses"], "response_window・a_fired_at が複製の期間に収まらない")

    # 判定・操作の確認
    j = protocol["judgment"]
    n_seeds = protocol["seeds"]["last"] - protocol["seeds"]["first"] + 1
    expect(j["h1"]["min_seeds_all"] <= n_seeds and j["m"]["min_seeds_all"] <= n_seeds, "min_seeds_all が個体数を超える")
    expect(j["manipulation"]["identical_before_pulse"] == tl["trials"]["first"],
           "identical_before_pulse が経験の開始と違う")
    count = tl["trials"]["count"]
    n_b = round(st["p_b"] * count)
    ec = j["manipulation"]["expected_counts"]
    expect(ec["ordered"] == {"A": count, "B": n_b, "C": count - n_b, "a_then_b": n_b, "a_then_c": count - n_b},
           "expected_counts.ordered が p_b・試行数と合わない")
    expect(ec["shuffled"] == {"A": count, "B": n_b, "C": count - n_b}, "expected_counts.shuffled が合わない")
    expect(ec["silent"] == {"A": 0, "B": 0, "C": 0}, "expected_counts.silent が 0 ではない")
    # 動作確認（v0.3 §5.5）
    S = _load("align_smoke_0012", HERE / "smoke.py")
    sm = protocol["smoke"]
    smoke_seeds = list(range(sm["seeds"]["first"], sm["seeds"]["last"] + 1))
    formal = range(protocol["seeds"]["first"], protocol["seeds"]["last"] + 1)
    expect(not any(s in formal for s in smoke_seeds), "動作確認の seed が判定の seed の範囲と重なる")
    expect(sorted((s - 1) % 6 for s in smoke_seeds) == list(range(6)), "動作確認の seed が 6 通りの役の割り当てを一巡しない")
    try:
        expect(S.reliable_fraction(protocol) == j["manipulation"]["min_a_fired_fraction"], "reliable_fraction の解決が違う")
        expect(S.t_min(protocol) >= 1, "T_min が 1 未満")
    except ValueError as exc:
        problems.append(f"動作確認の値が解決できない：{exc}")
    checks = sm["checks"]
    expect(set(checks) == {"c1_no_baseline_ceiling", "c2_no_long_reverberation", "c3_sensory_not_buried"},
           "smoke.checks の項目が S1〜S3 と違う")
    expect(checks["c1_no_baseline_ceiling"]["max_fraction_exclusive"] == "reliable", "S1 の基準が reliable ではない")
    expect(checks["c3_sensory_not_buried"]["max_fraction_exclusive"] == "reliable", "S3 の基準が reliable ではない")
    c2 = checks["c2_no_long_reverberation"]
    expect(c2["min_spontaneous_interval"] == "derived_from_dynamics", "S2 の T_min が力学から導く形ではない")
    expect(c2["scope"] == ["main_runs_all_conditions_all_pulses", "pre_probe_clones"], "S2 の範囲が想定と違う")
    expect(c2["max_count"] == 0, "S2 の基準が 0 回ではない")
    expect(sm["on_failure"] == "stop_and_amend", "動作確認が落ちたときの扱いが stop_and_amend ではない")

    if problems:
        raise SystemExit("protocol と 0012 の設計図・道具がずれている：\n- " + "\n- ".join(problems))
