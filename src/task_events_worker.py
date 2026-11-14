# logs each event and designed for SQS batch processing. for local dev, this does not send real email or modify any data in DynamoDb

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

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
    # This worker currently has no state-changing side effects, so duplicate delivery is safe.
    logger.info(
        "Processed task event event_id=%s user_id=%s task_id=%s",
        payload["eventId"], payload["userId"], payload["taskId"],
    )

