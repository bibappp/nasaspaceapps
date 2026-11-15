"""Фоновые задачи загрузки медленных источников (NDVI MODIS, SMAP).

Состояние хранится в памяти процесса: после перезапуска задача стартует заново,
но уже скачанные запросы берутся из файлового кэша.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from dataclasses import field as dc_field

log = logging.getLogger(__name__)


@dataclass
class Job:
    id: str
    kind: str
    status: str = "running"  # running | done | failed
    done: int = 0
    total: int = 0
    error: str | None = None
    warnings: list[dict] = dc_field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "done": self.done,
            "total": self.total,
            "error": self.error,
            "warnings": self.warnings,
        }


_jobs: dict[str, Job] = {}
_tasks: set[asyncio.Task] = set()


def get_job(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def start_job(job_id: str, kind: str, runner: Callable[[Callable[[int, int], None]], Awaitable[object]]) -> Job:
    """Запускает задачу, если такой ещё нет (или прошлая попытка не удалась)."""
    existing = _jobs.get(job_id)
    if existing is not None and existing.status in ("running", "done"):
        return existing
    job = Job(id=job_id, kind=kind)
    _jobs[job_id] = job

    def progress(done: int, total: int) -> None:
        job.done, job.total = done, total

    async def run() -> None:
        try:
            result = await runner(progress)
            ok = getattr(result, "ok", True)
            job.warnings = [w.as_dict() for w in getattr(result, "warnings", [])]
            job.status = "done" if ok else "failed"
            if not ok:
                job.error = "source unavailable"
        except Exception as exc:
            log.exception("job %s failed", job_id)
            job.status, job.error = "failed", str(exc)[:200]

    task = asyncio.get_running_loop().create_task(run())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return job
