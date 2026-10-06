"""Composition Root。全部品を生成して組み立てる、唯一の場所。

Manifest の文字列キー（kind）と実装クラスの対応表もここにある。
"""

import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from anima_ll.adapter.clock.fixed_step_clock import FixedStepClock
from anima_ll.adapter.clock.system_clock import SystemClock
from anima_ll.adapter.effector.console_effector import ConsoleEffector
from anima_ll.adapter.effector.recording_effector import RecordingEffector
from anima_ll.adapter.kernel.fake_delayed_kernel import FakeDelayedKernel
from anima_ll.adapter.receptor.scripted_receptor import ScriptedReceptor
from anima_ll.domain.model.manifest import (
    ComponentSpec,
    NeuroarchitectureManifest,
    ResourceSpec,
    UnitSpec,
)
from anima_ll.domain.port.clock import Clock
from anima_ll.domain.port.cognitive_unit import CognitiveUnit
from anima_ll.domain.port.compute_kernel import ComputeKernel
from anima_ll.domain.port.effector import Effector
from anima_ll.domain.port.event_log import EventLog
from anima_ll.domain.port.receptor import Receptor
from anima_ll.domain.port.snapshot_store import SnapshotStore
from anima_ll.runtime.brain_state_integrator import BrainStateIntegrator
from anima_ll.runtime.delta_canonicalizer import DeltaCanonicalizer
from anima_ll.runtime.effector_dispatcher import EffectorDispatcher
from anima_ll.runtime.external_event_intake import ExternalEventIntake
from anima_ll.runtime.identifier_issuer import IdentifierIssuer
from anima_ll.runtime.kernel_task_coordinator import KernelTaskCoordinator
from anima_ll.runtime.projection_router import ProjectionRouter
from anima_ll.runtime.pulse_runtime import PulseRuntime
from anima_ll.runtime.receptive_view_builder import ReceptiveViewBuilder
from anima_ll.runtime.resource_scheduler import ResourceScheduler
from anima_ll.runtime.runtime_lifecycle import RuntimeLifecycle
from anima_ll.runtime.unit_registry import UnitRegistry
from anima_ll.unit.dynamics.activity_dynamics import ActivityState
from anima_ll.unit.dynamics.simple_activity_dynamics import SimpleActivityDynamics
from anima_ll.unit.generic_cognitive_unit import GenericCognitiveUnit
from anima_ll.unit.output.kernel_request_output import KernelRequestOutput
from anima_ll.unit.output.relay_output import RelayOutput
from anima_ll.unit.output.unit_output import UnitOutput


# ---- Manifest の kind → 実装 ----------------------------------------------

def _kernel_fake_delayed(spec: ResourceSpec, clock: Clock) -> ComputeKernel:
    return FakeDelayedKernel(clock=clock, delay_seconds=float(spec.params.get("delay_seconds", 3.0)))


def _receptor_scripted(spec: ComponentSpec) -> Receptor:
    return ScriptedReceptor(spec.component_id, spec.params.get("script") or {})


def _effector_console(spec: ComponentSpec) -> Effector:
    prefix = str(spec.params.get("prefix", "AnIma-ll> "))
    return ConsoleEffector(spec.component_id, write=lambda text: print(prefix + text, flush=True))


def _effector_recording(spec: ComponentSpec) -> Effector:
    return RecordingEffector(spec.component_id)


KERNELS: dict[str, Callable[[ResourceSpec, Clock], ComputeKernel]] = {
    "fake_delayed": _kernel_fake_delayed,
}
RECEPTORS: dict[str, Callable[[ComponentSpec], Receptor]] = {
    "scripted": _receptor_scripted,
}
EFFECTORS: dict[str, Callable[[ComponentSpec], Effector]] = {
    "console": _effector_console,
    "recording": _effector_recording,
}


# ---- Unit の組み立て --------------------------------------------------------

def _build_unit(spec: UnitSpec, rng: random.Random) -> GenericCognitiveUnit:
    """部品を組み合わせて Unit を作る。初期値に seed 付きの小さなばらつきを入れる。

    ばらつきは「生命感の演出」ではなく、全 Unit が同じ値で動き続けないようにするための
    出生時の初期条件（Birth State 側の値）。
    """
    d = spec.dynamics
    if d.kind != "simple_activity":
        raise ValueError(f"未知の dynamics: {d.kind}")
    jitter = float(d.params.get("jitter", 0.0))

    def vary(value: float) -> float:
        return value * (1.0 + rng.uniform(-jitter, jitter))

    threshold = vary(float(d.params.get("threshold", 0.5)))
    dynamics = SimpleActivityDynamics(
        decay_per_second=float(d.params.get("decay", 0.85)),
        threshold=threshold,
        refractory_pulses=int(d.params.get("refractory_pulses", 3)),
        intrinsic_drive_per_second=vary(float(d.params.get("intrinsic_drive", 0.0))),
    )
    initial = ActivityState(activity=rng.uniform(0.0, threshold * 0.5))

    o = spec.output
    output: UnitOutput
    if o.kind == "relay":
        output = RelayOutput()
    elif o.kind == "kernel_request":
        output = KernelRequestOutput(
            resource_class=str(o.params["resource"]),
            io_template=o.params.get("io_template"),
            max_inputs=int(o.params.get("max_inputs", 8)),
        )
    else:
        raise ValueError(f"未知の output: {o.kind}")
    return GenericCognitiveUnit(spec.unit_id, dynamics, output, initial)


# ---- 全体の組み立て ---------------------------------------------------------

@dataclass
class Application:
    lifecycle: RuntimeLifecycle
    pulse_runtime: PulseRuntime
    units: UnitRegistry
    receptors: dict[str, Receptor] = field(default_factory=dict)
    effectors: dict[str, Effector] = field(default_factory=dict)


def build_application(
    manifest: NeuroarchitectureManifest,
    *,
    clock: Clock,
    event_log: EventLog,
    snapshot_store: SnapshotStore | None = None,
    individual_id: str = "anima",
    receptor_overrides: Mapping[str, Receptor] | None = None,
    effector_overrides: Mapping[str, Effector] | None = None,
    kernel_overrides: Mapping[str, ComputeKernel] | None = None,
    unit_overrides: Mapping[str, CognitiveUnit] | None = None,
) -> Application:
    rng = random.Random(manifest.seed)
    issuer = IdentifierIssuer()

    receptors = {
        spec.component_id: (receptor_overrides or {}).get(spec.component_id)
        or RECEPTORS[spec.kind](spec)
        for spec in manifest.receptors
    }
    effectors = {
        spec.component_id: (effector_overrides or {}).get(spec.component_id)
        or EFFECTORS[spec.kind](spec)
        for spec in manifest.effectors
    }
    kernels = {
        spec.resource_class: (kernel_overrides or {}).get(spec.resource_class)
        or KERNELS[spec.kernel](spec, clock)
        for spec in manifest.resources
    }
    built = [_build_unit(spec, rng) for spec in manifest.units]  # seed の消費順を固定するため全部作る
    units = UnitRegistry((unit_overrides or {}).get(u.unit_id) or u for u in built)
    coordinator = KernelTaskCoordinator(kernels, manifest.capacities(), issuer)

    pulse_runtime = PulseRuntime(
        units=units,
        claim_permissions={u.unit_id: u.allowed_resource_classes for u in manifest.units},
        intake=ExternalEventIntake(list(receptors.values())),
        view_builder=ReceptiveViewBuilder(),
        router=ProjectionRouter(manifest),
        canonicalizer=DeltaCanonicalizer(issuer, manifest.delta_ttl_pulses),
        integrator=BrainStateIntegrator(),
        scheduler=ResourceScheduler(),
        coordinator=coordinator,
        dispatcher=EffectorDispatcher(list(effectors.values())),
        issuer=issuer,
        event_log=event_log,
    )
    lifecycle = RuntimeLifecycle(
        individual_id=individual_id,
        clock=clock,
        pulse_runtime=pulse_runtime,
        coordinator=coordinator,
        units=units,
        snapshot_store=snapshot_store,
    )
    return Application(lifecycle, pulse_runtime, units, receptors, effectors)


def make_clock(mode: str, interval_seconds: float) -> Clock:
    if mode == "realtime":
        return SystemClock(interval_seconds)
    if mode == "fast":
        return FixedStepClock(step_seconds=interval_seconds)
    raise ValueError(f"未知の clock mode: {mode}")
