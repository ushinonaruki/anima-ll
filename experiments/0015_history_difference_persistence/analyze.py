"""実験 0015 の判定（事前登録 v0.2 に従う。測定の前にコミットする）。判定の値の正本は protocol.yaml。

個体ごと（README §4）：
  W(t) ＝ w(A→B) − w(A→C)、D(t) ＝ W_ordered(t) − W_shuffled(t)
  D0 ＝ D(経験の終わり)、DT ＝ D(総 Pulse)、P ＝ sign(D0) × DT        主の判定 p：P ＞ 0
  適用対象：D0 ≠ 0 の個体（D0 ＝ 0 は N/A。0 に潰さず、分母に入れない）
判定：成り立った個体数 ÷ 適用対象の個体数 ≥ min_fraction（適用対象が 0 個体なら判定そのものが N/A）。
操作の確認（README §6）は、保存した生の記録から再検証する。1 つでも成り立たなければ invalid とし、
D0・DT・P は計算も表示もしない。

動作確認（smoke）のデータでは、完全性・操作の確認（README §7）だけを出す。D0・DT・P は計算しない。

使い方:
  python experiments/0015_history_difference_persistence/analyze.py [data/experiments/0015]
"""

import gzip
import importlib.util
import json
import sys
from pathlib import Path

import yaml

HERE = Path("experiments/0015_history_difference_persistence")
PROTOCOL = yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
DEFAULT_DIR = Path("data/experiments/0015")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load("alignment_0015", HERE / "alignment.py")
W = load("world_0015", HERE / "world.py")
CONDITIONS = PROTOCOL["stimulus"]["conditions"]
END = W.experience_end(PROTOCOL)
TOTAL = W.total_pulses(PROTOCOL)


def read(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


# ---- 完全性・操作の確認（生の記録から再検証する） ----------------------------------------------

def completeness(data: dict, expected: list[int]) -> list[str]:
    problems = []
    if data["meta"]["protocol"] != PROTOCOL:
        problems.append("データの protocol が今の protocol.yaml と違う")
    if data["meta"]["manifest"] != W.manifest_raw(PROTOCOL):
        problems.append("データの設計図が今の設計図と違う")
    got = [r["seed"] for r in data["runs"]]
    if sorted(got) != expected:
        problems.append(f"個体の数・seed が protocol と違う（{len(got)}/{len(expected)}）")
    times = [str(t) for t in W.sample_times(PROTOCOL)]
    for r in data["runs"]:
        for c in CONDITIONS:
            if list(r["conditions"][c]["samples"]) != times:
                problems.append(f"seed {r['seed']} {c}: 標本の時刻が protocol と違う")
    return problems


def manipulation(runs: list[dict]) -> list[str]:
    tol = PROTOCOL["judgment"]["manipulation"]["replay_matches_recorded_weights"]
    problems = []
    for r in runs:
        seed, conds = r["seed"], r["conditions"]
        tag = f"seed {seed}"
        problems += [f"{tag}: {p}" for p in W.check_stimulus_counts(
            PROTOCOL, seed, {c: conds[c]["sensory"] for c in CONDITIONS})]
        if any(p > END for c in CONDITIONS for p, _ in conds[c]["sensory"]):
            problems.append(f"{tag}: 経験の終わりより後に感覚の出来事がある")
        d = W.first_divergence(PROTOCOL, seed)
        if d != r["first_divergence"]:
            problems.append(f"{tag}: 札が最初に違う Pulse が刺激の列と合わない")
        o, s = conds["ordered"], conds["shuffled"]
        if o["birth"] != s["birth"]:
            problems.append(f"{tag}: 2 条件の出生時の状態が違う")
        if d is not None and ([a for a in o["activity"] if a[0] < d] != [a for a in s["activity"] if a[0] < d]
                              or o["before_divergence"] != s["before_divergence"]):
            problems.append(f"{tag}: 札が最初に違う Pulse より前の発火・状態が 2 条件で違う")
        for c in CONDITIONS:
            x = conds[c]
            for t in (END, TOTAL):
                err = W.replay_error(PROTOCOL, x["activity"], W.weights(x["samples"][str(t)]), t)
                if not err < tol:
                    problems.append(f"{tag} {c}: Pulse {t} の再生の計算と記録の重みの差 {err}")
    return problems


# ---- 判定の量（valid で、本番のときだけ計算する） ------------------------------------------------

def w_at(run: dict, condition: str, t: int) -> float:
    return W.w_contrast(W.weights(run["conditions"][condition]["samples"][str(t)]), run["roles"]["units"])


def d_at(run: dict, t: int) -> float:
    return w_at(run, "ordered", t) - w_at(run, "shuffled", t)


def statistics(run: dict) -> dict:
    d0, dt = d_at(run, END), d_at(run, TOTAL)
    applicable = d0 != 0
    p = W.sign(d0) * dt
    return {"D0": d0, "DT": dt, "applicable": applicable,
            "P": p if applicable else None, "p": (p > 0) if applicable else None}


# ---- 記録（判定に使わない。README §5） ------------------------------------------------------------

def records(runs: list[dict]) -> dict:
    out = {}
    times = W.sample_times(PROTOCOL)
    after = [t for t in times if t >= END]
    for r in runs:
        u = r["roles"]["units"]
        d0 = d_at(r, END)
        traj = {str(t): {"W_ordered": w_at(r, "ordered", t), "W_shuffled": w_at(r, "shuffled", t), "D": d_at(r, t),
                         **{f"a_{x}{y}_{c}": W.a_pair(W.weights(r["conditions"][c]["samples"][str(t)]), u[x], u[y])
                            for c in CONDITIONS for x, y in (("A", "B"), ("A", "C"))}}
                for t in times}
        crossing = next((t for t in after if W.sign(d0) * d_at(r, t) <= 0), None) if d0 != 0 else None
        out[str(r["seed"])] = {
            "D0": d0,
            "aligned_endpoint_change": (W.sign(d0) * d_at(r, TOTAL) - abs(d0)) if d0 != 0 else None,
            "first_sampled_crossing": crossing,
            "trajectory": traj,
        }
    out["D0_positive_individuals"] = sum(1 for r in runs if d_at(r, END) > 0)
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
    base = {"experiment": "0015", "smoke": smoke, "git_commit": data["meta"]["git_commit"], "seeds": expected,
            "valid": not problems, "problems": problems,
            "first_divergence": {str(r["seed"]): r["first_divergence"] for r in runs}}
    if smoke:
        return base | {"note": "動作確認（README §7：実行の操作の確認だけ）。D0・DT・P は計算していない",
                       "smoke_passed": not problems}
    if problems:
        return base | {"primary": "p", "judgment": None, "per_seed": None, "records": None,
                       "note": "invalid のため、D0・DT・P は計算していない"}
    per = {str(r["seed"]): statistics(r) for r in runs}
    applicable = [sd for sd in per if per[sd]["applicable"]]
    ok = [sd for sd in applicable if per[sd]["p"]]
    need = PROTOCOL["judgment"]["min_fraction"]
    if applicable:
        frac = len(ok) / len(applicable)
        status = "holds" if frac >= need else "fails"
    else:
        frac, status = None, "n/a"
    judgment = {"p": {"status": status, "satisfied": len(ok), "applicable": len(applicable),
                      "not_applicable": len(per) - len(applicable), "fraction": frac, "required_fraction": need,
                      "seeds": sorted(int(x) for x in ok)}}
    return base | {"primary": "p", "judgment": judgment, "per_seed": per, "records": records(runs)}


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    ALIGN.check(PROTOCOL)
    report = analyze(read(folder / "runs.json.gz"))
    (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"valid: {report['valid']}")
    for p in report["problems"][:50]:
        print(f"  - {p}")
    if report["smoke"]:
        print("【動作確認（README §7）。D0・DT・P は計算していない】")
        print(f"smoke_passed: {report['smoke_passed']}")
    elif report["judgment"] is None:
        print("invalid のため、D0・DT・P は計算していない")
    else:
        j = report["judgment"]["p"]
        print(f"p（主）: {j['status']} ({j['satisfied']}/{j['applicable']}、N/A {j['not_applicable']}、"
              f"必要な比 {j['required_fraction']})")
    print(f"saved {folder / 'report.json'}")


if __name__ == "__main__":
    main()
