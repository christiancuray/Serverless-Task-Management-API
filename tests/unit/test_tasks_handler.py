"""Isolated handler unit tests; no AWS or Floci connection is used."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError


HANDLER_PATH = Path(__file__).resolve().parents[2] / "src" / "tasks_handler.py"


def conditional_failure(operation):
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "Not found"}},
        operation,
    )


@pytest.fixture
def app(monkeypatch):
    """Mock boto3 before importing the handler, which initializes its table at import time."""
    monkeypatch.setenv("TASKS_TABLE_NAME", "UnitTestTasks")
    monkeypatch.setenv("TASK_EVENTS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123456789012/unit-test")
    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
    table = MagicMock()
    resource = MagicMock()
    resource.Table.return_value = table
    monkeypatch.setattr(boto3, "resource", lambda *args, **kwargs: resource)
    sqs = MagicMock()
    monkeypatch.setattr(boto3, "client", lambda service, *args, **kwargs: sqs)

    spec = importlib.util.spec_from_file_location("isolated_tasks_handler", HANDLER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return SimpleNamespace(handler=module.handler, table=table, sqs=sqs)


def call(app, method="GET", *, user="user-a", task_id=None, body=None, raw_body=None, claims=True):
    event = {"httpMethod": method, "pathParameters": {"taskId": task_id} if task_id else None}
    if claims:
        event["requestContext"] = {"authorizer": {"claims": {"sub": user}}}
    if body is not None:
        event["body"] = json.dumps(body)
    if raw_body is not None:
        event["body"] = raw_body
    return app.handler(event, None)


def payload(result):
    return json.loads(result["body"])


def test_create_task_uses_authenticated_user_and_defaults_status(app):
    result = call(
        app,
        "POST",
        body={"title": "  Study AWS  ", "status": "DONE", "userId": "spoofed"},
    )
    assert result["statusCode"] == 201
    item = payload(result)
    assert item == {
        "userId": "user-a",
        "taskId": item["taskId"],
        "title": "Study AWS",
        "status": "TODO",
    }
    assert item["taskId"]
    app.table.put_item.assert_called_once_with(Item=item)


def test_list_tasks_is_scoped_to_authenticated_user(app):
    app.table.query.return_value = {"Items": [{"taskId": "t1", "userId": "user-a"}]}
    result = call(app, "GET")
    assert result["statusCode"] == 200
    assert payload(result) == [{"taskId": "t1", "userId": "user-a"}]

    condition = app.table.query.call_args.kwargs["KeyConditionExpression"].get_expression()
    assert condition["values"][0].name == "userId"
    assert condition["values"][1] == "user-a"


def test_get_task_uses_authenticated_user_in_key(app):
    expected = {"taskId": "t1", "userId": "user-a"}
    app.table.get_item.return_value = {"Item": expected}
    result = call(app, task_id="t1")
    assert result["statusCode"] == 200
    assert payload(result) == expected
    app.table.get_item.assert_called_once_with(Key={"userId": "user-a", "taskId": "t1"})


def test_update_task_sends_scoped_key_and_normalized_title(app):
    app.table.update_item.return_value = {
        "Attributes": {"taskId": "t1", "userId": "user-a", "title": "Updated", "status": "DONE"}
    }
    result = call(app, "PUT", task_id="t1", body={"title": " Updated ", "status": "DONE"})
    assert result["statusCode"] == 200
    assert payload(result)["status"] == "DONE"

    kwargs = app.table.update_item.call_args.kwargs
    assert kwargs["Key"] == {"userId": "user-a", "taskId": "t1"}
    assert kwargs["ExpressionAttributeValues"] == {":title": "Updated", ":status": "DONE"}
    assert kwargs["ConditionExpression"] == "attribute_exists(taskId)"


def test_delete_task_is_scoped_and_requires_existing_task(app):
    result = call(app, "DELETE", task_id="t1")
    assert result["statusCode"] == 204
    app.table.delete_item.assert_called_once_with(
        Key={"userId": "user-a", "taskId": "t1"},
        ConditionExpression="attribute_exists(taskId)",
    )

def test_delete_task_missing(app):
    app.table.delete_item.side_effect = conditional_failure("DeleteItem")
    result = call(app, "DELETE", task_id="unknownId")
    assert result["statusCode"] == 404
    app.table.delete_item.assert_called_once_with(
        Key={"userId": "user-a", "taskId": "unknownId"},
        ConditionExpression="attribute_exists(taskId)",
    )


@pytest.mark.parametrize(
    "body",
    [{}, {"title": ""}, {"title": "   "}, {"title": None}, {"title": 123}],
)
def test_create_rejects_missing_or_invalid_title(app, body):
    result = call(app, "POST", body=body)
    assert result["statusCode"] == 400
    app.table.put_item.assert_not_called()


@pytest.mark.parametrize("status", ["INVALID", "done", "", None, 123])
def test_update_rejects_invalid_status(app, status):
    result = call(app, "PUT", task_id="t1", body={"title": "Task", "status": status})
    assert result["statusCode"] == 400
    app.table.update_item.assert_not_called()


@pytest.mark.parametrize("method", ["POST", "PUT"])
def test_mutations_reject_malformed_json(app, method):
    task_id = "t1" if method == "PUT" else None
    result = call(app, method, task_id=task_id, raw_body="{oops")
    assert result["statusCode"] == 400
    app.table.put_item.assert_not_called()
    app.table.update_item.assert_not_called()


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "DELETE"])
def test_missing_claims_returns_401_before_database_access(app, method):
    result = call(app, method, task_id="t1", body={"title": "Task", "status": "TODO"}, claims=False)
    assert result["statusCode"] == 401
    app.table.query.assert_not_called()
    app.table.get_item.assert_not_called()
    app.table.put_item.assert_not_called()
    app.table.update_item.assert_not_called()
    app.table.delete_item.assert_not_called()


def test_user_b_cannot_read_user_a_task(app):
    app.table.get_item.return_value = {}
    result = call(app, "GET", user="user-b", task_id="task-owned-by-a")
    assert result["statusCode"] == 404
    app.table.get_item.assert_called_once_with(
        Key={"userId": "user-b", "taskId": "task-owned-by-a"}
    )


def test_missing_task_returns_404_on_get(app):
    app.table.get_item.return_value = {}
    result = call(app, "GET", task_id="missing")
    assert result["statusCode"] == 404


@pytest.mark.parametrize("method,operation", [("PUT", "UpdateItem"), ("DELETE", "DeleteItem")])
def test_missing_task_returns_404_on_mutation(app, method, operation):
    db_method = app.table.update_item if method == "PUT" else app.table.delete_item
    db_method.side_effect = conditional_failure(operation)
    body = {"title": "Task", "status": "TODO"} if method == "PUT" else None
    result = call(app, method, task_id="missing", body=body)
    assert result["statusCode"] == 404


def test_unrecognized_method_returns_405(app):
    result = call(app, "PATCH", task_id="t1")
    assert result["statusCode"] == 405
    app.table.get_item.assert_not_called()
