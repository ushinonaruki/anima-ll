"""実験 0018 の判定（事前登録 v0.2 に従う。測定の前にコミットする）。判定の値の正本は protocol.yaml。

個体ごと（README §4）：
  E(t0) ＝ |B_ordered_std − B_shuffled_std| ＋ |C_ordered_std − C_shuffled_std|（t0 ＋ read_at の発火）
  S ＝ Σ_t0 E(t0)                                 主の判定 s：S ＞ 0（standardized-background sufficiency test）
適用対象はすべての個体（W_o ＝ W_s の試し・個体も専用に除外せず、S ＝ 0 の不成立）。
判定：成り立った個体数 ÷ 個体数 ≥ min_fraction。
操作の確認（README §6）は、保存した生の記録から再検証する。1 つでも成り立たなければ invalid とし、E・S は計算も表示もしない。

動作確認（smoke）のデータでは、完全性・操作の確認（README §7）だけを出す。
protocol の smoke.hide の量（E・S・D_fork・4 本それぞれの差・違った本数・recipient_mean_displacement・donor_mean_offset）は計算しない。

使い方:
  python experiments/0018_standardized_contrast/analyze.py [data/experiments/0018]
"""

import gzip
import importlib.util
import json
import sys
from pathlib import Path

import yaml

HERE = Path("experiments/0018_standardized_contrast")
PROTOCOL = yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
DEFAULT_DIR = Path("data/experiments/0018")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load("alignment_0018", HERE / "alignment.py")
W = load("world_0018", HERE / "world.py")
END = W.experience_end(PROTOCOL)
ENDPOINT = W.endpoint(PROTOCOL)
TOTAL = W.total_pulses(PROTOCOL)
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
        if [p["t0"] for p in r["probes"]] != times:
            problems.append(f"seed {r['seed']}: 試しの時刻が protocol と違う")
    return problems


def manipulation(runs: list[dict]) -> list[str]:
    tol = PROTOCOL["judgment"]["manipulation"]["replay_matches_recorded_weights"]
    w_max = W.w_max(PROTOCOL)
    problems = []
    for r in runs:
        seed, conds, tag = r["seed"], r["conditions"], f"seed {r['seed']}"
        problems += [f"{tag}: {p}" for p in W.check_stimulus_counts(
            PROTOCOL, seed, {c: conds[c]["sensory"] for c in W.CONDITIONS})]
        if any(p > END for c in W.CONDITIONS for p, _ in conds[c]["sensory"]):
            problems.append(f"{tag}: 経験の終わりより後に本体が感覚の出来事を受けた")
        d = W.first_divergence(PROTOCOL, seed)
        if d != r["first_divergence"]:
            problems.append(f"{tag}: 札が最初に違う Pulse が刺激の列と合わない")
        o, s = conds["ordered"], conds["shuffled"]
        if o["birth"] != s["birth"]:
            problems.append(f"{tag}: 2 条件の出生時の状態が違う")
        if d is not None and ([a for a in o["activity"] if a[0] < d] != [a for a in s["activity"] if a[0] < d]
                              or o["before_divergence"] != s["before_divergence"]):
            problems.append(f"{tag}: 札が最初に違う Pulse より前の発火・状態が 2 条件で違う")
        for c in W.CONDITIONS:
            x = conds[c]
            start = x["clone"]["from"]
            if ([a for a in x["activity"] if a[0] > start] != x["clone"]["activity"]
                    or x["clone"]["connections_end"] != x["connections_end"]):
                problems.append(f"{tag} {c}: clone_identity")
            err = W.replay_error(PROTOCOL, x["activity"], W.weights(x["connections_endpoint"]), ENDPOINT)
            if not err < tol:
                problems.append(f"{tag} {c}: 終端の再生の計算と記録の重みの差 {err}")
        for rec in r["probes"]:
            problems += [f"{tag}: {p}" for p in W.check_probe(PROTOCOL, seed, rec, w_max)]
    return problems


# ---- 判定の量（valid で、本番のときだけ計算する） ------------------------------------------------

def readouts(run: dict) -> list[int]:
    return [W.readout(rec, run["roles"]["units"], READ_AT) for rec in run["probes"]]


def statistics(run: dict) -> dict:
    s = sum(readouts(run))
    return {"S": s, "s": s > 0}


# ---- 記録（判定に使わない。README §5。本番で valid のときだけ） ----------------------------------

def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def records(runs: list[dict]) -> dict:
    W13 = load("world_0013_for_0018_records", Path("experiments/0013_self_amplified_asymmetry/world.py"))
    out = {}
    for r in runs:
        u = r["roles"]["units"]
        e = readouts(r)
        wm = W.w_max(PROTOCOL)
        diffs = [W.fork_differences(rec, u, wm) for rec in r["probes"]]
        direction = {"B": [0, 0], "C": [0, 0]}         # [B は D、C は −D の符号と一致, 一致しない]（E ＞ 0 の試しで変化した側だけ）
        for rec, x, df in zip(r["probes"], e, diffs):
            if x == 0:
                continue
            t = rec["t0"] + READ_AT
            for role, sgn in (("B", _sign(df["D"])), ("C", -_sign(df["D"]))):
                ch = (W.fired_at(rec["activity"]["ordered_std"], u[role], t)
                      - W.fired_at(rec["activity"]["shuffled_std"], u[role], t))
                if ch != 0:
                    direction[role][0 if ch == sgn else 1] += 1
        c = r["conditions"]
        w = {cd: {t: W.w_contrast(W.weights(c[cd][f"connections_{k}"]), u)
                  for t, k in ((END, "experience_end"), (ENDPOINT, "endpoint"))} for cd in W.CONDITIONS}
        d0 = w["ordered"][END] - w["shuffled"][END]
        dt = w["ordered"][ENDPOINT] - w["shuffled"][ENDPOINT]
        out[str(r["seed"])] = {
            "nonzero_probes": [rec["t0"] for rec, x in zip(r["probes"], e) if x > 0],
            "E": e,
            "E_equals_2": sum(1 for x in e if x == 2),
            "D_fork": [df["D"] for df in diffs],
            "recipient_mean_displacement": [df["recipient_mean_displacement"] for df in diffs],
            "donor_mean_offset": [df["donor_mean_offset"] for df in diffs],
            "target_weight_differences": [df["per_weight"] for df in diffs],
            "changed_weight_count": [df["changed"] for df in diffs],
            "direction_matches_D": direction,
            "W": {cd: {str(t): v for t, v in w[cd].items()} for cd in W.CONDITIONS},
            "D0": d0, "DT": dt, "sign_D0_times_DT": _sign(d0) * dt,
            "spontaneous_fires_input_free": {cd: {role: sum(1 for p, v in c[cd]["activity"]
                                                            if v == u[role] and END < p <= TOTAL)
                                                  for role in ("A", "B", "C")} for cd in W.CONDITIONS},
            "rho_A_birth": W13.rho(c["ordered"]["birth"][u["A"]]),
        }
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
    base = {"experiment": "0018", "smoke": smoke, "git_commit": data["meta"]["git_commit"], "seeds": expected,
            "valid": not problems, "problems": problems}
    if smoke:
        return base | {"note": "動作確認（README §7：実行の操作の確認だけ）。smoke.hide の量（E・S・D_fork・"
                               "4 本それぞれの差・違った本数・標準化の変位・提供側の offset）は計算していない",
                       "smoke_passed": not problems}
    if problems:
        return base | {"primary": "s", "judgment": None, "per_seed": None, "records": None,
                       "note": "invalid のため、E・S は計算していない"}
    per = {str(r["seed"]): statistics(r) for r in runs}
    ok = [sd for sd in per if per[sd]["s"]]
    need = PROTOCOL["judgment"]["min_fraction"]
    frac = len(ok) / len(per)
    judgment = {"s": {"status": "holds" if frac >= need else "fails", "satisfied": len(ok), "individuals": len(per),
                      "fraction": frac, "required_fraction": need, "seeds": sorted(int(x) for x in ok)}}
    return base | {"primary": "s", "judgment": judgment, "per_seed": per, "records": records(runs)}


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    ALIGN.check(PROTOCOL)
    report = analyze(read(folder / "runs.json.gz"))
    (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"valid: {report['valid']}")
    for p in report["problems"][:50]:
        print(f"  - {p}")
    if report["smoke"]:
        print("【動作確認（README §7）。smoke.hide の量は計算していない】")
        print(f"smoke_passed: {report['smoke_passed']}")
    elif report["judgment"] is None:
        print("invalid のため、E・S は計算していない")
    else:
        j = report["judgment"]["s"]
        print(f"s（主）: {j['status']} ({j['satisfied']}/{j['individuals']}、必要な比 {j['required_fraction']})")
    print(f"saved {folder / 'report.json'}")


if __name__ == "__main__":
    main()
