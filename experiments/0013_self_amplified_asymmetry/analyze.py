"""実験 0013 の判定（事前登録の一部。測定の前にコミットする）。判定の値の正本は protocol.yaml。

個体ごと（README §4・5）。和はすべて適格な組についてとる。項が 0 の組・空の和は、ふつうの算術で 0：
  b_ij      ＝ sign(f_ij(E)、可塑性なし)
  C_birth   ＝ Σ b_ij · a_ij(総 Pulse の終わり、可塑性あり)              主の判定 C：C_birth ＞ 0
  H_A       ：Σ b_ij · f_ij(L) について、可塑性あり ＞ 可塑性なし
  M         ：Σ sign(a_ij(介入の時刻)) · f_ij(介入の窓) について、そのまま ＞ 重みを戻す
判定：成り立った個体数 ÷ 適格な個体数（適格な組が 1 つ以上ある個体）≥ min_fraction_of_eligible
操作の確認（README §5.1）が 1 つでも成り立たなければ invalid。

動作確認（smoke）のデータでは、完全性・操作の確認（README §5.1・§7）だけを出す。C・H_A・M の量は計算しない。
（v0.5：d ＝ 1 の組の数が 0 でないことの検査は撤去した。0 は正当な観測値で、F_ij の数え方は契約テストで保証する）

使い方:
  python experiments/0013_self_amplified_asymmetry/analyze.py [data/experiments/0013]
"""

import gzip
import importlib.util
import json
import statistics as st
import sys
from pathlib import Path

import yaml

HERE = Path("experiments/0013_self_amplified_asymmetry")
PROTOCOL = yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
DEFAULT_DIR = Path("data/experiments/0013")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load("alignment_0013", HERE / "alignment.py")
W = load("world_0013", HERE / "world.py")


def read(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def window(name: str) -> tuple[int, int]:
    return tuple(PROTOCOL["timeline"][name])


# ---- 判定の量 ---------------------------------------------------------------------------

def birth_direction(run: dict) -> dict[tuple[str, str], int]:
    F = W.follows(run["activity"]["nonplastic"], window("early_window"))
    return {(i, j): W.sign(W.f_asym(F, i, j)) for i, j in map(tuple, run["eligible_pairs"])}


def statistics(run: dict) -> dict:
    b = birth_direction(run)
    a_end = run["weights_end"]["plastic"]
    c = sum(b[(i, j)] * W.a_asym(a_end, i, j) for i, j in b)
    late = window("late_window")
    f_p = W.follows(run["activity"]["plastic"], late)
    f_n = W.follows(run["activity"]["nonplastic"], late)
    ha_p = sum(b[(i, j)] * W.f_asym(f_p, i, j) for i, j in b)
    ha_n = sum(b[(i, j)] * W.f_asym(f_n, i, j) for i, j in b)
    a_at = {cid: v["weight"] for cid, v in run["connections_at_intervention"].items()}
    s = {(i, j): W.sign(W.a_asym(a_at, i, j)) for i, j in b}
    iv = tuple(PROTOCOL["intervention"]["window"])
    f_as = W.follows(run["activity"]["as_is"], iv)
    f_rs = W.follows(run["activity"]["reset_to_w0"], iv)
    m_as = sum(s[p] * W.f_asym(f_as, *p) for p in s)
    m_rs = sum(s[p] * W.f_asym(f_rs, *p) for p in s)
    return {"b": {f"{i}-{j}": v for (i, j), v in b.items()},
            "c_birth": c, "c": c > 0,
            "h_a_plastic": ha_p, "h_a_nonplastic": ha_n, "h_a": ha_p > ha_n,
            "m_as_is": m_as, "m_reset": m_rs, "m": m_as > m_rs}


# ---- 完全性・操作の確認 -------------------------------------------------------------------

def completeness(data: dict, expected: list[int]) -> list[str]:
    problems = []
    if data["meta"]["protocol"] != PROTOCOL:
        problems.append("データの protocol が今の protocol.yaml と違う")
    if data["meta"]["manifests"] != {c: W.manifest_raw(PROTOCOL, c) for c in PROTOCOL["conditions"]}:
        problems.append("データの設計図が今の設計図と違う")
    got = [r["seed"] for r in data["runs"]]
    if sorted(got) != expected:
        problems.append(f"個体の数・seed が protocol と違う（{len(got)}/{len(expected)}）")
    return problems


def manipulation(runs: list[dict]) -> list[str]:
    tol = PROTOCOL["judgment"]["manipulation"]["replay_matches_recorded_weights"]
    problems = []
    for r in runs:
        c = r["checks"]
        for key in ("nonplastic_weights_unchanged", "identical_birth_state",
                    "clone_identity", "reset_weights_are_w0", "reset_traces_kept"):
            if not c[key]:
                problems.append(f"seed {r['seed']}: {key}")
        # 最初に重みが変わるまでの一致は、保存済みの真偽値ではなく、保存済みの生の発火の記録から再検証する
        # （d2710f3 の run.py は、重みが一度も変わらない個体で誤って false を保存していた。#58）
        if not W.identical_until_first_weight_change(r["activity"]["plastic"], r["activity"]["nonplastic"]):
            problems.append(f"seed {r['seed']}: identical_until_first_weight_change")
        if not c["replay_error"] < tol:
            problems.append(f"seed {r['seed']}: 再生の計算と記録の重みの差 {c['replay_error']}")
    return problems


# ---- 記録（判定に使わない。README §6） ------------------------------------------------------

def records(runs: list[dict]) -> dict:
    out = {"eligible_individuals": sum(1 for r in runs if r["eligible_pairs"]),
           "eligible_pairs_per_individual": [len(r["eligible_pairs"]) for r in runs]}
    w_max = W.parse_neuroarchitecture(W.manifest_raw(PROTOCOL, "plastic")).plasticity.w_max
    ends = [w for r in runs for w in r["weights_end"]["plastic"].values()]
    out["final_weights"] = {"mean": st.fmean(ends), "sd": st.pstdev(ends),
                            "near_bounds": sum(1 for w in ends if w < 0.05 * w_max or w > 0.95 * w_max),
                            "count": len(ends)}
    structures = {"cycle": 0, "ordered": 0, "has_tie": 0}
    for r in runs:
        w = r["weights_end"]["plastic"]
        signs = [W.sign(W.a_asym(w, i, j)) for i, j in (("s1", "s2"), ("s2", "s3"), ("s3", "s1"))]
        if 0 in signs:
            structures["has_tie"] += 1
        elif abs(sum(signs)) == 3:
            structures["cycle"] += 1      # s1→s2→s3→s1（またはその逆）の向きがそろっている
        else:
            structures["ordered"] += 1    # 先導 → 追従の順番のある構造（DAG）
    out["final_direction_structure"] = structures
    out["rates_per_1000"] = [
        {"seed": r["seed"], "rho": r["rho"],
         **{u: 1000 * sum(1 for p, v in r["activity"]["plastic"] if v == u) / PROTOCOL["timeline"]["total_pulses"]
            for u in PROTOCOL["brain"]["units"]}} for r in runs]
    return out


# ---- 本体 -----------------------------------------------------------------------------------

def analyze(data: dict) -> dict:
    smoke = bool(data["meta"].get("smoke"))
    s = PROTOCOL["smoke"]["seeds"] if smoke else PROTOCOL["seeds"]
    expected = list(range(s["first"], s["last"] + 1))
    runs = data["runs"]
    problems = completeness(data, expected)
    if not problems:
        problems += manipulation(runs)
    base = {"experiment": "0013", "smoke": smoke, "git_commit": data["meta"]["git_commit"], "seeds": expected,
            "valid": not problems, "problems": problems,
            "first_weight_change_pulse": {str(r["seed"]): W.first_weight_change(r["activity"]["plastic"]) for r in runs},
            "eligible_pairs": {str(r["seed"]): r["eligible_pairs"] for r in runs}}
    if smoke:
        return base | {"note": "動作確認（README §7：実行の操作の確認だけ）。C・H_A・M の量は計算していない",
                       "smoke_passed": not problems}

    if problems:
        # invalid のときは、判定の量（C・H_A・M）を計算も表示もしない（無効な run の結果を見ないため）
        return base | {"primary": "c", "judgment": None, "per_seed": None, "records": None,
                       "note": "invalid のため、C・H_A・M は計算していない"}
    per = {str(r["seed"]): statistics(r) for r in runs}
    eligible = [str(r["seed"]) for r in runs if r["eligible_pairs"]]
    need = PROTOCOL["judgment"]["min_fraction_of_eligible"]
    judgment = {}
    for key in ("c", "h_a", "m"):
        ok = [sd for sd in eligible if per[sd][key]]
        frac = len(ok) / len(eligible) if eligible else None
        status = "invalid" if not eligible else ("holds" if frac >= need else "fails")
        judgment[key] = {"status": status, "satisfied": len(ok), "eligible": len(eligible), "fraction": frac,
                         "required_fraction": need, "seeds": sorted(int(x) for x in ok)}
    return base | {"primary": "c", "judgment": judgment, "per_seed": per,
                   "records": records(runs)}


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    ALIGN.check(PROTOCOL)
    report = analyze(read(folder / "runs.json.gz"))
    (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"valid: {report['valid']}")
    for p in report["problems"]:
        print(f"  - {p}")
    if report["smoke"]:
        print("【動作確認（README §7）。C・H_A・M の量は計算していない】")
        print(f"smoke_passed: {report['smoke_passed']}")
    elif report["judgment"] is None:
        print("invalid のため、C・H_A・M は計算していない")
    else:
        for key, name in (("c", "C（主）"), ("h_a", "H_A"), ("m", "M")):
            j = report["judgment"][key]
            print(f"{name}: {j['status']} ({j['satisfied']}/{j['eligible']}、必要な比 {j['required_fraction']})")
    print(f"saved {folder / 'report.json'}")


if __name__ == "__main__":
    main()
