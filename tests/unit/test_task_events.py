"""Task event publisher unit tests with SQS and DynamoDB mocked."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock
from datetime import datetime, timezone

import boto3
import pytest


HANDLER_PATH = Path(__file__).resolve().parents[2] / "src" / "tasks_handler.py"
QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/123456789012/unit-test"


@pytest.fixture
def publisher(monkeypatch):
    monkeypatch.setenv("TASKS_TABLE_NAME", "UnitTestTasks")
    monkeypatch.setenv("TASK_EVENTS_QUEUE_URL", QUEUE_URL)
    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)

    table = MagicMock()
    dynamodb = MagicMock()
    dynamodb.Table.return_value = table
    sqs = MagicMock()
    monkeypatch.setattr(boto3, "resource", lambda *args, **kwargs: dynamodb)
    monkeypatch.setattr(boto3, "client", lambda service, *args, **kwargs: sqs)

    spec = importlib.util.spec_from_file_location("isolated_publisher_tasks_handler", HANDLER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, table, sqs


def test_create_publishes_expected_task_created_message(publisher):
    module, table, sqs = publisher
    operation_order = []
    table.put_item.side_effect = lambda **kwargs: operation_order.append("persist")
    sqs.send_message.side_effect = lambda **kwargs: operation_order.append("publish")
    event = {
        "httpMethod": "POST",
        "requestContext": {"authorizer": {"claims": {"sub": "user-a"}}},
        "body": json.dumps({"title": "Write tests"}),
    }

    result = module.handler(event, None)
    task = json.loads(result["body"])

    assert result["statusCode"] == 201
    table.put_item.assert_called_once_with(Item=task)
    sqs.send_message.assert_called_once()
    sent = sqs.send_message.call_args.kwargs
    assert sent["QueueUrl"] == QUEUE_URL
    message = json.loads(sent["MessageBody"])
    assert set(message) == {
        "eventType", "eventId", "userId", "taskId", "occurredAt", "version"
    }
    assert message["eventType"] == "TASK_CREATED"
    assert message["eventId"]
    assert message["userId"] == "user-a"
    assert message["taskId"] == task["taskId"]
    assert (
        datetime.fromisoformat(message["occurredAt"]).utcoffset()
        == timezone.utc.utcoffset(None)
    )
    assert message["version"] == 1
    assert operation_order == ["persist", "publish"]


def test_create_returns_saved_task_id_if_event_publish_fails(publisher):
    module, table, sqs = publisher
    sqs.send_message.side_effect = RuntimeError("SQS unavailable")
    event = {
        "httpMethod": "POST",
        "requestContext": {"authorizer": {"claims": {"sub": "user-a"}}},
        "body": json.dumps({"title": "Write tests"}),
    }

    result = module.handler(event, None)

    assert result["statusCode"] == 503
    body = json.loads(result["body"])
    table.put_item.assert_called_once()
    assert body["taskId"] == table.put_item.call_args.kwargs["Item"]["taskId"]
    assert "Do not retry task creation" in body["message"]
    sqs.send_message.assert_called_once()
