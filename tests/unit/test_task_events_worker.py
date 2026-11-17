"""Worker unit tests; these exercise the handler without AWS services."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

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


class InMemoryIdempotencyTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item, ConditionExpression):
        if Item["eventId"] in self.items:
            error = RuntimeError("Duplicate event")
            error.response = {"Error": {"Code": "ConditionalCheckFailedException"}}
            raise error
        self.items[Item["eventId"]] = Item.copy()

    def update_item(self, Key, **kwargs):
        self.items[Key["eventId"]]["status"] = "COMPLETED"

    def delete_item(self, Key):
        self.items.pop(Key["eventId"], None)


def task_created_event(**overrides):
    payload = {
        "eventType": "TASK_CREATED",
        "eventId": "event-1",
        "userId": "user-1",
        "taskId": "task-1",
        "occurredAt": "2026-11-14T12:00:00+00:00",
        "version": 1,
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_successful_task_created_event_is_acknowledged(worker, caplog):
    worker._idempotency_table = InMemoryIdempotencyTable()
    event = {"Records": [record("message-1", task_created_event())]}

    result = worker.handler(event, None)

    assert result == {"batchItemFailures": []}
    assert "event_id=event-1" in caplog.text
    assert "user_id=user-1" in caplog.text
    assert "task_id=task-1" in caplog.text


def test_malformed_json_is_reported_as_batch_failure(worker):
    result = worker.handler({"Records": [record("bad-json", "{not-json")]}, None)

    assert result == {"batchItemFailures": [{"itemIdentifier": "bad-json"}]}


def test_unsupported_event_type_is_reported_as_batch_failure(worker):
    body = task_created_event(eventType="TASK_DELETED")

    result = worker.handler({"Records": [record("wrong-type", body)]}, None)

    assert result == {"batchItemFailures": [{"itemIdentifier": "wrong-type"}]}


def test_mixed_batch_reports_only_the_failed_message(worker):
    worker._idempotency_table = InMemoryIdempotencyTable()
    good = task_created_event()
    bad = json.dumps({"eventType": "TASK_UPDATED", "userId": "user-1", "taskId": "task-2"})

    result = worker.handler(
        {"Records": [record("good-message", good), record("bad-message", bad)]}, None
    )

    assert result == {"batchItemFailures": [{"itemIdentifier": "bad-message"}]}


@pytest.mark.parametrize(
    "overrides",
    [
        {"eventId": ""},
        {"userId": ""},
        {"taskId": ""},
        {"occurredAt": ""},
        {"version": None},
    ],
)
def test_missing_required_event_field_is_rejected(worker, overrides):
    body = task_created_event(**overrides)

    result = worker.handler({"Records": [record("missing-field", body)]}, None)

    assert result == {"batchItemFailures": [{"itemIdentifier": "missing-field"}]}


def test_duplicate_delivery_is_safe_and_acknowledged(worker, caplog):
    body = task_created_event()
    worker._idempotency_table = InMemoryIdempotencyTable()

    result = worker.handler(
        {"Records": [record("delivery-1", body), record("delivery-2", body)]}, None
    )

    assert result == {"batchItemFailures": []}
    assert caplog.text.count("Processed task event event_id=event-1") == 1
    assert "Skipping duplicate task event event_id=event-1" in caplog.text


def test_retryable_processing_failure_returns_partial_batch_failure(worker, monkeypatch):
    class Table:
        def put_item(self, **kwargs):
            pass

        def update_item(self, **kwargs):
            raise RuntimeError("temporary downstream failure")

        def delete_item(self, **kwargs):
            pass

    worker._idempotency_table = Table()

    result = worker.handler(
        {"Records": [record("retry-message", task_created_event())]}, None
    )

    assert result == {"batchItemFailures": [{"itemIdentifier": "retry-message"}]}
