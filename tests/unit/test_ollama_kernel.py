"""OllamaKernel：HTTP は httpx.MockTransport で差し替えて検査する（実際の Ollama は使わない）。"""

import asyncio
import json
from pathlib import Path

import httpx

from anima_ll.adapter.kernel.ollama_kernel import NO_FRAGMENTS, OllamaKernel, render_fragments
from anima_ll.domain.model.kernel_task import KernelStatus, KernelTask


def task(items: list[dict], template: str | None = "associate") -> KernelTask:
    return KernelTask(
        task_id="t-1", unit_id="u1", resource_class="llm_pool", snapshot_id="s-1",
        input_delta_ids=tuple(f"d-{i}" for i in range(len(items))), started_pulse=1,
        inputs={"items": items}, io_template=template,
    )


def kernel(tmp_path: Path, handler) -> OllamaKernel:
    (tmp_path / "associate.txt").write_text("形式の説明", encoding="utf-8")
    return OllamaKernel(
        base_url="http://ollama:11434", model="anima-llm", templates_dir=tmp_path,
        options={"seed": 0, "temperature": 0.3}, transport=httpx.MockTransport(handler),
    )


def test_sends_template_fragments_and_options(tmp_path: Path) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "  おかえり \n"}})

    result = asyncio.run(kernel(tmp_path, handler).execute(task([{"from": "receptor.console", "content": "ただいま"}])))
    assert result.status == KernelStatus.OK and result.output == "おかえり"
    body = seen["body"]
    assert seen["path"] == "/api/chat"
    assert body["model"] == "anima-llm" and body["stream"] is False
    assert body["options"] == {"seed": 0, "temperature": 0.3}
    assert body["messages"][0] == {"role": "system", "content": "形式の説明"}
    assert "[receptor.console] ただいま" in body["messages"][1]["content"]


def test_empty_fragments_are_stated_explicitly() -> None:
    assert NO_FRAGMENTS in render_fragments({"items": []})
    assert NO_FRAGMENTS in render_fragments(None)


def test_http_error_becomes_error_result(tmp_path: Path) -> None:
    result = asyncio.run(
        kernel(tmp_path, lambda r: httpx.Response(404, text="model not found")).execute(task([]))
    )
    assert result.status == KernelStatus.ERROR and "404" in result.error


def test_connection_failure_becomes_error_result(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    result = asyncio.run(kernel(tmp_path, handler).execute(task([])))
    assert result.status == KernelStatus.ERROR and "ConnectError" in result.error


def test_malformed_response_becomes_error_result(tmp_path: Path) -> None:
    result = asyncio.run(kernel(tmp_path, lambda r: httpx.Response(200, json={"x": 1})).execute(task([])))
    assert result.status == KernelStatus.ERROR


def test_missing_template_becomes_error_result(tmp_path: Path) -> None:
    result = asyncio.run(
        kernel(tmp_path, lambda r: httpx.Response(200, json={})).execute(task([], template="nope"))
    )
    assert result.status == KernelStatus.ERROR and "テンプレート" in result.error
