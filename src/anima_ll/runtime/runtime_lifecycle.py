import asyncio

from anima_ll.domain.model.individual import IndividualSnapshot
from anima_ll.domain.model.pulse import PulseContext
from anima_ll.domain.port.clock import Clock
from anima_ll.domain.port.snapshot_store import SnapshotStore
from anima_ll.runtime.kernel_task_coordinator import KernelTaskCoordinator
from anima_ll.runtime.pulse_runtime import PulseRuntime
from anima_ll.runtime.unit_registry import UnitRegistry

_KERNEL_YIELDS = 8
"""Pulse の冒頭で非同期の計算に処理を譲る回数（時計が進んだあとに完了を確定させるため）。"""


class RuntimeLifecycle:
    """起動・停止と、Pulse の歩調を担う。Pulse は入力がなくても止まらない。"""

    def __init__(
        self,
        *,
        individual_id: str,
        clock: Clock,
        pulse_runtime: PulseRuntime,
        coordinator: KernelTaskCoordinator,
        units: UnitRegistry,
        snapshot_store: SnapshotStore | None = None,
    ) -> None:
        self._individual_id = individual_id
        self._clock = clock
        self._pulse_runtime = pulse_runtime
        self._coordinator = coordinator
        self._units = units
        self._snapshot_store = snapshot_store
        self._stop_requested = False
        self._pulse = 0

    @property
    def pulse(self) -> int:
        return self._pulse

    def request_stop(self) -> None:
        self._stop_requested = True

    async def run(self, max_pulses: int | None = None) -> None:
        last = self._clock.now()
        try:
            while not self._stop_requested and (max_pulses is None or self._pulse < max_pulses):
                await self._clock.next_pulse()
                for _ in range(_KERNEL_YIELDS):
                    await asyncio.sleep(0)
                now = self._clock.now()
                self._pulse += 1
                await self._pulse_runtime.run_pulse(
                    PulseContext(pulse=self._pulse, now=now, delta_time=now - last)
                )
                last = now
        finally:
            await self._coordinator.shutdown()
            self.save_snapshot()

    def save_snapshot(self) -> IndividualSnapshot:
        snapshot = IndividualSnapshot(
            individual_id=self._individual_id,
            pulse=self._pulse,
            units={unit.unit_id: unit.export_state() for unit in self._units.all()},
        )
        if self._snapshot_store is not None:
            self._snapshot_store.save(snapshot)
        return snapshot
