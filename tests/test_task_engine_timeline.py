import threading
import time
from datetime import datetime, timezone

from infrastructure.repositories import JsonlWriter
from services.case_service import CaseService
from services.task_engine import AnalysisTaskEngine
from services.timeline_service import TimelineService


def wait_for(engine, task_id, expected, timeout=3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if engine.get(task_id).status in expected:
            return engine.get(task_id)
        time.sleep(0.01)
    raise AssertionError(engine.get(task_id))


def test_task_lifecycle_and_persistence(tmp_path):
    cases = CaseService(tmp_path / "cases")
    case = cases.create_case("TASK-1", "Tasks", "Tester", "fixture", "tasks")
    engine = AnalysisTaskEngine(cases, max_workers=2)
    engine.register("success", lambda params, progress, cancel: (progress(50), {"value": 42})[1])
    task = engine.create("success", "Successful task", {"fixture": True})
    assert task.status == "pending"
    engine.start(task.task_id)
    completed = wait_for(engine, task.task_id, {"completed"})
    assert completed.progress == 100
    assert completed.result == {"value": 42}
    history = (tmp_path / "cases" / case.case_id / "task_history.jsonl").read_text()
    assert task.task_id in history
    engine.shutdown()


def test_task_failure_and_cancellation(tmp_path):
    cases = CaseService(tmp_path / "cases")
    cases.create_case("TASK-2", "Tasks", "Tester", "fixture", "errors")
    engine = AnalysisTaskEngine(cases, max_workers=2)
    engine.register("failure", lambda params, progress, cancel: (_ for _ in ()).throw(RuntimeError("known failure")))

    def cancellable(params, progress, cancel):
        for value in range(100):
            if cancel.is_set():
                return {"stopped": True}
            progress(value)
            time.sleep(0.005)
        return {"stopped": False}

    engine.register("cancel", cancellable)
    failed = engine.create("failure", "Failing task")
    cancelled = engine.create("cancel", "Cancellable task")
    engine.start(failed.task_id)
    engine.start(cancelled.task_id)
    wait_for(engine, failed.task_id, {"failed"})
    time.sleep(0.03)
    engine.cancel(cancelled.task_id)
    assert wait_for(engine, cancelled.task_id, {"cancelled"}).status == "cancelled"
    engine.shutdown()


def test_multiple_tasks_and_timeline_sources(tmp_path):
    cases = CaseService(tmp_path / "cases")
    case = cases.create_case("TIME-1", "Timeline", "Tester", "fixture", "timeline")
    cases.audit.append("local-user", "evidence.loaded", "evidence", "e1", {}, {"status": "success"})
    JsonlWriter(tmp_path / "cases" / case.case_id / "files.jsonl").append({
        "entry_id": "f1", "path": "/notes.txt", "inode": 3,
        "modified_at": "2024-01-02T00:00:00Z",
        "accessed_at": None, "changed_at": None, "created_at": None,
    })
    timeline = TimelineService(cases)
    events = timeline.events()
    assert any(item.source_kind == "software_audit" and item.event_type == "evidence" for item in events)
    assert any(item.source_kind == "filesystem" and item.event_type == "file_modified" for item in events)
    filtered = timeline.events(
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 1, 3, tzinfo=timezone.utc),
        event_types={"file_modified"},
    )
    assert len(filtered) == 1
    assert filtered[0].file_path == "/notes.txt"
