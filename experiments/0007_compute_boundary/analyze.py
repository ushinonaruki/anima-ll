"""実験 0007 の判定（事前登録の一部。測定の前にコミットする）。

判定（README「正式な判定」）：
- A0 Unit の力学を変えていない：コード・設定の差分なし ＋ 構造テスト ＋ stop で OLD・NEW-1・NEW-4 の
  全 Unit の状態の推移が seed ごとに完全一致
- A1 silent drop がない：契約テスト ＋ stop・smoke（新基盤）で消えた意図 0 件、旧来の claim・schedule のログなし
- A2 Worker の数で意図が変わらない：契約テスト ＋ stop で NEW-1 と NEW-4 の意図の列が seed ごとに完全一致
- A3 Unit ごとの FIFO と 1 in-flight、A4 work-conserving、A5 あふれは明示的な劣化：契約テスト
  （A3 は stop・smoke での同時実行数・開始順も確認する）

正常系の run（stop・smoke）であふれが起きたら、その run は invalid（検証条件を満たしていない）。
smoke の不整合（例外・消えた意図・二重実行など）は実装の誤りとして報告する。

使い方:
  python experiments/0007_compute_boundary/analyze.py [data/experiments/0007/results.json.gz]
"""

import gzip
import json
import subprocess
import sys
from pathlib import Path

DEFAULT = Path("data/experiments/0007/results.json.gz")
OLD_COMMIT = "3ae66e7"
UNCHANGED_PATHS = (
    "src/anima_ll/unit/dynamics",
    "src/anima_ll/domain/model/manifest.py",
    "config/neuroarchitecture/minimal-v1.yaml",
)
CONTRACT_TESTS = {
    "A0": ["tests/architecture/test_neuroarchitecture_unchanged.py", "tests/architecture/test_dependency_rules.py"],
    "A1": ["tests/integration/test_compute_boundary.py::test_a1_intent_waits_when_workers_are_full",
           "tests/integration/test_compute_boundary.py::test_a1_intent_from_busy_unit_is_kept",
           "tests/unit/test_execution_queue.py::test_never_drops_when_no_worker_is_free"],
    "A2": ["tests/integration/test_compute_boundary.py::test_a2_intents_are_identical_for_0_1_4_free_workers"],
    "A3": ["tests/integration/test_compute_boundary.py::test_a3_same_unit_runs_one_at_a_time_in_order",
           "tests/unit/test_execution_queue.py::test_same_unit_is_serialized_within_one_dispatch"],
    "A4": ["tests/integration/test_compute_boundary.py::test_a4_skips_unrunnable_intent_and_keeps_its_place",
           "tests/unit/test_execution_queue.py::test_busy_unit_is_skipped_but_keeps_its_place"],
    "A5": ["tests/integration/test_compute_boundary.py::test_a5_overflow_rejects_new_intent_and_marks_degraded",
           "tests/integration/test_compute_boundary.py::test_a5_kernel_error_is_distinct_from_overflow",
           "tests/unit/test_execution_queue.py::test_tail_drop_at_capacity",
           "tests/unit/test_execution_queue.py::test_capacity_is_per_resource_class"],
}


def run_pytest(targets: list[str]) -> bool:
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", *targets], capture_output=True, text=True)
    return proc.returncode == 0


def code_unchanged() -> bool | None:
    try:
        proc = subprocess.run(["git", "diff", "--quiet", OLD_COMMIT, "--", *UNCHANGED_PATHS])
    except OSError:
        return None
    return {0: True, 1: False}.get(proc.returncode)


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    with gzip.open(path, "rt", encoding="utf-8") as f:
        results = json.load(f)
    meta = results["meta"]
    seeds = meta["seeds"]
    problems: list[str] = []

    # ---- 完全性 ----
    complete = (not meta["quick"] and seeds == list(range(1, 21))
                and len(results["stop"]) == 3 * 20 and len(results["smoke"]) == 2 * 20)
    if not complete:
        problems.append("事前登録の全条件（seed 1〜20・quick なし）がそろっていない：正式判定に使えない")

    stop = {(r["condition"], r["seed"]): r for r in results["stop"]}
    new_runs = [r for r in results["stop"] if r["condition"] != "OLD"] + results["smoke"]

    # ---- 正常系の run の妥当性（あふれ・例外） ----
    invalid = [(r["condition"], r["seed"]) for r in new_runs if r["lifecycle"] and r["lifecycle"]["overflow"]]
    errors = [(r["condition"], r["seed"], r["error"]) for r in results["stop"] + results["smoke"] if r["error"]]
    if invalid:
        problems.append(f"正常系の run であふれ（invalid）：{invalid}")
    if errors:
        problems.append(f"例外：{errors}")

    # ---- A0 ----
    unchanged = code_unchanged()
    a0_states = all(
        stop[("OLD", s)]["states"] and stop[("OLD", s)]["states"] == stop[("NEW-1", s)]["states"]
        == stop[("NEW-4", s)]["states"] for s in seeds
    )
    a0_mismatch = [s for s in seeds if not (stop[("OLD", s)]["states"] == stop[("NEW-1", s)]["states"]
                                            == stop[("NEW-4", s)]["states"])]

    # ---- A1 ----
    lifecycle_ok = all(r["lifecycle"] and r["lifecycle"]["unaccounted"] == 0
                       and r["lifecycle"]["not_admitted_without_overflow"] == 0 for r in new_runs)
    no_old_logs = all("claim" not in r["event_types"] and "schedule" not in r["event_types"] for r in new_runs)

    # ---- A2 ----
    a2_equal = all(stop[("NEW-1", s)]["intents"] and stop[("NEW-1", s)]["intents"] == stop[("NEW-4", s)]["intents"]
                   for s in seeds)

    # ---- A3（結合での確認） ----
    a3_runs = all(r["lifecycle"]["max_running_per_unit"] <= 1 and r["lifecycle"]["order_violations"] == 0
                  and r["lifecycle"]["started_twice"] == 0 for r in new_runs)

    tests = {key: run_pytest(targets) for key, targets in CONTRACT_TESTS.items()}

    verdict = {
        "A0": bool(unchanged) and tests["A0"] and a0_states,
        "A1": tests["A1"] and lifecycle_ok and no_old_logs,
        "A2": tests["A2"] and a2_equal,
        "A3": tests["A3"] and a3_runs,
        "A4": tests["A4"],
        "A5": tests["A5"],
    }
    report = {
        "git_commit": meta["git_commit"],
        "complete": complete,
        "valid": complete and not invalid and not errors,
        "details": {
            "A0": {"code_unchanged_since_" + OLD_COMMIT: unchanged, "contract_tests": tests["A0"],
                   "state_trajectories_identical": a0_states, "mismatched_seeds": a0_mismatch},
            "A1": {"contract_tests": tests["A1"], "no_unaccounted_intents": lifecycle_ok,
                   "no_claim_or_schedule_logs": no_old_logs},
            "A2": {"contract_tests": tests["A2"], "stop_intents_identical_new1_new4": a2_equal},
            "A3": {"contract_tests": tests["A3"], "runs_serialized_in_order": a3_runs},
            "A4": {"contract_tests": tests["A4"]},
            "A5": {"contract_tests": tests["A5"]},
        },
        "verdict": verdict,
        "boundary_implemented": complete and not invalid and not errors and all(verdict.values()),
        "problems": problems,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
