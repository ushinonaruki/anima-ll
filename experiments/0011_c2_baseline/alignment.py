"""protocol.yaml（事前登録の正本）と、再利用している旧の実装の定数が同じ条件かを機械的に確かめる。

値を書き直すためではなく、ズレていたら実行・分析を止めるため。run.py と analyze.py の両方が最初に呼ぶ。
"""

import importlib.util
from pathlib import Path


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pairs(xs) -> list[tuple[float, float]]:
    return [(float(a), float(t)) for a, t in xs]


def check(protocol: dict) -> None:
    R4 = _load("align_run_0004", "experiments/0004_adaptation/run.py")
    R5 = _load("align_run_0005", "experiments/0005_response_threshold/run.py")
    A4 = _load("align_analyze_0004", "experiments/0004_adaptation/analyze.py")
    A5 = _load("align_analyze_0005", "experiments/0005_response_threshold/analyze.py")
    problems = []

    def expect(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    conds = _pairs(protocol["adaptation_conditions"])
    expect(protocol["plasticity"] == "none", "plasticity が none ではない")
    # B2・B4：0005 の手順
    # YAML は `0005` を数（8 進の 5）として読むので、4 桁の実験番号に戻して比べる（protocol.yaml は書き換えない）
    procedure = protocol["b2"]["procedure"]
    procedure = f"{procedure:04d}" if isinstance(procedure, int) else str(procedure)
    expect(procedure == "0005", f"b2.procedure が 0005 ではない（{procedure}）")
    expect(protocol["b2"]["required"] == "all_identical", "b2.required が all_identical ではない")
    expect(protocol["b2"]["compare_with"] == "old_reference.k2_data", "b2.compare_with が違う")
    expect(_pairs(R5.CONDITIONS) == conds, "0005 の run.py の CONDITIONS が protocol の adaptation_conditions と違う")
    expect(_pairs(A5.EXPECTED_CONDITIONS) == conds, "0005 の analyze.py の条件が protocol と違う")
    expect(list(R5.SEEDS) == list(range(protocol["seeds"]["first"], protocol["seeds"]["last"] + 1)),
           "0005 の SEEDS が protocol の seeds と違う")
    expect(A5.EXPECTED_SEEDS == list(range(protocol["seeds"]["first"], protocol["seeds"]["last"] + 1)),
           "0005 の analyze.py の seed が protocol と違う")
    expect({"conditioning": list(R5.CONDITIONING), "probe": R5.PROBE, "pulses": R5.PULSES,
            "probe_weights": list(R5.PROBE_WEIGHTS), "conditioning_weight": 1.0} == A5.EXPECTED_PROTOCOL,
           "0005 の run.py と analyze.py の手順が違う")
    expect(A5.IMMEDIATE == R5.PROBE + 1, "0005 の IMMEDIATE が probe の次の Pulse ではない")
    expect(_pairs(protocol["b4"]["reference_conditions"]) == _pairs(A5.H2_REFERENCE),
           "b4.reference_conditions が 0005 の基準の条件と違う")
    # B3：0004 パート A の手順
    w = protocol["b3"]["windows"]
    expect(tuple(w["early"]) == tuple(A4.EARLY), "b3.windows.early が 0004 の EARLY と違う")
    expect(tuple(w["late"]) == tuple(A4.LATE), "b3.windows.late が 0004 の LATE と違う")
    expect(tuple(protocol["b3"]["applicability"]["window"]) == tuple(A4.LATE),
           "b3.applicability.window が 0004 の終盤と違う")
    expect(_pairs(protocol["b3"]["reference_conditions"]) == _pairs(A4.H1_REFERENCE),
           "b3.reference_conditions が 0004 の基準の条件と違う")
    expect(protocol["b3"]["silent_pulses"] == R4.SILENT_PULSES, "b3.silent_pulses が 0004 と違う")
    # B1：入力なしの長さ・パート B の台本の元
    expect(protocol["b1"]["silent_pulses"] == R4.SILENT_PULSES, "b1.silent_pulses が 0004 と違う")
    expect(protocol["b1"]["inputs"] == ["silent", "part_b"], "b1.inputs が silent・part_b ではない")
    expect(len({k["id"] for k in protocol["b1"]["kernel_conditions"]}) == len(protocol["b1"]["kernel_conditions"]),
           "b1.kernel_conditions の id が重複している")
    # 参照値の選び方の規則（analyze.py が実装しているのはこの規則だけ）
    expect(protocol["reference_value_rule"]["selection"] == "min_alpha_times_tau_then_alpha",
           "reference_value_rule.selection が analyze.py の実装している規則と違う")
    # 旧の比較データ
    for key in ("k1_data", "k2_data"):
        expect(Path(protocol["old_reference"][key]).exists(), f"old_reference.{key} がない")

    if problems:
        raise SystemExit("protocol と再利用する旧の実装がずれている：\n- " + "\n- ".join(problems))
