# logs each event and designed for SQS batch processing. for local dev, this does not send real email or modify any data in DynamoDb

import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    failures= []
    for record in event.get("Records", []):
        try:
            payload = json.loads(record["body"])
            if payload.get("eventType") != "TASK_CREATED":
                raise ValueError(f"Unexpected event type: {payload.get('eventType')}")
            # successfully processed event
            logger.info(f"Task created for user {payload.get('userId')} with task ID {payload.get('taskId')}")
        except (ValueError, KeyError, TypeError) as e:
            logger.exception("Unable to process SQS message")
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures }

