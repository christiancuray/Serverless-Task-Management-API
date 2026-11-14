"""Worker unit tests; these exercise the handler without AWS services."""

import importlib.util
import json
from pathlib import Path

import pytest


WORKER_PATH = Path(__file__).resolve().parents[2] / "src" / "task_events_worker.py"


@pytest.fixture
def worker():
    spec = importlib.util.spec_from_file_location("isolated_task_events_worker", WORKER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record(message_id, body):
    return {"messageId": message_id, "body": body}


def test_successful_task_created_event_is_acknowledged(worker, caplog):
    event = {
        "Records": [record("message-1", json.dumps({
            "eventType": "TASK_CREATED",
            "userId": "user-1",
            "taskId": "task-1",
        }))]
    }

    result = worker.handler(event, None)

    assert result == {"batchItemFailures": []}
    assert "Task created for user user-1 with task ID task-1" in caplog.text


def test_malformed_json_is_reported_as_batch_failure(worker):
    result = worker.handler({"Records": [record("bad-json", "{not-json")]}, None)

    assert result == {"batchItemFailures": [{"itemIdentifier": "bad-json"}]}


def test_unsupported_event_type_is_reported_as_batch_failure(worker):
    body = json.dumps({"eventType": "TASK_DELETED", "taskId": "task-1"})

    result = worker.handler({"Records": [record("wrong-type", body)]}, None)

    assert result == {"batchItemFailures": [{"itemIdentifier": "wrong-type"}]}


def test_mixed_batch_reports_only_the_failed_message(worker):
    good = json.dumps({"eventType": "TASK_CREATED", "userId": "user-1", "taskId": "task-1"})
    bad = json.dumps({"eventType": "TASK_UPDATED", "userId": "user-1", "taskId": "task-2"})

    result = worker.handler(
        {"Records": [record("good-message", good), record("bad-message", bad)]}, None
    )

    assert result == {"batchItemFailures": [{"itemIdentifier": "bad-message"}]}
