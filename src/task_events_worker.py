# logs each event and designed for SQS batch processing. for local dev, this does not send real email or modify any data in DynamoDb

import json
import logging
import os
import time
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_idempotency_table = None


def _table():
    """Create the DynamoDB table client lazily so local imports stay lightweight."""
    global _idempotency_table
    if _idempotency_table is None:
        table_name = os.environ.get("TASK_EVENT_IDEMPOTENCY_TABLE_NAME")
        if not table_name:
            raise RuntimeError("TASK_EVENT_IDEMPOTENCY_TABLE_NAME is not configured")
        _idempotency_table = boto3.resource("dynamodb").Table(table_name)
    return _idempotency_table

def handler(event, context):
    failures= []
    for record in event.get("Records", []):
        payload = None
        try:
            payload = json.loads(record["body"])
            if not isinstance(payload, dict):
                raise ValueError("Event body must be a JSON object")
            if payload.get("eventType") != "TASK_CREATED":
                raise ValueError(f"Unexpected event type: {payload.get('eventType')}")
            required = ("eventId", "userId", "taskId", "occurredAt")
            if any(
                not isinstance(payload.get(field), str) or not payload[field].strip()
                for field in required
            ):
                raise ValueError("Event is missing a required field")
            if type(payload.get("version")) is not int or payload["version"] != 1:
                raise ValueError(f"Unsupported event version: {payload['version']}")
            occurred_at = datetime.fromisoformat(payload["occurredAt"].replace("Z", "+00:00"))
            if (
                occurred_at.tzinfo is None
                or occurred_at.utcoffset() != timezone.utc.utcoffset(occurred_at)
            ):
                raise ValueError("occurredAt must include a UTC timezone")
        except (ValueError, KeyError, TypeError):
            logger.exception(
                "Unable to process SQS message message_id=%s event_id=%s",
                record.get("messageId"),
                payload.get("eventId") if isinstance(payload, dict) else None,
            )
            failures.append({"itemIdentifier": record["messageId"]})
            continue

        try:
            process_event(payload)
        except Exception:
            logger.exception("Retryable failure processing event_id=%s", payload["eventId"])
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures }


def process_event(payload):
    table = _table()
    event_id = payload["eventId"]
    try:
        table.put_item(
            Item={"eventId": event_id, "status": "PROCESSING", "expiresAt": int(time.time()) + 30 * 24 * 60 * 60},
            ConditionExpression="attribute_not_exists(eventId)",
        )
    except Exception as error:
        # ConditionalCheckFailedException indicates another delivery already claimed or
        # completed this event. It is acknowledged so SQS will not redeliver it.
        if error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.info("Skipping duplicate task event event_id=%s", event_id)
            return
        raise

    try:
        # Place state-changing event work here. The eventId claim prevents a second
        # delivery from running the same work concurrently.
        logger.info(
            "Processed task event event_id=%s user_id=%s task_id=%s",
            event_id, payload["userId"], payload["taskId"],
        )
        table.update_item(
            Key={"eventId": event_id},
            UpdateExpression="SET #status = :completed",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":completed": "COMPLETED"},
        )
    except Exception:
        # Permit a later SQS retry after a failed processing attempt.
        table.delete_item(Key={"eventId": event_id})
        raise

