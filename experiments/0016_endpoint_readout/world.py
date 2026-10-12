"""実験 0016 の道具（事前登録 v0.2 に従う。脳の側ではなく、実験者の側）。値はすべて protocol.yaml から受け取る。

- 経験と無入力の区間：0015 v0.2 の順序ありと同じ（刺激の列・Receptor・再生の確認は 0015 の道具を使う）
- 試しと介入：0014 v0.3 と同じ（probe・equalize・check_probe は 0014 の道具を使う）。
  各試しは、本体の t0 − 1 の終わりから独立に作る（本体には入れない）
- 指標の材料：E(t0) ＝ |B_as_is − B_equalized| ＋ |C_as_is − C_equalized|（t0 ＋ read_at の発火）
"""

import importlib.util
from collections.abc import Mapping
from pathlib import Path

import yaml

from anima_ll.adapter.clock.fixed_step_clock import FixedStepClock
from anima_ll.adapter.config.yaml_config_source import (
    parse_birth_state,
    parse_environment,
    parse_neuroarchitecture,
)
from anima_ll.bootstrap import Application, build_application
from anima_ll.domain.model.identifiers import ComponentId, PulseNumber

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# protocol.yaml の式の文字列。ここに書いた式を実装している（alignment.py が protocol と同じか確かめる）
EXPERIENCE_END = "trials.first - 1 + trials.count * trials.every"
ENDPOINT = "2 * experience_end"
PROBES_FIRST = "endpoint + 1"
PROBE_COUNT = "adaptation_tau / pulse_interval_seconds"
TOTAL_PULSES = "endpoint + probes.count"
CLONE_END = "t0 + probe.read_at"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W14 = _load("world_0014_for_0016", ROOT / "experiments/0014_order_to_activity/world.py")
W15 = _load("world_0015_for_0016", ROOT / "experiments/0015_history_difference_persistence/world.py")
ExperimentLog = W14.ExperimentLog
clone = W14.clone
advance_to = W14.advance_to
probe = W14.probe                    # 0014 v0.3 の手順（t0 の終わりで 2 腕に分け、t0 ＋ read_at まで進める）
check_probe = W14.check_probe
w_probe = W14.w_probe
fired_at = W14.fired_at
w_max = W14.w_max
role_units = W14.role_units
role_receptors = W14.role_receptors
snapshot = W14.snapshot
unit_states = W14.unit_states
check_stimulus_counts = W15.check_stimulus_counts
replay_error = W15.replay_error
weights = W15.weights
w_contrast = W15.w_contrast
stimuli = W15.stimuli


def manifest_raw(protocol: dict) -> dict:
    return yaml.safe_load((ROOT / protocol["brain"]["manifest"]).read_text(encoding="utf-8"))


# ---- 時間の流れ（protocol の式から） ---------------------------------------------------------

def _expect(protocol_value, expected: str, name: str) -> None:
    if protocol_value != expected:
        raise ValueError(f"{name} の式が道具と違う")


def experience_end(protocol: dict) -> PulseNumber:
    tl = protocol["timeline"]
    _expect(tl["experience_end"], EXPERIENCE_END, "experience_end")
    t = tl["trials"]
    return t["first"] - 1 + t["count"] * t["every"]


def endpoint(protocol: dict) -> PulseNumber:
    _expect(protocol["timeline"]["endpoint"], ENDPOINT, "endpoint")
    return 2 * experience_end(protocol)


def probe_count(protocol: dict) -> int:
    tl = protocol["timeline"]
    _expect(tl["probes"]["count"], PROBE_COUNT, "probes.count")
    exact = manifest_raw(protocol)["defaults"]["dynamics"]["adaptation_tau"] / tl["pulse_interval_seconds"]
    n = round(exact)
    if abs(exact - n) > 1e-9:
        raise ValueError(f"adaptation_tau ÷ pulse_interval_seconds が整数でない（{exact}）")
    return n


def probe_times(protocol: dict) -> list[PulseNumber]:
    p = protocol["timeline"]["probes"]
    _expect(p["first"], PROBES_FIRST, "probes.first")
    first = endpoint(protocol) + 1
    return [first + k * p["every"] for k in range(probe_count(protocol))]


def total_pulses(protocol: dict) -> PulseNumber:
    _expect(protocol["timeline"]["total_pulses"], TOTAL_PULSES, "total_pulses")
    _expect(protocol["timeline"]["clone_end"], CLONE_END, "clone_end")
    return endpoint(protocol) + probe_count(protocol)


# ---- 個体の組み立て ------------------------------------------------------------------------------

def build(protocol: dict, seed: int, log: ExperimentLog) -> Application:
    env = parse_environment({
        "receptors": {r: {"kind": "scripted", "script": {}} for r in protocol["brain"]["receptors"]},
        "runtime": {"pulse_interval_seconds": protocol["timeline"]["pulse_interval_seconds"]},
    })
    return build_application(
        parse_neuroarchitecture(manifest_raw(protocol)),
        env,
        parse_birth_state({"individual_id": f"anima-0016-{seed}", "seed": seed}),
        clock=FixedStepClock(env.pulse_interval_seconds),
        event_log=log,
        receptor_overrides=W15.receptors_for(protocol, "ordered", seed),
        run_metadata={"experiment": "0016", "condition": "ordered",
                      "receptors": "ScheduledReceptor（experiments/0012_passive_world/world.py）"},
    )


# ---- 指標 ----------------------------------------------------------------------------------------

def readout(record: Mapping, units: Mapping[str, ComponentId], read_at: int) -> int:
    """E(t0) ＝ |B_as_is − B_equalized| ＋ |C_as_is − C_equalized|（B・C は t0 ＋ read_at に発火したら 1）。"""
    t = record["t0"] + read_at
    act = record["activity"]
    return sum(abs(fired_at(act["as_is"], units[r], t) - fired_at(act["equalized"], units[r], t)) for r in ("B", "C"))
