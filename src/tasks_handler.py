import json
import os
import boto3 
import uuid
from datetime import datetime, timezone
import logging

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

client_options = { "region_name": os.getenv("AWS_REGION", "us-east-1") }
if os.getenv("AWS_ENDPOINT_URL"):
    client_options["endpoint_url"] = os.environ["AWS_ENDPOINT_URL"]

table = boto3.resource("dynamodb", **client_options).Table(os.environ["TASKS_TABLE_NAME"])

sqs = boto3.client("sqs", **client_options)
logger = logging.getLogger(__name__)

###
### Do not read userId from a request body/header. In production, Lambda must be reachable only through
### trusted paths or perform its own JWT validation.
###
def handler(event, context):
    claims = (event.get("requestContext") or {}).get("authorizer") or {}
    user_id = claims.get("claims", {}).get("sub")
    if not user_id:
        return response(401, {"message": "Unauthorized"})
    
    # Determine the HTTP method from the event
    method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method")
    task_id = (event.get("pathParameters") or {}).get("taskId")
    key = {"userId": user_id, "taskId": task_id} if task_id else None

    # Handle POST req to create a new task
    if method in ("POST", "PUT"):
        try:
            body = json.loads(event.get("body", "{}"))
        except (ValueError, TypeError):
            return response(400, {"message": "Invalid JSON body!"})
        if not isinstance(body, dict):
            return response(400, {"message": "Invalid request body!"})

        if method == "POST" and not task_id:
            title = body.get("title")
            if not isinstance(title, str) or not title.strip():
                return response(400, {"message": "Invalid title!"})
            item = {
                "userId": user_id,
                "taskId": str(uuid.uuid4()),
                "title": title.strip(),
                "status": "TODO"
            }
            table.put_item(Item=item)
            try:
                publish_task_created(item)
            except Exception:
                logger.exception("Task persisted but event publishing failed; task_id=%s", item["taskId"])
                return response(503, {
                    "message": "Task was saved, but its event could not be published. Do not retry task creation.",
                    "taskId": item["taskId"],
                })
            return response(201, item)

        if method == "PUT" and task_id:
            title, status =  body.get("title"), body.get("status")
            if not isinstance(title, str) or not title.strip():
                return response(400, {"message": "Invalid title!"})
            if not isinstance(status, str) or status not in ["TODO", "IN_PROGRESS", "DONE"]:
                return response(400, {"message": "Invalid status!"})
            try:
                res = table.update_item(
                    Key=key,
                    UpdateExpression="SET title = :title, #s = :status",
                    ConditionExpression="attribute_exists(taskId)",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":title": title.strip(),
                        ":status": status
                    },
                    ReturnValues="ALL_NEW")
                return response(200, res["Attributes"])
            except ClientError as e:
                if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    return response(404, {"message": "Task not found!"})
                else:
                    return response(500, {"message": "Internal Server Error!"})

    # Handle GET request to retrieve tasks
    if method == "GET" and not task_id:
        res = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("userId").eq(user_id)
        )
        return response(200, res.get("Items", []))
    if method == "GET" and task_id:
        item = table.get_item(Key=key).get("Item")
        return response(200, item) if item else response(404, {"message": "Task not found!"})

    # Handle DELETE request to delete a task
    if method == "DELETE" and task_id:
        try:
            table.delete_item(
                Key=key,
                ConditionExpression="attribute_exists(taskId)"
            )
            return response(204, {})
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return response(404, {"message": "Task not found!"})
            else:
                return response(500, {"message": "Internal Server Error!"})
            
    # Handle Invalid method
    return response(405, {"message": "Method Not Allowed"})

def publish_task_created(item):
    queue_url = os.environ.get("TASK_EVENTS_QUEUE_URL")
    if not queue_url:
        raise RuntimeError("TASK_EVENTS_QUEUE_URL is missing")
    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps({
            "eventType": "TASK_CREATED",
            "eventId": str(uuid.uuid4()),
            "userId": item["userId"],
            "taskId": item["taskId"],
            "occurredAt": datetime.now(timezone.utc).isoformat(),
            "version": 1,
        })
    )

def response(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": os.getenv(
                "FRONTEND_ORIGIN", "http://localhost:5173"
            ),
        },
        "body": json.dumps(body),
    }
