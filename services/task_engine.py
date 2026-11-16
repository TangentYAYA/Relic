import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict
from typing import Any, Callable

from domain.models import AnalysisTask
from infrastructure.audit import utc_now
from infrastructure.repositories import JsonlWriter
from services.case_service import CaseService


TaskHandler = Callable[[dict, Callable[[int], None], threading.Event], Any]


class AnalysisTaskEngine:
    def __init__(self, cases: CaseService, max_workers: int = 2):
        self.cases = cases
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="relic-analysis")
        self.handlers: dict[str, TaskHandler] = {}
        self.tasks: dict[str, AnalysisTask] = {}
        self.cancel_events: dict[str, threading.Event] = {}
        self.futures: dict[str, Future] = {}
        self.lock = threading.RLock()

    def register(self, task_type: str, handler: TaskHandler) -> None:
        if not task_type or task_type in self.handlers:
            raise ValueError(f"task handler already registered: {task_type}")
        self.handlers[task_type] = handler

    def create(self, task_type: str, task_name: str, parameters: dict | None = None) -> AnalysisTask:
        if task_type not in self.handlers:
            raise KeyError(f"unregistered task type: {task_type}")
        task = AnalysisTask(str(uuid.uuid4()), task_type, task_name, parameters or {})
        with self.lock:
            self.tasks[task.task_id] = task
            self._persist(task)
        return task

    def start(self, task_id: str) -> AnalysisTask:
        with self.lock:
            task = self._get(task_id)
            if task.status != "pending":
                raise ValueError(f"task is not pending: {task.status}")
            task.status = "running"
            task.start_time = utc_now()
            cancel_event = threading.Event()
            self.cancel_events[task_id] = cancel_event
            self._persist(task)
            future = self.executor.submit(self._run, task_id, cancel_event)
            self.futures[task_id] = future
            return task

    def cancel(self, task_id: str) -> AnalysisTask:
        with self.lock:
            task = self._get(task_id)
            if task.status not in {"pending", "running"}:
                return task
            self.cancel_events.setdefault(task_id, threading.Event()).set()
            if task.status == "pending":
                task.status = "cancelled"
                task.end_time = utc_now()
                self._persist(task)
            return task

    def get(self, task_id: str) -> AnalysisTask:
        with self.lock:
            return self._get(task_id)

    def history(self) -> list[AnalysisTask]:
        with self.lock:
            return sorted(self.tasks.values(), key=lambda item: item.start_time or "", reverse=True)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)

    def _run(self, task_id: str, cancel_event: threading.Event) -> None:
        task = self.get(task_id)
        try:
            def progress(value: int) -> None:
                with self.lock:
                    if task.status == "running":
                        task.progress = max(0, min(100, int(value)))
                        self._persist(task)

            result = self.handlers[task.task_type](task.parameters, progress, cancel_event)
            with self.lock:
                if cancel_event.is_set():
                    task.status = "cancelled"
                else:
                    task.status = "completed"
                    task.progress = 100
                    task.result = result if isinstance(result, dict) else {"value": result}
                task.end_time = utc_now()
                self._persist(task)
        except Exception as exc:
            with self.lock:
                task.status = "cancelled" if cancel_event.is_set() else "failed"
                task.error_message = str(exc)
                task.end_time = utc_now()
                self._persist(task)

    def _get(self, task_id: str) -> AnalysisTask:
        if task_id not in self.tasks:
            raise KeyError(f"unknown task: {task_id}")
        return self.tasks[task_id]

    def _persist(self, task: AnalysisTask) -> None:
        case = self.cases.active_case
        if case is None:
            return
        JsonlWriter(self.cases.case_path(case.case_id) / "task_history.jsonl").append(asdict(task))
