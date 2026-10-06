"""実験 0002 の集計（事前登録の一部。実行前にコミットする）。

使い方:
  python experiments/0002_periodicity_with_llm/analyze.py data/logs/run-*-s42.jsonl data/logs/run-*-s43.jsonl ...

標準ライブラリだけで動く（Docker 内でも手元でも）。
"""

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

KERNEL_UNITS = ("u1", "u2", "u3")
RECEPTOR_PREFIX = "receptor."
CV_THRESHOLD = 0.2
MIN_UTTERANCES = 5


def coefficient_of_variation(pulses: list[int]) -> float | None:
    """発生した Pulse の列から、間隔の変動係数（標準偏差 / 平均）を出す。間隔が 2 つ未満なら None。"""
    intervals = [b - a for a, b in zip(pulses, pulses[1:])]
    if len(intervals) < 2:
        return None
    mean = statistics.fmean(intervals)
    return statistics.pstdev(intervals) / mean if mean else None


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def analyze(events: list[dict]) -> dict:
    claims: dict[str, list[int]] = defaultdict(list)
    effects: list[int] = []
    effect_deltas: list[str] = []
    deltas: dict[str, dict] = {}
    task_inputs: dict[str, list[str]] = {}
    started = without_evidence = errors = 0
    receptor_inputs = 0
    last_pulse = 0

    for e in events:
        t = e["type"]
        last_pulse = max(last_pulse, e.get("pulse", 0))
        if t == "claim":
            claims[e["unit_id"]].append(e["pulse"])
        elif t == "effect":
            effects.append(e["pulse"])
            effect_deltas.append(e["delta_id"])
        elif t == "delta":
            deltas[e["delta_id"]] = e
            if e["source_id"].startswith(RECEPTOR_PREFIX):
                receptor_inputs += 1
        elif t == "task_started":
            started += 1
            without_evidence += bool(e.get("without_evidence"))
            task_inputs[e["task_id"]] = e["input_delta_ids"]
        elif t == "task_completed" and e["status"] != "ok":
            errors += 1

    def grounded(delta_id: str) -> bool:
        """来歴を遡って、受容器からの入力に辿り着くか。"""
        stack, seen = [delta_id], set()
        while stack:
            current = deltas.get(stack.pop())
            if current is None or current["delta_id"] in seen:
                continue
            seen.add(current["delta_id"])
            if current["source_id"].startswith(RECEPTOR_PREFIX):
                return True
            stack += list(current.get("parent_delta_ids") or ())
            if current.get("origin_task_id"):
                stack += task_inputs.get(current["origin_task_id"], [])
        return False

    unit_cv = {u: coefficient_of_variation(claims.get(u, [])) for u in KERNEL_UNITS}
    utterance_cv = coefficient_of_variation(effects)
    ungrounded = sum(not grounded(d) for d in effect_deltas)

    h1 = all(cv is not None and cv < CV_THRESHOLD for cv in unit_cv.values())
    if len(effects) < MIN_UTTERANCES:
        h2: bool | None = None
    else:
        h2 = utterance_cv is not None and utterance_cv < CV_THRESHOLD

    return {
        "pulses": last_pulse,
        "receptor_inputs": receptor_inputs,
        "claims": {u: len(claims.get(u, [])) for u in KERNEL_UNITS},
        "unit_cv": unit_cv,
        "utterances": len(effects),
        "utterance_cv": utterance_cv,
        "tasks_started": started,
        "tasks_without_evidence": without_evidence,
        "kernel_errors": errors,
        "ungrounded_utterances": ungrounded,
        "H1_periodic": h1,
        "H2_periodic": h2,
    }


def fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true", help="結果を JSON で出す")
    args = parser.parse_args()

    results = {str(path): analyze(load(path)) for path in args.logs}
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for path, r in results.items():
            print(f"## {Path(path).name}")
            print(f"  pulses={r['pulses']}  receptor_inputs={r['receptor_inputs']}  kernel_errors={r['kernel_errors']}")
            print("  H1 発火間隔の CV: " + "  ".join(f"{u}={fmt(r['unit_cv'][u])}(n={r['claims'][u]})" for u in KERNEL_UNITS)
                  + f"  → {'周期的' if r['H1_periodic'] else '周期的でない'}")
            h2 = {True: "周期的", False: "周期的でない", None: "判定不能（発話が少ない）"}[r["H2_periodic"]]
            print(f"  H2 発話間隔の CV: {fmt(r['utterance_cv'])}(n={r['utterances']})  → {h2}")
            print(f"  根拠なしの計算: {r['tasks_without_evidence']}/{r['tasks_started']}"
                  f"  外からの根拠のない発話: {r['ungrounded_utterances']}/{r['utterances']}")

    runs = list(results.values())
    if any(r["receptor_inputs"] for r in runs):
        print("\n注意: 受容器からの入力があるログが含まれています（実験 0002 は話しかけない条件）")
    h1_supported = all(r["H1_periodic"] for r in runs)
    h2_values = [r["H2_periodic"] for r in runs]
    h2 = None if None in h2_values else all(h2_values)
    print(f"\n判定（{len(runs)} 本）: H1 {'支持' if h1_supported else '不支持'} / "
          f"H2 {'判定不能' if h2 is None else ('支持' if h2 else '不支持')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
