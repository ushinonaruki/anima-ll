"""0012 の事後の解析 A3：経験の後の、s_B と s_C の興奮しやすさの違い（順応）。範囲外の seed だけ。

- 経験の後の区間の始まり（Pulse 13799 の終わり）の、s_B・s_C の順応（adaptation）の値（本体の Unit の状態を読むだけ）
- 経験の後の試しの時刻で複製を作り、複製の上でだけ w(s_A→s_B) と w(s_A→s_C) を、その時点の 2 本の平均に揃えて試す。
  重みの差を消したときの「s_B が窓で発火した割合 − s_C が発火した割合」が、重み以外（興奮しやすさ）の寄与
- 同じ時刻で、重みを揃えない試し（ふつうの試し）との差が、重みの差の寄与
使い方: python experiments/0012_passive_world/post/excitability.py <出力フォルダ> [every]
"""

import importlib.util
import json
import statistics as st
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import yaml

EXP = Path("experiments/0012_passive_world")
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))
SEEDS = list(range(1001, 1021))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = load("world_0012", EXP / "world.py")
WINDOW = PROTOCOL["probe"]["response_window"]


def probe(app, log, roles, units, t0, equalize: bool):
    copied, clog = W.clone(app, log)
    if equalize:
        state = copied.connections.export_state()
        ab, ac = (W.connection_id(units["A"], units[t]) for t in ("B", "C"))
        mean = (state[ab]["weight"] + state[ac]["weight"]) / 2
        state[ab]["weight"] = state[ac]["weight"] = mean
        copied.connections.import_state(state)
    copied.receptors[roles["A"]].inject(t0)
    W.advance_to(copied, t0 - 1 + PROTOCOL["probe"]["clone_pulses"])
    fires = [[p - t0, u] for p, u in clog.activity()]
    return W.fired_in(fires, units["B"], WINDOW) - W.fired_in(fires, units["C"], WINDOW)


def seed_job(args) -> list[dict]:
    seed, every = args
    roles, units = W.role_receptors(PROTOCOL, seed), W.role_units(PROTOCOL, seed)
    first = PROTOCOL["timeline"]["post_probes"]["first"]
    times = list(range(first, PROTOCOL["timeline"]["total_pulses"] - PROTOCOL["probe"]["clone_pulses"] + 2, every))
    out = []
    for condition in PROTOCOL["stimulus"]["conditions"]:
        log = W.ExperimentLog()
        app = W.build(PROTOCOL, condition, seed, log)
        W.advance_to(app, first - 1)
        adapt = {role: app.units.get(units[role]).export_state()["adaptation"] for role in ("A", "B", "C")}
        half = len(times) // 2
        rows = []
        for t0 in times:
            W.advance_to(app, t0 - 1)
            rows.append((probe(app, log, roles, units, t0, False), probe(app, log, roles, units, t0, True)))
        out.append({"seed": seed, "condition": condition, "adaptation_at_post_start": adapt,
                    "R_actual": st.fmean(r[0] for r in rows), "R_equalized": st.fmean(r[1] for r in rows),
                    "R_actual_first_half": st.fmean(r[0] for r in rows[:half]),
                    "R_actual_second_half": st.fmean(r[0] for r in rows[half:]),
                    "R_equalized_first_half": st.fmean(r[1] for r in rows[:half]),
                    "R_equalized_second_half": st.fmean(r[1] for r in rows[half:])})
    return out


def main() -> None:
    folder = Path(sys.argv[1])
    every = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    with ProcessPoolExecutor() as pool:
        rows = [r for rs in pool.map(seed_job, [(s, every) for s in SEEDS]) for r in rs]
    summary = {}
    for c in PROTOCOL["stimulus"]["conditions"]:
        rs = [r for r in rows if r["condition"] == c]
        summary[c] = {
            "adaptation_B_minus_C_mean": st.fmean(r["adaptation_at_post_start"]["B"] - r["adaptation_at_post_start"]["C"] for r in rs),
            **{k: st.fmean(r[k] for r in rs) for k in ("R_actual", "R_equalized", "R_actual_first_half",
                                                        "R_actual_second_half", "R_equalized_first_half",
                                                        "R_equalized_second_half")},
            "weight_part_mean": st.fmean(r["R_actual"] - r["R_equalized"] for r in rs),
        }
    report = {"seeds": SEEDS, "every": every, "summary": summary, "rows": rows}
    (folder / f"excitability_every{every}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
