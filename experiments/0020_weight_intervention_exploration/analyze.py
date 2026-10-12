"""探索 0020 の記録の解析（探索の設計 v0.1 に従う。判定を置かない）。正本は protocol.yaml。

1. 操作の確認（README §5）を、保存した生の記録から再検証する。1 つでも満たされなければ invalid とし、
   記録の量は計算するが「invalid のデータの記録」と明記する（探索なので判定はもともとない）
2. 記録（README §4）を、生の記録から個体ごとに全件計算する。holds／fails へは換算しない
3. 要約は個体の数え上げだけ（記述）。都合のよい個体を選ばない（全 100 個体を per_seed に出す）

使い方:
  python experiments/0020_weight_intervention_exploration/analyze.py [data/experiments/0020]
  python experiments/0020_weight_intervention_exploration/analyze.py <フォルダ> --check   # 道具の通しの確認（操作の確認だけ）
"""

import gzip
import importlib.util
import json
import math
import sys
from pathlib import Path

import yaml

HERE = Path("experiments/0020_weight_intervention_exploration")
PROTOCOL = yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
DEFAULT_DIR = Path("data/experiments/0020")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load("alignment_0020", HERE / "alignment.py")
W = load("world_0020", HERE / "world.py")
END = W.experience_end(PROTOCOL)
TOTAL = W.total_pulses(PROTOCOL)
DT = PROTOCOL["timeline"]["pulse_interval_seconds"]
SPEC = W.plasticity(PROTOCOL)


def read(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


# ---- 操作の確認（生の記録から） ------------------------------------------------------------------

def completeness(data: dict, expected: list[int]) -> list[str]:
    problems = []
    if data["meta"]["protocol"] != PROTOCOL:
        problems.append("データの protocol が今の protocol.yaml と違う")
    if data["meta"]["manifest"] != W.manifest_raw(PROTOCOL):
        problems.append("データの設計図が今の設計図と違う")
    got = [r["seed"] for r in data["runs"]]
    if sorted(got) != expected:
        problems.append(f"個体の数・seed が protocol と違う（{len(got)}/{len(expected)}）")
    return problems


def arm_spikes(run: dict, arm: str) -> list[list]:
    return run["arms"]["spikes"][arm]


def affine_all(run: dict, arm: str) -> dict:
    """各腕・各接続の affine の係数（介入の直後の状態から、その腕の自分の発火の列で）。"""
    fork = run["fork"][arm]["connections"]
    spikes = arm_spikes(run, arm)
    out = {}
    for cid, st in fork.items():
        src, dst = W.unit_of(cid)
        out[cid] = W.affine(st, [p for p, u in spikes if u == src], [p for p, u in spikes if u == dst],
                            END, TOTAL, SPEC, DT)
    return out


def check_run(run: dict, tol_replay: float, tol_affine: float) -> list[str]:
    seed, conds, tag = run["seed"], run["conditions"], f"seed {run['seed']}"
    units = run["roles"]["units"]
    problems = [f"{tag}: {p}" for p in W.check_stimulus_counts(
        PROTOCOL, seed, {c: conds[c]["sensory"] for c in W.CONDITIONS})]
    if any(p > END for c in W.CONDITIONS for p, _ in conds[c]["sensory"]):
        problems.append(f"{tag}: 経験の終わりより後に感覚の出来事がある")
    d = W.first_divergence(PROTOCOL, seed)
    if d != run["first_divergence_history"]:
        problems.append(f"{tag}: 札が最初に違う Pulse が刺激の列と合わない")
    o, s = conds["ordered"], conds["shuffled"]
    if o["birth"] != s["birth"]:
        problems.append(f"{tag}: 2 条件の出生時の状態が違う")
    if d is not None and ([a for a in o["activity"] if a[0] < d] != [a for a in s["activity"] if a[0] < d]
                          or o["before_divergence"] != s["before_divergence"]):
        problems.append(f"{tag}: 札が最初に違う Pulse より前の発火・状態が 2 条件で違う")
    for c in W.CONDITIONS:
        err = W.replay_error(PROTOCOL, [a for a in conds[c]["activity"] if a[0] <= END],
                             W.weights(conds[c]["connections_12000"]), END)
        if not err < tol_replay:
            problems.append(f"{tag} {c}: 12000 の再生の計算と記録の重みの差 {err}")
    # control は ordered の本体そのもの：12001 以降の発火が arms の control と一致
    if [a for a in o["activity"] if a[0] > END] != arm_spikes(run, "control"):
        problems.append(f"{tag}: control の発火が ordered の本体の記録と違う")
    if run["arms"]["connections_24000"]["control"] != o["connections_24000"]:
        problems.append(f"{tag}: control の 24000 の接続の状態が ordered の本体と違う")
    # 何も変えない複製が control と一致
    if (run["twin"]["activity"] != arm_spikes(run, "control")
            or run["twin"]["connections_24000"] != run["arms"]["connections_24000"]["control"]):
        problems.append(f"{tag}: clone_identity")
    # 介入：4 本 ＝ shuffled の 12000、それ以外は control と同じ
    fc, fi = run["fork"]["control"], run["fork"]["intervention"]
    ids = W.four_ids(units)
    target_ids = {ids[k] for k in W.TARGETS}
    if fc["units"] != fi["units"] or fc["units"] != o["units_12000"]:
        problems.append(f"{tag}: 介入の直後の Unit の状態が 2 腕で違う")
    if fc["connections"] != o["connections_12000"]:
        problems.append(f"{tag}: control の介入の直後の接続が ordered の 12000 と違う")
    for cid, v in fc["connections"].items():
        e = fi["connections"][cid]
        if e["pre_trace"] != v["pre_trace"] or e["post_trace"] != v["post_trace"]:
            problems.append(f"{tag}: {cid} の痕跡が介入で変わった")
        if cid not in target_ids and e["weight"] != v["weight"]:
            problems.append(f"{tag}: 対象外の {cid} の重みが介入で変わった")
    if any(fi["connections"][ids[k]]["weight"] != s["connections_12000"][ids[k]]["weight"] for k in W.TARGETS):
        problems.append(f"{tag}: 介入腕の 4 本が shuffled の 12000 の値と違う")
    # 12001 の発火は 2 腕で同じ（12001 の駆動は 12000 の冒頭に固定した重みで凍結済み）
    first = END + 1
    if ([a for a in arm_spikes(run, "control") if a[0] == first]
            != [a for a in arm_spikes(run, "intervention") if a[0] == first]):
        problems.append(f"{tag}: 12001 の発火が 2 腕で違う")
    # 各腕の 24000 の重み ＝ その腕の自分の発火の列からの再構成（本体の更新を呼ぶ道筋・affine の両方）
    for arm in W.ARMS:
        conns = run["arms"]["connections_24000"][arm]
        for cid, a in affine_all(run, arm).items():
            w0 = run["fork"][arm]["connections"][cid]["weight"]
            rec = conns[cid]["weight"]
            if not abs(a["w_end"] - rec) < tol_affine or not abs(a["S"] * w0 + a["B"] - rec) < tol_affine:
                problems.append(f"{tag} {arm}: {cid} の 24000 の重みが自分の発火の列からの再構成と合わない")
    # 最初の分岐の Pulse の発火の再構成
    dv = run["arms"]["divergence"]
    if dv is not None:
        if dv["before"]["t-2"] is None:
            problems.append(f"{tag}: 分岐が 12001 で、直前 2 Pulse の状態がない")
        else:
            t = dv["pulse"]
            for arm in W.ARMS:
                rec = W.reconstruct_firing(dv["before"]["t-1"][arm]["units"], dv["before"]["t-2"][arm]["connections"],
                                           dv["spikes"]["t-1"][arm], DT)
                predicted = sorted(u for u, r in rec.items() if r["fires"])
                actual = sorted(u for _, u in dv["spikes"]["t"][arm])
                if predicted != actual:
                    problems.append(f"{tag} {arm}: 分岐の Pulse {t} の発火の再構成が実際と合わない")
    return problems


# ---- 記録（判定に使わない。README §4） ------------------------------------------------------------

def record_run(run: dict) -> dict:
    u = run["roles"]["units"]
    ids = W.four_ids(u)
    W13 = load("world_0013_for_0020", Path("experiments/0013_self_amplified_asymmetry/world.py"))
    aff = {arm: affine_all(run, arm) for arm in W.ARMS}
    w0 = {arm: W.target_weights(run["fork"][arm]["connections"], u) for arm in W.ARMS}
    wT = {arm: W.target_weights(run["arms"]["connections_24000"][arm], u) for arm in W.ARMS}
    coef = {arm: {k: {f: aff[arm][ids[k]][f] for f in ("S", "log_S", "B", "pot", "dep", "n_factors_lt_1")}
                  for k in ("AB", "AC")} for arm in W.ARMS}
    dS = {k: coef["intervention"][k]["S"] - coef["control"][k]["S"] for k in ("AB", "AC")}
    dB = {k: coef["intervention"][k]["B"] - coef["control"][k]["B"] for k in ("AB", "AC")}

    def M(base: dict) -> dict:
        m = {k: dS[k] * base[k] + dB[k] for k in ("AB", "AC")}   # R(base, s_I) − R(base, s_C)（反実仮想）
        return m | {"W": m["AB"] - m["AC"]}

    M_I, M_C = M(w0["intervention"]), M(w0["control"])
    J = {k: M_I[k] - M_C[k] for k in ("AB", "AC", "W")}
    contrast = lambda w: w["AB"] - w["AC"]
    dW0 = contrast(w0["intervention"]) - contrast(w0["control"])
    dWT = contrast(wT["intervention"]) - contrast(wT["control"])
    spikes = {arm: W_spikes for arm, W_spikes in run["arms"]["spikes"].items()}
    counts = {arm: {r: sum(1 for _, x in spikes[arm] if x == u[r]) for r in ("A", "B", "C")} for arm in W.ARMS}
    birth = run["conditions"]["ordered"]["birth"]
    dv = run["arms"]["divergence"]
    div = None
    if dv is not None and dv["before"]["t-2"] is not None:
        div = {"pulse": dv["pulse"], "units": dv["units"],
               "roles": sorted(r for r in ("A", "B", "C") if u[r] in dv["units"]),
               "reconstruction": {arm: W.reconstruct_firing(dv["before"]["t-1"][arm]["units"],
                                                            dv["before"]["t-2"][arm]["connections"],
                                                            dv["spikes"]["t-1"][arm], DT) for arm in W.ARMS}}
    o, s = run["conditions"]["ordered"], run["conditions"]["shuffled"]
    nat = lambda c, k: W.w_contrast(W.weights(run["conditions"][c][k]), u)
    return {
        "rho_birth": {r: W13.rho(birth[u[r]]) for r in ("A", "B", "C")},
        "spike_counts_12001_24000": counts,
        "A_silent": {arm: counts[arm]["A"] == 0 for arm in W.ARMS},
        "min_margin": run["arms"]["min_margin"],
        "divergence": div,
        "trains_identical": dv is None,
        "delta_targets_12000": {k: w0["intervention"][k] - w0["control"][k] for k in W.TARGETS},
        "delta_targets_24000": {k: wT["intervention"][k] - wT["control"][k] for k in W.TARGETS},
        "dW0": dW0, "dWT": dWT,
        "sign_dW0_times_dWT": _sign(dW0) * dWT,
        "abs_dWT_minus_abs_dW0": abs(dWT) - abs(dW0),
        "affine": coef,
        "dS": dS, "dB": dB,
        "M_I": M_I, "M_C": M_C, "J": J,
        "M_sign_agree_W": _sign(M_I["W"]) == _sign(M_C["W"]),
        "underflow_audit": {arm: {k: coef[arm][k]["S"] == 0.0 and math.isfinite(coef[arm][k]["log_S"])
                                  for k in ("AB", "AC")} for arm in W.ARMS},
        "natural": {"D_12000": nat("ordered", "connections_12000") - nat("shuffled", "connections_12000"),
                    "D_24000": nat("ordered", "connections_24000") - nat("shuffled", "connections_24000"),
                    "A_spikes_shuffled_12001_24000": sum(1 for p, x in s["activity"] if x == u["A"] and p > END)},
    }


def summarize(per: dict) -> dict:
    """数え上げだけ（記述）。holds／fails へ換算しない。"""
    vals = list(per.values())
    n = len(vals)
    rho_lt1 = [v for v in vals if v["rho_birth"]["A"] < 1]
    return {
        "individuals": n,
        "A_silent_control": sum(v["A_silent"]["control"] for v in vals),
        "A_silent_intervention": sum(v["A_silent"]["intervention"] for v in vals),
        "silence_status_differs_between_arms": sum(v["A_silent"]["control"] != v["A_silent"]["intervention"] for v in vals),
        "rho_A_lt_1": len(rho_lt1),
        "rho_A_lt_1_and_A_silent": {arm: sum(v["A_silent"][arm] for v in rho_lt1) for arm in W.ARMS},
        "rho_A_ge_1_and_A_silent": {arm: sum(v["A_silent"][arm] for v in vals if v["rho_birth"]["A"] >= 1)
                                    for arm in W.ARMS},
        "trains_identical": sum(v["trains_identical"] for v in vals),
        "sign_dW0_times_dWT_gt_0": sum(v["sign_dW0_times_dWT"] > 0 for v in vals),
        "abs_dWT_gt_abs_dW0": sum(v["abs_dWT_minus_abs_dW0"] > 0 for v in vals),
        "M_sign_agree_W": sum(v["M_sign_agree_W"] for v in vals),
        "underflow_any": sum(any(x for a in v["underflow_audit"].values() for x in a.values()) for v in vals),
    }


def analyze(data: dict, check_only: bool = False) -> dict:
    s = PROTOCOL["synthetic_seeds"] if check_only else PROTOCOL["seeds"]
    allowed = set(range(s["first"], s["last"] + 1))
    runs = data["runs"]
    expected = sorted(r["seed"] for r in runs) if check_only else list(range(s["first"], s["last"] + 1))
    problems = completeness(data, expected)
    if check_only and not set(expected) <= allowed:
        problems.append("通しの確認に合成・確認専用の範囲の外の seed が使われた")
    tol_r, tol_a = PROTOCOL["checks"]["replay_history_12000"], PROTOCOL["checks"]["affine_matches_runtime"]
    for r in runs:
        problems += check_run(r, tol_r, tol_a)
    base = {"experiment": "0020", "kind": "exploration", "check_only": check_only,
            "git_commit": data["meta"]["git_commit"], "seeds": expected, "valid": not problems, "problems": problems}
    if check_only:
        return base | {"note": "道具の通しの確認（操作の確認だけ）。記録の量は計算・表示していない"}
    per = {str(r["seed"]): record_run(r) for r in runs}
    return base | {"note": "探索（判定なし）。全個体を記録し、holds／fails へ換算しない" +
                           ("" if not problems else "。invalid のデータの記録である"),
                   "summary": summarize(per), "per_seed": per}


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check_only = "--check" in sys.argv
    folder = Path(args[0]) if args else DEFAULT_DIR
    ALIGN.check(PROTOCOL)
    report = analyze(read(folder / "runs.json.gz"), check_only)
    (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"valid: {report['valid']}")
    for p in report["problems"][:50]:
        print(f"  - {p}")
    if check_only:
        print("【道具の通しの確認。記録の量は計算していない】")
    else:
        print("summary:", json.dumps(report["summary"], ensure_ascii=False))
    print(f"saved {folder / 'report.json'}")


if __name__ == "__main__":
    main()
