"""Opt-in handler integration tests using disposable Floci DynamoDB/SQS resources.

Run with RUN_FLOCI_INTEGRATION=1 after starting Floci. These tests create a
uniquely named table and queue; they do not run in normal pytest. Synthetic authorizer
claims exercise handler ownership logic, not Cognito JWT signatures or API Gateway.
"""

import importlib
import json
import os
import sys
from urllib.parse import urlparse
import uuid

import boto3
import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_FLOCI_INTEGRATION") != "1",
    reason="set RUN_FLOCI_INTEGRATION=1 to run against Floci",
)


@pytest.fixture
def floci_handler(monkeypatch):
    endpoint = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
    parsed_endpoint = urlparse(endpoint)
    if (
        parsed_endpoint.scheme != "http"
        or parsed_endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}
    ):
        pytest.fail("Floci integration tests require a loopback AWS_ENDPOINT_URL")
    region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    access_key = os.getenv("AWS_ACCESS_KEY_ID", "test")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "test")
    table_name = f"TasksTest{uuid.uuid4().hex[:12]}"
    dynamodb = boto3.resource(
        "dynamodb",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )
    sqs = boto3.client(
        "sqs",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )
    table = dynamodb.create_table(
        TableName=table_name,
        KeySchema=[
            {"AttributeName": "userId", "KeyType": "HASH"},
            {"AttributeName": "taskId", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "userId", "AttributeType": "S"},
            {"AttributeName": "taskId", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    queue_url = None
    try:
        table.wait_until_exists()
        queue_url = sqs.create_queue(
            QueueName=f"TaskEventsTest{uuid.uuid4().hex[:12]}"
        )["QueueUrl"]
        monkeypatch.setenv("AWS_ENDPOINT_URL", endpoint)
        monkeypatch.setenv("AWS_REGION", region)
        monkeypatch.setenv("TASKS_TABLE_NAME", table_name)
        monkeypatch.setenv("TASK_EVENTS_QUEUE_URL", queue_url)
        sys.modules.pop("src.tasks_handler", None)
        handler = importlib.import_module("src.tasks_handler")
        yield handler.handler
    finally:
        try:
            if queue_url:
                sqs.delete_queue(QueueUrl=queue_url)
        finally:
            try:
                table.delete()
                table.wait_until_not_exists()
            finally:
                sys.modules.pop("src.tasks_handler", None)


def request(handler, method, *, user="integration-user", task_id=None, body=None):
    event = {
        "httpMethod": method,
        "requestContext": {"authorizer": {"claims": {"sub": user}}},
        "pathParameters": {"taskId": task_id} if task_id else None,
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return handler(event, None)


def test_floci_crud_smoke(floci_handler):
    created = request(floci_handler, "POST", body={"title": "Floci smoke test"})
    assert created["statusCode"] == 201
    item = json.loads(created["body"])
    task_id = item["taskId"]

    assert request(floci_handler, "GET")["statusCode"] == 200
    assert request(floci_handler, "GET", task_id=task_id)["statusCode"] == 200
    updated = request(
        floci_handler,
        "PUT",
        task_id=task_id,
        body={"title": "Updated in Floci", "status": "DONE"},
    )
    assert updated["statusCode"] == 200
    assert json.loads(updated["body"])["status"] == "DONE"
    assert request(floci_handler, "DELETE", task_id=task_id)["statusCode"] == 204
    assert request(floci_handler, "GET", task_id=task_id)["statusCode"] == 404
