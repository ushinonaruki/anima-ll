"""実験 0014 の判定（事前登録 v0.3 に従う。測定の前にコミットする）。判定の値の正本は protocol.yaml。

個体ごと（README §4・5）：
  ΔR(t0) ＝ [B − C](as_is) − [B − C](equalized)、B・C は t0 ＋ read_at に発火したら 1
  p_i    ＝ mean_t0 [ sign(W_probe(t0)) × ΔR(t0) ]（順序あり）        主の判定 p：p_i ＞ 0
  w      ：W_post（probes.first − 1 の終わり）について、順序あり ＞ 順序を崩した
判定：成り立った個体数 ÷ 個体数 ≥ min_fraction。項が 0 の試しは、ふつうの算術で 0（専用の分岐を置かない）。
操作の確認（README §6）は、保存した生の記録から再検証する。1 つでも成り立たなければ invalid とし、
p・w の量は計算も表示もしない。

動作確認（smoke）のデータでは、完全性・操作の確認（README §7）だけを出す。p・w の量は計算しない。

使い方:
  python experiments/0014_order_to_activity/analyze.py [data/experiments/0014]
"""

import gzip
import importlib.util
import json
import statistics as st
import sys
from pathlib import Path

import yaml

HERE = Path("experiments/0014_order_to_activity")
PROTOCOL = yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
DEFAULT_DIR = Path("data/experiments/0014")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load("alignment_0014", HERE / "alignment.py")
W = load("world_0014", HERE / "world.py")
CONDITIONS = PROTOCOL["stimulus"]["conditions"]
READ_AT = PROTOCOL["probe"]["read_at"]


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
    times = W.probe_times(PROTOCOL)
    for r in data["runs"]:
        for c in CONDITIONS:
            if [p["t0"] for p in r["conditions"][c]["probes"]] != times:
                problems.append(f"seed {r['seed']} {c}: 試しの時刻が protocol と違う")
    return problems


def manipulation(runs: list[dict]) -> list[str]:
    w_max = W.w_max(PROTOCOL)
    first_probe = PROTOCOL["timeline"]["probes"]["first"]
    problems = []
    for r in runs:
        seed, conds = r["seed"], r["conditions"]
        tag = f"seed {seed}"
        # 刺激の数（刺激の列と、本体が受けた感覚の出来事の両方）
        problems += [f"{tag}: {p}" for p in W.check_stimulus_counts(
            PROTOCOL, seed, {c: conds[c]["sensory"] for c in CONDITIONS})]
        if any(p >= first_probe for c in CONDITIONS for p, _ in conds[c]["sensory"]):
            problems.append(f"{tag}: 本体が試しの区間に感覚の出来事を受けた")
        # 分かれる前の一致
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
            # 複製の一致
            start = x["clone"]["from"]
            if ([a for a in x["activity"] if a[0] > start] != x["clone"]["activity"]
                    or x["clone"]["connections_end"] != x["connections_end"]):
                problems.append(f"{tag} {c}: clone_identity")
            # 試しの入力・介入の複製・2 腕の t0 ＋ 1 の一致
            for rec in x["probes"]:
                problems += [f"{tag} {c}: {p}" for p in W.check_probe(PROTOCOL, seed, rec, w_max)]
    return problems


# ---- 判定の量（valid で、本番のときだけ計算する） ------------------------------------------------

def p_value(run: dict, condition: str) -> float:
    units = run["roles"]["units"]
    probes = run["conditions"][condition]["probes"]
    return st.fmean(W.sign(W.w_probe(rec, units)) * W.delta_r(rec, units, READ_AT) for rec in probes)


def w_post(run: dict, condition: str) -> float:
    c = run["conditions"][condition]["connections_post"]
    return W.w_difference({k: v["weight"] for k, v in c.items()}, run["roles"]["units"])


def statistics(run: dict) -> dict:
    p = p_value(run, "ordered")
    wo, ws = w_post(run, "ordered"), w_post(run, "shuffled")
    return {"p_i": p, "p": p > 0, "w_post_ordered": wo, "w_post_shuffled": ws, "w": wo > ws}


# ---- 記録（判定に使わない。README §5 の記録） ----------------------------------------------------

def records(runs: list[dict]) -> dict:
    out = {}
    for r in runs:
        u = r["roles"]["units"]
        row = {}
        for c in CONDITIONS:
            probes = r["conditions"][c]["probes"]
            r_as_is = [W.fired_at(p["activity"]["as_is"], u["B"], p["t0"] + READ_AT)
                       - W.fired_at(p["activity"]["as_is"], u["C"], p["t0"] + READ_AT) for p in probes]
            row[c] = {
                "mean_R_as_is": st.fmean(r_as_is),
                "intervention_effect": p_value(r, c),
                "w_post": w_post(r, c),
                "a_fired_fraction": st.fmean(W.fired_at(p["activity"]["as_is"], u["A"], p["t0"] + 1) for p in probes),
                "w_probe": [W.w_probe(p, u) for p in probes],
                "delta_r": [W.delta_r(p, u, READ_AT) for p in probes],
                "adaptation_at_fork": {role: [p["fork"]["as_is"]["units"][u[role]]["adaptation"] for p in probes]
                                       for role in ("B", "C")},
            }
        row["ordered_minus_shuffled_mean_R_as_is"] = row["ordered"]["mean_R_as_is"] - row["shuffled"]["mean_R_as_is"]
        out[str(r["seed"])] = row
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
    base = {"experiment": "0014", "smoke": smoke, "git_commit": data["meta"]["git_commit"], "seeds": expected,
            "valid": not problems, "problems": problems,
            "first_divergence": {str(r["seed"]): r["first_divergence"] for r in runs}}
    if smoke:
        return base | {"note": "動作確認（README §7：実行の操作の確認だけ）。p・w の量は計算していない",
                       "smoke_passed": not problems}
    if problems:
        return base | {"primary": "p", "judgment": None, "per_seed": None, "records": None,
                       "note": "invalid のため、p・w は計算していない"}
    per = {str(r["seed"]): statistics(r) for r in runs}
    need = PROTOCOL["judgment"]["min_fraction"]
    judgment = {}
    for key in ("p", "w"):
        ok = [sd for sd in per if per[sd][key]]
        frac = len(ok) / len(per)
        judgment[key] = {"status": "holds" if frac >= need else "fails", "satisfied": len(ok), "individuals": len(per),
                         "fraction": frac, "required_fraction": need, "seeds": sorted(int(x) for x in ok)}
    return base | {"primary": "p", "judgment": judgment, "per_seed": per, "records": records(runs)}


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    ALIGN.check(PROTOCOL)
    report = analyze(read(folder / "runs.json.gz"))
    (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"valid: {report['valid']}")
    for p in report["problems"][:50]:
        print(f"  - {p}")
    if len(report["problems"]) > 50:
        print(f"  …ほか {len(report['problems']) - 50} 件")
    if report["smoke"]:
        print("【動作確認（README §7）。p・w の量は計算していない】")
        print(f"smoke_passed: {report['smoke_passed']}")
    elif report["judgment"] is None:
        print("invalid のため、p・w は計算していない")
    else:
        for key, name in (("p", "p（主）"), ("w", "w（副）")):
            j = report["judgment"][key]
            print(f"{name}: {j['status']} ({j['satisfied']}/{j['individuals']}、必要な比 {j['required_fraction']})")
    print(f"saved {folder / 'report.json'}")


if __name__ == "__main__":
    main()
