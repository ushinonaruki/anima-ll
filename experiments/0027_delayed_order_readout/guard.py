"""実験 0027 の一度限りの実行の保護（README §9、protocol の execution・execution.per_seed）。run.py と analyze.py が使う。

0023〜0026 の guard の契約（PR #104・#108・#112・#115：commit の確定、seed ごとの排他的な開始の記録、一度だけ書く終了の記録、原子的な保存、
失敗したときの扱い）をそのまま引き継ぐ。中身は 0025・0026 の guard.py と同じ作りで、このフォルダに自前で持つ
（ほかの実験の guard.py は読み込まない）。

seed ごとの記録（出力先の seeds/<seed>/ の下）：
- run_started.json（開始の記録）：seed に触れる前に O_CREAT | O_EXCL で作る（排他）。seed・measurement_commit・
  protocol_sha256・started_at を持つ。**開始の記録がある seed は、終了の記録の有無にかかわらず二度と始めない**
- raw.json.gz（生の記録）：一時ファイルに書いて fsync し、os.replace で置く
- run_finished.json（終了の記録）：seed・status（completed／failed）・finished_at・raw_file_sha256・raw_file_bytes を持つ。
  一時ファイルに書いて fsync し、os.link で置く（既にあれば失敗する。上書きしない）

seed の状態（seed_status）：
- absent（何もない）／started（開始の記録だけ：実行中か、中断した）／completed（終了の記録が completed で、raw の SHA-256・
  バイト数が終了の記録と一致）／failed（終了の記録が failed）／broken（それ以外：開始の記録のない終了の記録・raw、
  completed なのに raw がない・ハッシュが違う、読めない記録、置き忘れの一時ファイルなど）

同じ出力先で同時に動く実行は 1 つだけ（run.lock への fcntl.flock。プロセスが終われば OS が外す）。
このモジュールは experiment ID・出力先・protocol のパス・seed の範囲を持たない（それらは run.py・analyze.py が protocol から読む）。
保護は出力先のフォルダ単位（data/ は git の外）。別の作業場所での実行までは防げないので、使った seed を BLACKBOARD・PR に
記録する運用と併せて使う。
"""

import contextlib
import datetime
import fcntl
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
START, FINISH, RAW = "run_started.json", "run_finished.json", "raw.json.gz"
SEEDS_DIR, LOCK = "seeds", "run.lock"
STATUSES = ("absent", "started", "completed", "failed", "broken")
START_FIELDS = ("seed", "measurement_commit", "protocol_sha256", "started_at")
FINISH_FIELDS = ("seed", "status", "finished_at", "raw_file_sha256", "raw_file_bytes")


class GuardError(RuntimeError):
    """実行・解析してはいけない状態。"""


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
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def environment() -> dict:
    return {"python": sys.version.split()[0], "platform": platform.platform(), "pid": os.getpid()}


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


def atomic_write(path: Path, data: bytes) -> None:
    """一時ファイルに書いて fsync し、os.replace で置く（途中で止まっても半端なファイルが本名で残らない）。
    一時ファイルが既にあれば失敗する（前の中断の跡を黙って消さない）。"""
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def write_once(path: Path, data: bytes) -> None:
    """一時ファイルに書いて fsync し、os.link で本名に置く（本名が既にあれば FileExistsError。上書きしない）。"""
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.link(tmp, path)
    finally:
        os.unlink(tmp)
    _fsync_dir(path.parent)


@contextlib.contextmanager
def session_lock(out: Path) -> Iterator[None]:
    """同じ出力先で同時に動く実行・解析を 1 つにする（fcntl.flock。プロセスが終われば OS が外す）。"""
    out.mkdir(parents=True, exist_ok=True)
    fd = os.open(out / LOCK, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise GuardError(f"{out} では、ほかの実行・解析が動いている（同時に動かさない）") from e
        yield
    finally:
        os.close(fd)


def seed_dir(out: Path, seed: int) -> Path:
    return out / SEEDS_DIR / str(seed)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def read_seed(out: Path, seed: int) -> dict:
    """seed の開始・終了の記録と、raw の SHA-256・バイト数（ないものは None）、置き忘れの一時ファイル。"""
    d = seed_dir(out, seed)
    raw = d / RAW
    return {"start": _load(d / START), "finish": _load(d / FINISH),
            "raw_sha256": sha256_file(raw) if raw.exists() else None,
            "raw_bytes": raw.stat().st_size if raw.exists() else None,
            "tmp": sorted(p.name for p in d.iterdir() if p.name.endswith(".tmp")) if d.is_dir() else []}


def seed_status(out: Path, seed: int) -> tuple[str, list[str]]:
    """seed の状態（STATUSES のどれか）と、broken の理由。"""
    d = seed_dir(out, seed)
    if not d.exists():
        return "absent", []
    try:
        r = read_seed(out, seed)
    except (OSError, ValueError) as e:
        return "broken", [f"記録が読めない（{e!r}）"]
    start, fin, problems = r["start"], r["finish"], []
    if r["tmp"]:
        problems.append(f"一時ファイルが残っている（{r['tmp']}）")
    if start is None:
        if fin is None and r["raw_sha256"] is None and not r["tmp"] and not any(d.iterdir()):
            return "absent", []
        return "broken", problems + ["開始の記録がないのに、終了の記録・raw・一時ファイルがある"]
    if any(start.get(k) is None for k in START_FIELDS) or start.get("seed") != seed:
        problems.append("開始の記録の項目が足りないか、seed が違う")
    if fin is None:
        if r["raw_sha256"] is not None:
            problems.append("終了の記録がないのに raw がある")
        return ("broken", problems) if problems else ("started", [])
    if any(k not in fin for k in FINISH_FIELDS) or fin.get("seed") != seed:
        problems.append("終了の記録の項目が足りないか、seed が違う")
    if fin.get("status") == "failed":
        return ("broken", problems) if problems else ("failed", [])
    if fin.get("status") != "completed":
        problems.append(f"終了の記録の status が completed・failed のどちらでもない（{fin.get('status')!r}）")
    elif r["raw_sha256"] is None:
        problems.append("completed なのに raw がない")
    elif r["raw_sha256"] != fin.get("raw_file_sha256") or r["raw_bytes"] != fin.get("raw_file_bytes"):
        problems.append("raw の SHA-256・バイト数が終了の記録と一致しない")
    return ("broken", problems) if problems else ("completed", [])


def scan(out: Path) -> dict:
    """出力先のすべての seed の状態と、seeds/ の下の想定外のもの。{"seeds": {seed: (状態, 理由)}, "anomalies": [...]}"""
    root = out / SEEDS_DIR
    found, anomalies = {}, []
    if root.is_dir():
        for p in sorted(root.iterdir()):
            if p.is_dir() and p.name.isdigit() and str(int(p.name)) == p.name:
                found[int(p.name)] = seed_status(out, int(p.name))
            else:
                anomalies.append(f"seeds/ の下に想定外のもの（{p.name}）")
    return {"seeds": found, "anomalies": anomalies}


def begin_seed(out: Path, seed: int, record: dict) -> Path:
    """seed に触れる前に呼ぶ。seed の開始の記録を排他的に作る。開始の記録（や何か）が既にあれば GuardError。"""
    missing = [k for k in START_FIELDS if k not in record]
    if missing or record["seed"] != seed:
        raise GuardError(f"開始の記録の項目が足りないか、seed が違う（{missing}）")
    d = seed_dir(out, seed)
    path = d / START
    if path.exists():
        raise GuardError(f"seed {seed} は既に開始している（{path}。終了の記録の有無にかかわらず再実行しない）")
    others = sorted(p.name for p in d.iterdir()) if d.exists() else []
    if others:
        raise GuardError(f"seed {seed} のフォルダに、開始の記録がないまま {others} がある（再実行しない）")
    d.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)   # 排他（同時に 2 つが作ろうとしても 1 つだけ）
    except FileExistsError as e:
        raise GuardError(f"seed {seed} は既に開始している（{path}。終了の記録の有無にかかわらず再実行しない）") from e
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    _fsync_dir(d)
    return path


def finish_seed(out: Path, seed: int, record: dict) -> None:
    """seed の終了の記録を一度だけ書く（既にあれば GuardError。上書きしない）。開始の記録がなければ書かない。"""
    missing = [k for k in FINISH_FIELDS if k not in record]
    if missing or record["seed"] != seed or record["status"] not in ("completed", "failed"):
        raise GuardError(f"終了の記録の項目・status が想定と違う（{missing}）")
    d = seed_dir(out, seed)
    if not (d / START).exists():
        raise GuardError(f"seed {seed} の開始の記録がない（終了の記録を書かない）")
    try:
        write_once(d / FINISH, json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8"))
    except FileExistsError as e:
        raise GuardError(f"seed {seed} の終了の記録は既にある（上書きしない）") from e
