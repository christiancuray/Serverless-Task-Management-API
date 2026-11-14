"""Opt-in SQS worker integration tests against isolated Floci queues."""

import importlib.util
import json
import os
from pathlib import Path
from urllib.parse import urlparse
import uuid

import boto3
import pytest


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_FLOCI_INTEGRATION") != "1",
        reason="set RUN_FLOCI_INTEGRATION=1 to run against Floci",
    ),
]
WORKER_PATH = Path(__file__).resolve().parents[2] / "src" / "task_events_worker.py"


@pytest.fixture
def floci_sqs():
    endpoint = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
    parsed_endpoint = urlparse(endpoint)
    if (
        parsed_endpoint.scheme != "http"
        or parsed_endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}
    ):
        pytest.fail("Floci integration tests require a loopback AWS_ENDPOINT_URL")

    session = boto3.session.Session()
    sqs = session.client(
        "sqs",
        endpoint_url=endpoint,
        region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
    )
    suffix = uuid.uuid4().hex[:12]
    queue_url = sqs.create_queue(QueueName=f"TaskEventsTest{suffix}")["QueueUrl"]
    try:
        yield sqs, queue_url
    finally:
        sqs.delete_queue(QueueUrl=queue_url)


def load_worker():
    spec = importlib.util.spec_from_file_location("isolated_floci_task_events_worker", WORKER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sqs_event_is_delivered_and_worker_acknowledges_it(floci_sqs, caplog):
    sqs, queue_url = floci_sqs
    message = {
        "eventType": "TASK_CREATED",
        "eventId": str(uuid.uuid4()),
        "userId": "integration-user",
        "taskId": str(uuid.uuid4()),
        "occurredAt": "2026-11-14T12:00:00+00:00",
        "version": 1,
    }
    sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(message))

    received = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1)["Messages"][0]
    result = load_worker().handler(
        {"Records": [{"messageId": received["MessageId"], "body": received["Body"]}]}, None
    )
    assert result == {"batchItemFailures": []}
    assert f"event_id={message['eventId']}" in caplog.text
    assert f"task_id={message['taskId']}" in caplog.text

    # Lambda normally deletes successfully processed messages; emulate that acknowledgement.
    sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=received["ReceiptHandle"])
    assert "Messages" not in sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1)


def test_poison_message_can_be_redriven_to_disposable_dlq(floci_sqs):
    sqs, source_url = floci_sqs
    dlq_name = f"TaskEventsDLQTest{uuid.uuid4().hex[:12]}"
    dlq_url = sqs.create_queue(QueueName=dlq_name)["QueueUrl"]
    try:
        dlq_arn = sqs.get_queue_attributes(
            QueueUrl=dlq_url, AttributeNames=["QueueArn"]
        )["Attributes"]["QueueArn"]
        redrive_policy = json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "1"})
        sqs.set_queue_attributes(
            QueueUrl=source_url,
            Attributes={"RedrivePolicy": redrive_policy},
        )
        message = {
            "eventType": "TASK_CREATED",
            "eventId": str(uuid.uuid4()),
            "userId": "integration-user",
            "taskId": str(uuid.uuid4()),
            "occurredAt": "2026-11-14T12:00:00+00:00",
            "version": 1,
        }
        body = json.dumps(message)
        sqs.send_message(QueueUrl=source_url, MessageBody=body)
        received = sqs.receive_message(QueueUrl=source_url, MaxNumberOfMessages=1)["Messages"][0]
        worker = load_worker()
        worker.process_event = lambda payload: (_ for _ in ()).throw(
            RuntimeError("simulated retryable downstream failure")
        )
        failure = worker.handler(
            {"Records": [{"messageId": received["MessageId"], "body": received["Body"]}]}, None
        )
        assert failure == {"batchItemFailures": [{"itemIdentifier": received["MessageId"]}]}

        # Redrive occurs after a failed delivery is received again, not in the worker.
        sqs.change_message_visibility(
            QueueUrl=source_url, ReceiptHandle=received["ReceiptHandle"], VisibilityTimeout=0
        )
        sqs.receive_message(QueueUrl=source_url, MaxNumberOfMessages=1)
        dead = sqs.receive_message(QueueUrl=dlq_url, MaxNumberOfMessages=1)
        assert dead.get("Messages", [])[0]["Body"] == body
    finally:
        sqs.delete_queue(QueueUrl=dlq_url)
