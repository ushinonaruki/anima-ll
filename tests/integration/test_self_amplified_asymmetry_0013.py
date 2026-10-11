"""実験 0013 の道具の契約テスト（README §5.1・§7）。

判定の seed（2001〜2020）は使わない。走らせるのは動作確認の範囲の seed（3001〜3006）を、短い長さでだけ。
"""

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "0013_self_amplified_asymmetry"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))
SEEDS = range(3001, 3007)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _load("world_0013_test", EXP / "world.py")


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


@pytest.fixture
def R():
    return _load("run_0013_test", EXP / "run.py")


@pytest.fixture
def A():
    return _load("analyze_0013_test", EXP / "analyze.py")


def test_protocol_and_tools_are_aligned() -> None:
    _load("alignment_0013_test", EXP / "alignment.py").check(PROTOCOL)


@pytest.mark.parametrize("seed", SEEDS)
def test_plastic_and_nonplastic_twins_share_the_birth_state(seed) -> None:
    p = W.build(PROTOCOL, "plastic", seed, W.ExperimentLog())
    n = W.build(PROTOCOL, "nonplastic", seed, W.ExperimentLog())
    assert W.birth_state(p) == W.birth_state(n)


def test_nonplastic_weights_do_not_change(R) -> None:
    n = W.build(PROTOCOL, "nonplastic", 3001, W.ExperimentLog())
    start = R.all_weights(n)
    W.advance_to(n, 3000)
    assert R.all_weights(n) == start and len(start) == 6


@pytest.mark.parametrize("seed", SEEDS)
def test_twins_fire_identically_until_the_first_weight_change(R, seed) -> None:
    lp, ln = W.ExperimentLog(), W.ExperimentLog()
    p, n = W.build(PROTOCOL, "plastic", seed, lp), W.build(PROTOCOL, "nonplastic", seed, ln)
    W.advance_to(p, 3000)
    W.advance_to(n, 3000)
    first = R.first_weight_change(lp.activity())
    assert first is not None
    assert [a for a in lp.activity() if a[0] <= first] == [a for a in ln.activity() if a[0] <= first]


def test_as_is_clone_matches_main_and_reset_clone_has_w0_weights_with_traces_kept() -> None:
    log = W.ExperimentLog()
    p = W.build(PROTOCOL, "plastic", 3002, log)
    w0 = next(iter(p.connections.export_state().values()))["weight"]
    W.advance_to(p, 2000)
    before = p.connections.export_state()
    as_is, log_as_is = W.clone(p, log)
    reset, _ = W.clone(p, log)
    W.reset_weights(reset, w0)
    after = reset.connections.export_state()
    assert all(v["weight"] == w0 for v in after.values())
    assert all(after[c]["pre_trace"] == before[c]["pre_trace"] and after[c]["post_trace"] == before[c]["post_trace"]
               for c in before)
    assert p.connections.export_state() == before          # 本体は触られていない
    W.advance_to(as_is, 3000)
    W.advance_to(p, 3000)
    assert [a for a in log.activity() if a[0] > 2000] == log_as_is.activity()
    assert as_is.connections.export_state() == p.connections.export_state()


def test_first_weight_change_on_synthetic_records(R) -> None:
    assert R.first_weight_change([[5, "s1"], [7, "s1"], [9, "s2"]]) == 9
    assert R.first_weight_change([[5, "s1"], [5, "s2"], [6, "s3"]]) == 6   # 同じ Pulse は痕跡に入っていない
    assert R.first_weight_change([[5, "s1"], [8, "s1"]]) is None


def test_follows_and_asymmetries() -> None:
    act = [[10, "s1"], [11, "s2"], [20, "s2"], [21, "s1"], [30, "s1"], [31, "s2"], [31, "s3"]]
    F = W.follows(act, (1, 100))
    assert F == {("s1", "s2"): 2, ("s2", "s1"): 1, ("s1", "s3"): 1}
    assert W.f_asym(F, "s1", "s2") == 1 and W.f_asym(F, "s3", "s1") == -1
    assert W.follows(act, (12, 100)) == {("s2", "s1"): 1, ("s1", "s2"): 1, ("s1", "s3"): 1}
    w = {"s1.main->s2": 0.007, "s2.main->s1": 0.004}
    assert W.a_asym(w, "s1", "s2") == pytest.approx(0.003)
    assert (W.sign(0.2), W.sign(0.0), W.sign(-1)) == (1, 0, -1)


def _synthetic_run(eligible, nonplastic_early, plastic_late=(), nonplastic_late=(), weights=None):
    weights = weights or {f"{a}.main->{b}": 0.005 for a in ("s1", "s2", "s3") for b in ("s1", "s2", "s3") if a != b}
    return {
        "eligible_pairs": eligible,
        "activity": {"nonplastic": list(nonplastic_early) + list(nonplastic_late), "plastic": list(plastic_late),
                     "as_is": [], "reset_to_w0": []},
        "weights_end": {"plastic": weights},
        "connections_at_intervention": {k: {"weight": v} for k, v in weights.items()},
    }


def test_statistics_use_plain_arithmetic_for_zero_terms_and_empty_sums(A) -> None:
    # 適格な組がない：すべての和は 0（空の和）→ C・H_A・M はどれも成り立たない
    s = A.statistics(_synthetic_run([], []))
    assert (s["c_birth"], s["h_a_plastic"], s["m_as_is"]) == (0, 0, 0)
    assert not (s["c"] or s["h_a"] or s["m"])
    # b ＝ 0 の組（前の窓で非対称なし）の項は 0
    early = [[1100, "s1"], [1101, "s2"], [1200, "s2"], [1201, "s1"]]
    w = {f"{a}.main->{b}": 0.005 for a in ("s1", "s2", "s3") for b in ("s1", "s2", "s3") if a != b}
    w["s1.main->s2"] = 0.008
    s = A.statistics(_synthetic_run([["s1", "s2"]], early, weights=w))
    assert s["b"] == {"s1-s2": 0} and s["c_birth"] == 0 and not s["c"]
    # b ＝ ＋1 で、接続も同じ向き → C_birth ＞ 0
    early = [[1100, "s1"], [1101, "s2"]]
    s = A.statistics(_synthetic_run([["s1", "s2"]], early, weights=w))
    assert s["b"] == {"s1-s2": 1} and s["c_birth"] == pytest.approx(0.003) and s["c"]
