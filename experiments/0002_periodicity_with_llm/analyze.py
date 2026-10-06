"""実験 0002 の集計（事前登録の一部。実行前にコミットする）。

使い方:
  python experiments/0002_periodicity_with_llm/analyze.py data/logs/0002/l1/*.jsonl

- seed・実行環境はファイル名ではなく、ログ先頭の run 記録から読む
- 仮説の判定に使うのは --primary-seeds（既定 42 43）の run だけ。それ以外は参考として表示する
- Kernel の失敗が started の 1 割以上の run は無効（判定不能）とする
- 実行環境（Kernel）の違う run が混ざっていたら判定しない

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
MAX_ERROR_RATE = 0.1
DEFAULT_PRIMARY_SEEDS = (42, 43)


def coefficient_of_variation(pulses: list[float]) -> float | None:
    """発生した時点の列から、間隔の変動係数（標準偏差 / 平均）を出す。間隔が 2 つ未満なら None。"""
    intervals = [b - a for a, b in zip(pulses, pulses[1:])]
    if len(intervals) < 2:
        return None
    mean = statistics.fmean(intervals)
    return statistics.pstdev(intervals) / mean if mean else None


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run_record(events: list[dict]) -> dict | None:
    return next((e for e in events if e["type"] == "run"), None)


def environment_signature(run: dict) -> str:
    """実行環境の要約（Kernel の種類とモデル）。混ざっていないかを見るため。"""
    resources = run.get("environment", {}).get("resources", [])
    return ",".join(
        f"{r['resource_class']}={r['kernel']}" + (f"({r['params']['model']})" if "model" in r.get("params", {}) else "")
        for r in resources
    )


def analyze(events: list[dict]) -> dict:
    claims: dict[str, list[int]] = defaultdict(list)
    effects: list[int] = []
    effect_deltas: list[str] = []
    deltas: dict[str, dict] = {}
    task_inputs: dict[str, list[str]] = {}
    started = without_evidence = errors = 0
    receptor_inputs = 0
    last_pulse = 0
    pulse_time: dict[int, float] = {}
    pulse_dt: list[float] = []

    for e in events:
        t = e["type"]
        last_pulse = max(last_pulse, e.get("pulse", 0))
        if t == "pulse":
            pulse_time[e["pulse"]] = e["now"]
            pulse_dt.append(e["dt"])
        elif t == "claim":
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

    # 補助指標（判定には使わない）：壁時計での間隔。Pulse が遅れていれば Pulse 上の CV とずれる
    def wall(pulses: list[int]) -> list[float]:
        return [pulse_time[p] for p in pulses if p in pulse_time]

    unit_cv_wall = {u: coefficient_of_variation(wall(claims.get(u, []))) for u in KERNEL_UNITS}
    utterance_cv_wall = coefficient_of_variation(wall(effects))
    max_pulse_dt = max(pulse_dt[1:], default=None)  # 最初の Pulse は起動待ちを含むので除く
    ungrounded = sum(not grounded(d) for d in effect_deltas)

    error_rate = errors / started if started else 0.0
    valid = error_rate < MAX_ERROR_RATE

    h1: bool | None = all(cv is not None and cv < CV_THRESHOLD for cv in unit_cv.values())
    h2: bool | None
    if len(effects) < MIN_UTTERANCES:
        h2 = None
    else:
        h2 = utterance_cv is not None and utterance_cv < CV_THRESHOLD
    if not valid:
        h1 = h2 = None

    run = run_record(events) or {}
    return {
        "seed": run.get("seed"),
        "environment": environment_signature(run) if run else None,
        "git_commit": run.get("git_commit"),
        "valid": valid,
        "kernel_error_rate": error_rate,
        "pulses": last_pulse,
        "receptor_inputs": receptor_inputs,
        "claims": {u: len(claims.get(u, [])) for u in KERNEL_UNITS},
        "unit_cv": unit_cv,
        "utterances": len(effects),
        "utterance_cv": utterance_cv,
        "unit_cv_wall": unit_cv_wall,
        "utterance_cv_wall": utterance_cv_wall,
        "max_pulse_dt": max_pulse_dt,
        "tasks_started": started,
        "tasks_without_evidence": without_evidence,
        "kernel_errors": errors,
        "ungrounded_utterances": ungrounded,
        "H1_periodic": h1,
        "H2_periodic": h2,
    }


def fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


LABEL = {True: "周期的", False: "周期的でない", None: "判定不能"}


def verdict(values: list[bool | None]) -> str:
    if not values or None in values:
        return "判定不能"
    return "支持" if all(values) else "不支持"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--primary-seeds", nargs="+", type=int, default=list(DEFAULT_PRIMARY_SEEDS),
                        help="仮説の判定に使う個体の seed（既定 42 43）")
    parser.add_argument("--json", action="store_true", help="結果を JSON で出す")
    args = parser.parse_args()

    results = {str(path): analyze(load(path)) for path in args.logs}
    missing = [p for p, r in results.items() if r["seed"] is None]
    if missing:
        print("run 記録（seed・実行環境）のないログは集計できません:\n  " + "\n  ".join(missing))
        return 2

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for path, r in results.items():
            role = "判定" if r["seed"] in args.primary_seeds else "参考"
            print(f"## {Path(path).name}  [seed {r['seed']}・{role}]  {r['environment']}  commit={r['git_commit']}")
            print(f"  pulses={r['pulses']}  receptor_inputs={r['receptor_inputs']}"
                  f"  kernel_errors={r['kernel_errors']}/{r['tasks_started']}"
                  + ("" if r["valid"] else f"  ← 失敗率 {r['kernel_error_rate']:.0%} のため無効"))
            print("  H1 発火間隔の CV: " + "  ".join(f"{u}={fmt(r['unit_cv'][u])}(n={r['claims'][u]})" for u in KERNEL_UNITS)
                  + f"  → {LABEL[r['H1_periodic']]}")
            print(f"  H2 発話間隔の CV: {fmt(r['utterance_cv'])}(n={r['utterances']})  → {LABEL[r['H2_periodic']]}")
            print("  （補助）壁時計の CV: " + "  ".join(f"{u}={fmt(r['unit_cv_wall'][u])}" for u in KERNEL_UNITS)
                  + f"  発話={fmt(r['utterance_cv_wall'])}  Pulse 間隔の最大={fmt(r['max_pulse_dt'])} 秒")
            print(f"  根拠なしの計算: {r['tasks_without_evidence']}/{r['tasks_started']}"
                  f"  外からの根拠のない発話: {r['ungrounded_utterances']}/{r['utterances']}")

    runs = list(results.values())
    problems = []
    environments = {r["environment"] for r in runs}
    if len(environments) > 1:
        problems.append("実行環境の違う run が混ざっています: " + " / ".join(sorted(map(str, environments))))
    if any(r["receptor_inputs"] for r in runs):
        problems.append("受容器からの入力がある run が含まれています（実験 0002 は話しかけない条件）")
    primary = [r for r in runs if r["seed"] in args.primary_seeds]
    seeds = sorted(r["seed"] for r in primary)
    if seeds != sorted(args.primary_seeds):
        problems.append(f"判定に使う seed {sorted(args.primary_seeds)} の run がちょうど 1 本ずつそろっていません（あるもの: {seeds}）")

    print()
    if problems:
        print("判定しません:\n  " + "\n  ".join(problems))
        return 1
    print(f"判定（seed {', '.join(map(str, args.primary_seeds))}）: "
          f"H1 {verdict([r['H1_periodic'] for r in primary])} / "
          f"H2 {verdict([r['H2_periodic'] for r in primary])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
