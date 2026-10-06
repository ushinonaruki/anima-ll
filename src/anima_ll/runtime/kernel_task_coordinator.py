import asyncio
from collections.abc import Mapping

from anima_ll.domain.model.claim import KernelTaskDraft
from anima_ll.domain.model.identifiers import (
    PulseNumber,
    ResourceClass,
    SnapshotId,
    TaskId,
    UnitId,
)
from anima_ll.domain.model.kernel_task import KernelResult, KernelStatus, KernelTask
from anima_ll.domain.port.compute_kernel import ComputeKernel
from anima_ll.runtime.identifier_issuer import IdentifierIssuer


class KernelTaskCoordinator:
    """採択された依頼を Kernel に投げ、終わったものを回収する。

    Kernel の推論は複数 Pulse にまたがってよい。その間も Pulse は進む。
    """

    def __init__(
        self,
        kernels: Mapping[ResourceClass, ComputeKernel],
        capacities: Mapping[ResourceClass, int],
        issuer: IdentifierIssuer,
    ) -> None:
        self._kernels = dict(kernels)
        self._capacities = dict(capacities)
        self._issuer = issuer
        self._in_flight: dict[TaskId, tuple[KernelTask, asyncio.Task[KernelResult]]] = {}

    def busy_units(self) -> frozenset[UnitId]:
        return frozenset(task.unit_id for task, _ in self._in_flight.values())

    def free_capacity(self) -> dict[ResourceClass, int]:
        used: dict[ResourceClass, int] = {}
        for task, _ in self._in_flight.values():
            used[task.resource_class] = used.get(task.resource_class, 0) + 1
        return {rc: cap - used.get(rc, 0) for rc, cap in self._capacities.items()}

    def start(
        self,
        *,
        unit_id: UnitId,
        resource_class: ResourceClass,
        draft: KernelTaskDraft,
        snapshot_id: SnapshotId,
        pulse: PulseNumber,
    ) -> KernelTask:
        task = KernelTask(
            task_id=self._issuer.task_id(),
            unit_id=unit_id,
            resource_class=resource_class,
            snapshot_id=snapshot_id,
            input_delta_ids=draft.input_delta_ids,
            started_pulse=pulse,
            inputs=draft.inputs,
            io_template=draft.io_template,
        )
        kernel = self._kernels[resource_class]
        self._in_flight[task.task_id] = (task, asyncio.create_task(self._execute(kernel, task)))
        return task

    def collect_completed(self) -> tuple[tuple[KernelTask, KernelResult], ...]:
        done_ids = sorted(tid for tid, (_, job) in self._in_flight.items() if job.done())
        completed = []
        for task_id in done_ids:
            task, job = self._in_flight.pop(task_id)
            completed.append((task, job.result()))
        return tuple(completed)

    async def shutdown(self) -> None:
        for _, job in self._in_flight.values():
            job.cancel()
        await asyncio.gather(*(job for _, job in self._in_flight.values()), return_exceptions=True)
        self._in_flight.clear()

    @staticmethod
    async def _execute(kernel: ComputeKernel, task: KernelTask) -> KernelResult:
        try:
            return await kernel.execute(task)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # Kernel の故障は Unit への結果として返す
            return KernelResult(task_id=task.task_id, status=KernelStatus.ERROR, error=repr(exc))
