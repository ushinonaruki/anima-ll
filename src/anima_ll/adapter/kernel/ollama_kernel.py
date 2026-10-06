"""Ollama のローカル LLM を Compute Kernel として使う。

Kernel は依頼元の Unit について何も知らない。受け取るのは入力の断片と IO テンプレートの名前だけ。
テンプレートの本文には入出力の形式しか書かない（人格・口調・振る舞いは書かない）。

失敗（接続できない・時間切れ・応答の形式の誤り）は例外にせず、ERROR の結果として返す。
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

from anima_ll.domain.model.identifiers import JsonValue
from anima_ll.domain.model.kernel_task import KernelResult, KernelStatus, KernelTask

NO_FRAGMENTS = "（断片なし）"


class OllamaKernel:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        templates_dir: Path,
        options: Mapping[str, Any] | None = None,
        timeout_seconds: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._templates_dir = Path(templates_dir)
        self._options = dict(options or {})
        self._timeout = timeout_seconds
        self._transport = transport  # テストで差し替えるため
        self._templates: dict[str, str] = {}

    async def execute(self, task: KernelTask) -> KernelResult:
        try:
            system = self._template(task.io_template)
        except OSError as exc:
            return self._error(task, f"IO テンプレートを読めません: {exc}")

        messages = [{"role": "user", "content": render_fragments(task.inputs)}]
        if system:
            messages.insert(0, {"role": "system", "content": system})
        body = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": self._options,
        }
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post("/api/chat", json=body)
            if response.status_code != 200:
                return self._error(task, f"HTTP {response.status_code}: {response.text[:200]}")
            content = response.json()["message"]["content"]
        except httpx.HTTPError as exc:
            return self._error(task, f"{type(exc).__name__}: {exc}")
        except (ValueError, KeyError, TypeError) as exc:
            return self._error(task, f"応答の形式が想定と違います: {exc!r}")

        return KernelResult(task_id=task.task_id, status=KernelStatus.OK, output=str(content).strip())

    def _template(self, name: str | None) -> str:
        if not name:
            return ""
        if name not in self._templates:
            self._templates[name] = (self._templates_dir / f"{name}.txt").read_text(encoding="utf-8").strip()
        return self._templates[name]

    @staticmethod
    def _error(task: KernelTask, message: str) -> KernelResult:
        return KernelResult(task_id=task.task_id, status=KernelStatus.ERROR, error=message)


def render_fragments(inputs: JsonValue) -> str:
    """受容野の断片を、発信元つきの箇条書きにする。断片がないことも明示する。"""
    items = inputs.get("items", []) if isinstance(inputs, dict) else []
    if not items:
        return f"断片：\n{NO_FRAGMENTS}"
    lines = []
    for item in items:
        content = item.get("content")
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        lines.append(f"- [{item.get('from')}] {text}")
    return "断片：\n" + "\n".join(lines)
