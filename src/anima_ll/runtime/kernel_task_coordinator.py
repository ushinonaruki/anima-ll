import asyncio
from collections.abc import Mapping

from anima_ll.domain.model.identifiers import PulseNumber, ResourceClass, TaskId, UnitId
from anima_ll.domain.model.kernel_task import KernelResult, KernelStatus, KernelTask
from anima_ll.domain.port.compute_kernel import ComputeKernel
from anima_ll.runtime.compute_intent import ComputeIntent
from anima_ll.runtime.identifier_issuer import IdentifierIssuer


class KernelTaskCoordinator:
    """列から取り出された意図を Kernel に投げ、終わったものを回収する。

    Kernel の推論は複数 Pulse にまたがってよい。その間も Pulse は進む。
    Kernel に渡すのは凍結した下書き（KernelTask）だけで、意図の一生の状態は渡さない。
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
        self._in_flight: dict[TaskId, tuple[ComputeIntent, KernelTask, asyncio.Task[KernelResult]]] = {}

    def busy_units(self) -> frozenset[UnitId]:
        return frozenset(task.unit_id for _, task, _ in self._in_flight.values())

    def free_capacity(self) -> dict[ResourceClass, int]:
        used: dict[ResourceClass, int] = {}
        for _, task, _ in self._in_flight.values():
            used[task.resource_class] = used.get(task.resource_class, 0) + 1
        return {rc: cap - used.get(rc, 0) for rc, cap in self._capacities.items()}

    def in_flight(self) -> tuple[ComputeIntent, ...]:
        return tuple(intent for intent, _, _ in self._in_flight.values())

    def start(self, intent: ComputeIntent, pulse: PulseNumber) -> KernelTask:
        draft = intent.draft
        task = KernelTask(
            task_id=self._issuer.task_id(),
            unit_id=intent.unit_id,
            resource_class=intent.resource_class,
            snapshot_id=intent.origin_snapshot_id,
            input_delta_ids=draft.input_delta_ids,
            started_pulse=pulse,
            inputs=draft.inputs,
            io_template=draft.io_template,
        )
        kernel = self._kernels[intent.resource_class]
        job = asyncio.create_task(self._execute(kernel, task))
        self._in_flight[task.task_id] = (intent, task, job)
        return task

    def collect_completed(self) -> tuple[tuple[ComputeIntent, KernelTask, KernelResult], ...]:
        done = sorted(
            (tid for tid, (_, _, job) in self._in_flight.items() if job.done()),
            key=lambda tid: self._in_flight[tid][0].intent_seq,
        )
        completed = []
        for task_id in done:
            intent, task, job = self._in_flight.pop(task_id)
            completed.append((intent, task, job.result()))
        return tuple(completed)

    async def shutdown(self) -> None:
        jobs = [job for _, _, job in self._in_flight.values()]
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        self._in_flight.clear()

    @staticmethod
    async def _execute(kernel: ComputeKernel, task: KernelTask) -> KernelResult:
        try:
            return await kernel.execute(task)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # Kernel の故障は Unit への結果として返す
            return KernelResult(task_id=task.task_id, status=KernelStatus.ERROR, error=repr(exc))
