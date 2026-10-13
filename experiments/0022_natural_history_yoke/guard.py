"""実験 0022 の一度限りの実行の保護（README §7.2。0020・0021 の guard の契約を継承し、値は持たない）。run.py と analyze.py が使う。

- 計測の開始前に、HEAD が 40 桁の commit で、作業ツリーがその commit と一致する（変更・未追跡のファイルがない）ことを確かめ、
  その commit を確定する。環境変数や "unknown" で commit を代えることはしない
- 出力先に、排他的な開始の記録（run_started.json、O_CREAT | O_EXCL）を、seed に触れる前に作る。
  開始の記録・終了の記録・結果のどれかが既にあれば、完了・中断を問わず実行しない（黙った再実行・上書きをしない）
- 終わりに、HEAD と作業ツリーが開始時と同じ commit のままかを確かめ直す
- 結果は一時ファイルに書いて fsync し、os.replace で原子的に置く。終了の記録（run_finished.json）も同じ
- 失敗したときは、終了の記録に status ＝ failed と理由・触れた seed を残す（seed は使用済みとして扱う）

このモジュールは experiment ID・出力先・protocol のパス・seed の範囲を持たない（それらは run.py がこの実験の protocol から読む）。
保護は出力先のフォルダ単位（data/ は git の外）。別の作業場所での実行までは防げない。そのため、使った seed は
BLACKBOARD・PR に記録する運用と併せて使う（README §7.2）。
"""

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
START, FINISH, RUNS = "run_started.json", "run_finished.json", "runs.json.gz"


class GuardError(RuntimeError):
    """実行してはいけない状態（seed に触れる前・後の保護）。"""


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True, timeout=30).stdout


def verify_clean_commit(repo: Path, expected: str | None = None) -> str:
    """HEAD が 40 桁の commit で、作業ツリーが HEAD と一致することを確かめ、その commit を返す。
    expected を渡したときは HEAD がそれと同じであることも確かめる。環境変数は読まない。"""
    try:
        head = _git(repo, "rev-parse", "HEAD").strip()
        status = _git(repo, "status", "--porcelain", "--untracked-files=all")
    except (OSError, subprocess.SubprocessError) as e:
        raise GuardError(f"git で commit を確かめられない（{e!r}）") from e
    if not SHA_RE.match(head):
        raise GuardError(f"HEAD が 40 桁の commit ではない（{head!r}）")
    if status:
        raise GuardError("作業ツリーが commit と一致しない（変更・未追跡のファイルがある）：\n" + status)
    if expected is not None and head != expected:
        raise GuardError(f"HEAD（{head}）が指定した commit（{expected}）と違う")
    return head


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def environment() -> dict:
    return {"python": sys.version.split()[0], "platform": platform.platform(), "pid": os.getpid()}


def begin(out: Path, record: dict) -> Path:
    """seed に触れる前に呼ぶ。出力先に開始の記録を排他的に作る。既に何かあれば GuardError。"""
    out.mkdir(parents=True, exist_ok=True)
    for name in (RUNS, FINISH, RUNS + ".tmp", FINISH + ".tmp"):
        if (out / name).exists():
            raise GuardError(f"{out / name} が既にある（完了・中断を問わず、この出力先では再実行しない）")
    path = out / START
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as e:
        raise GuardError(f"{path} が既にある（この出力先では既に実行が始まっている。再実行しない）") from e
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(record | {"started_unix": time.time()}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    _fsync_dir(out)
    return path


def atomic_write(path: Path, data: bytes) -> None:
    """一時ファイルに書いて fsync し、os.replace で置く（途中で止まっても半端なファイルが本名で残らない）。"""
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def finish(out: Path, record: dict) -> None:
    atomic_write(out / FINISH, json.dumps(record | {"finished_unix": time.time()}, ensure_ascii=False,
                                          indent=2).encode("utf-8"))


def read_records(folder: Path) -> dict:
    """analyze.py 用：開始・終了の記録と、結果のファイルの sha256（ないものは None）。"""
    def load(name: str):
        p = folder / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    runs = folder / RUNS
    return {"start": load(START), "finish": load(FINISH),
            "runs_sha256": sha256_file(runs) if runs.exists() else None}


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
