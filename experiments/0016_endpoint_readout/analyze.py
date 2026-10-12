"""実験 0016 の判定（事前登録 v0.2 に従う。測定の前にコミットする）。判定の値の正本は protocol.yaml。

個体ごと（README §4）：
  E(t0) ＝ |B_as_is − B_equalized| ＋ |C_as_is − C_equalized|（t0 ＋ read_at の発火）
  S ＝ Σ_t0 E(t0)                                 主の判定 s：S ＞ 0（nonzero causal-readout test）
適用対象はすべての個体（W_probe が全試しで 0 の個体も N/A にせず、S ＝ 0 の不成立）。
判定：成り立った個体数 ÷ 個体数 ≥ min_fraction。
操作の確認（README §6）は、保存した生の記録から再検証する。1 つでも成り立たなければ invalid とし、E・S は計算も表示もしない。

動作確認（smoke）のデータでは、完全性・操作の確認（README §7）だけを出す。各試しの E も個体ごとの S も計算しない。

使い方:
  python experiments/0016_endpoint_readout/analyze.py [data/experiments/0016]
"""

import gzip
import importlib.util
import json
import sys
from pathlib import Path

import yaml

HERE = Path("experiments/0016_endpoint_readout")
PROTOCOL = yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
DEFAULT_DIR = Path("data/experiments/0016")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load("alignment_0016", HERE / "alignment.py")
W = load("world_0016", HERE / "world.py")
END = W.experience_end(PROTOCOL)
ENDPOINT = W.endpoint(PROTOCOL)
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
        seed, tag = r["seed"], f"seed {r['seed']}"
        problems += [f"{tag}: {p}" for p in W.check_stimulus_counts(PROTOCOL, seed, {"ordered": r["sensory"]})]
        if any(p > END for p, _ in r["sensory"]):
            problems.append(f"{tag}: 経験の終わりより後に本体が感覚の出来事を受けた")
        start = r["clone"]["from"]
        if ([a for a in r["activity"] if a[0] > start] != r["clone"]["activity"]
                or r["clone"]["connections_end"] != r["connections_end"]):
            problems.append(f"{tag}: clone_identity")
        err = W.replay_error(PROTOCOL, r["activity"], W.weights(r["connections_endpoint"]), ENDPOINT)
        if not err < tol:
            problems.append(f"{tag}: 終端の再生の計算と記録の重みの差 {err}")
        for rec in r["probes"]:
            problems += [f"{tag}: {p}" for p in W.check_probe(PROTOCOL, seed, rec, w_max)]
    return problems


# ---- 判定の量（valid で、本番のときだけ計算する） ------------------------------------------------

def readouts(run: dict) -> list[int]:
    return [W.readout(rec, run["roles"]["units"], READ_AT) for rec in run["probes"]]


def statistics(run: dict) -> dict:
    e = readouts(run)
    s = sum(e)
    return {"S": s, "s": s > 0}


# ---- 記録（判定に使わない。README §5） ------------------------------------------------------------

def records(runs: list[dict]) -> dict:
    W13 = load("world_0013_for_0016_records", Path("experiments/0013_self_amplified_asymmetry/world.py"))
    out = {}
    for r in runs:
        u = r["roles"]["units"]
        e = readouts(r)
        out[str(r["seed"])] = {
            "nonzero_probes": [rec["t0"] for rec, x in zip(r["probes"], e) if x > 0],
            "E": e,
            "W_probe": [W.w_probe(rec, u) for rec in r["probes"]],
            "W_experience_end": W.w_contrast(W.weights(r["connections_experience_end"]), u),
            "W_endpoint": W.w_contrast(W.weights(r["connections_endpoint"]), u),
            "a_fired_fraction": sum(W.fired_at(rec["activity"]["as_is"], u["A"], rec["t0"] + 1)
                                    for rec in r["probes"]) / len(r["probes"]),
            "a_spontaneous_fires_input_free": sum(1 for p, v in r["activity"] if v == u["A"] and END < p <= ENDPOINT),
            "rho_A_birth": W13.rho(r["birth"][u["A"]]),
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
    base = {"experiment": "0016", "smoke": smoke, "git_commit": data["meta"]["git_commit"], "seeds": expected,
            "valid": not problems, "problems": problems}
    if smoke:
        return base | {"note": "動作確認（README §7：実行の操作の確認だけ）。各試しの E も個体ごとの S も計算していない",
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
        print("【動作確認（README §7）。E・S は計算していない】")
        print(f"smoke_passed: {report['smoke_passed']}")
    elif report["judgment"] is None:
        print("invalid のため、E・S は計算していない")
    else:
        j = report["judgment"]["s"]
        print(f"s（主）: {j['status']} ({j['satisfied']}/{j['individuals']}、必要な比 {j['required_fraction']})")
    print(f"saved {folder / 'report.json'}")


if __name__ == "__main__":
    main()
