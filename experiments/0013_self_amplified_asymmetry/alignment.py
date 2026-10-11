"""protocol.yaml（事前登録の正本）と、0013 の設計図・道具が同じ条件かを機械的に確かめる。

ズレていたら実行・分析を止める。run.py と analyze.py の両方が最初に呼ぶ。
"""

import copy
import itertools
from pathlib import Path

import yaml

from anima_ll.adapter.config.yaml_config_source import parse_neuroarchitecture

ROOT = Path(__file__).resolve().parents[2]
SEEN_IN_0012 = set(range(1, 21)) | set(range(1001, 1021))   # 0012 の判定・事後の解析で、同じ設計図の刺激なしを見た seed


def check(protocol: dict) -> None:
    problems: list[str] = []

    def expect(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    brain = protocol["brain"]
    base = yaml.safe_load((ROOT / brain["dynamics_from"]).read_text(encoding="utf-8"))
    raw = {c: yaml.safe_load((ROOT / brain[c]).read_text(encoding="utf-8")) for c in ("plastic", "nonplastic")}
    expect(protocol["conditions"] == ["plastic", "nonplastic"], "conditions が plastic・nonplastic ではない")

    for c, r in raw.items():
        expect(r["defaults"]["dynamics"] == base["defaults"]["dynamics"], f"{c} の力学が minimal-v3 と違う")
        expect(all("dynamics" not in u for u in r["units"]), f"{c} で Unit ごとに力学を上書きしている")
        expect(not any(r["interfaces"][k] for k in ("resources", "receptors", "effectors")), f"{c} に外との口がある")
    # 双子：plastic の印だけが違う
    stripped = copy.deepcopy(raw["plastic"])
    for p in stripped["projections"]:
        p.pop("plastic", None)
    expect(stripped == raw["nonplastic"], "可塑性あり・なしの設計図が plastic の印以外でも違う")

    m = {c: parse_neuroarchitecture(r) for c, r in raw.items()}
    units = list(brain["units"])
    expect([u.unit_id for u in m["plastic"].units] == units, "Unit が protocol の units と違う")
    expect(all(u.output.kind == "relay" for u in m["plastic"].units), "relay でない Unit がある")
    expect({(p.source_id, p.target_id) for p in m["plastic"].projections} == set(itertools.permutations(units, 2)),
           "接続が 3 Unit の相互の 6 本ではない")
    spec = m["plastic"].plasticity
    expect(all(p.plastic and p.weight == spec.w_max / 2 for p in m["plastic"].projections),
           "可塑性ありの 6 本が、すべて可塑性の対象・初期の重み w_max／2 ではない")
    expect(not any(p.plastic for p in m["nonplastic"].projections), "可塑性なしに可塑性の対象の接続がある")

    tl, iv = protocol["timeline"], protocol["intervention"]
    total = tl["total_pulses"]
    for name in ("early_window", "late_window"):
        lo, hi = tl[name]
        expect(1 <= lo <= hi <= total, f"{name} が総 Pulse の中にない")
    expect(tl["early_window"][1] < tl["late_window"][0], "前の窓が後の窓より前にない")
    expect(list(iv["window"]) == list(tl["late_window"]), "介入の窓が後の窓と違う")
    expect(iv["at_pulse"] == iv["window"][0] - 1, "介入の時刻が介入の窓の直前ではない")
    expect(iv["arms"] == ["as_is", "reset_to_w0"], "介入の腕が as_is・reset_to_w0 ではない")
    expect(protocol["eligibility"]["pair_rule"] == "both_units_rho_at_least_1", "適格の決め方が想定と違う")

    j = protocol["judgment"]
    expect(j["primary"] == "c", "主の判定が c ではない")
    expect(j["birth_direction"] == "sign_of_nonplastic_early_window_f", "b_ij の決め方が想定と違う")
    expect(j["c"] == {"statistic": "sum(b * a_plastic_at_end)", "passes_if": "> 0"}, "C の定義が想定と違う")
    expect(j["h_a"] == {"statistic": "sum(b * f_late)", "passes_if": "plastic > nonplastic"}, "H_A の定義が想定と違う")
    expect(j["m"] == {"statistic": "sum(sign(a_at_intervention) * f_intervention_window)",
                      "passes_if": "as_is > reset_to_w0"}, "M の定義が想定と違う")
    expect(0 < j["min_fraction_of_eligible"] <= 1, "min_fraction_of_eligible が 0〜1 にない")

    formal = set(range(protocol["seeds"]["first"], protocol["seeds"]["last"] + 1))
    smoke = set(range(protocol["smoke"]["seeds"]["first"], protocol["smoke"]["seeds"]["last"] + 1))
    expect(not formal & SEEN_IN_0012, "判定の seed が、0012 で見た seed と重なる")
    expect(not smoke & SEEN_IN_0012, "動作確認の seed が、0012 で見た seed と重なる")
    expect(not formal & smoke, "判定の seed と動作確認の seed が重なる")
    expect(protocol["smoke"]["hide"] == ["c", "h_a", "m"], "動作確認で隠す量が c・h_a・m ではない")
    expect(protocol["smoke"]["on_failure"] == "stop_and_amend", "動作確認が落ちたときの扱いが stop_and_amend ではない")

    if problems:
        raise SystemExit("protocol と 0013 の設計図・道具がずれている：\n- " + "\n- ".join(problems))
