import json
import os
import boto3 
import uuid

client_options = { "region_name": os.getenv("AWS_REGION", "us-east-1") }
if os.getenv("AWS_ENDPOINT_URL"):
    client_options["endpoint_url"] = os.environ["AWS_ENDPOINT_URL"]

table = boto3.resource("dynamodb", **client_options).Table(os.environ["TASKS_TABLE_NAME"])

def handler(event, context):
    # Determine the HTTP method from the event
    method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method")

    # Handle POST req to create a new task
    if method == "POST":
        try:
            body = json.loads(event.get("body", "{}"))
        except json.JSONDecodeError:
            return reply(400, {"message": "Invalid JSON body!"})

        # valid body
        title = body.get("title")
        if not isinstance(title, str) or not title.strip():
            return reply(400, {"message": "Invalid title!"})
        item = {
            "userId": "demo-user",
            "taskId": str(uuid.uuid4()),
            "title": title.strip(),
            "status": "TODO"
        }
        table.put_item(Item=item)
        return reply(201, item)

    # Handle GET request to retrieve tasks
    if method == "GET":
        res = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("userId").eq("demo-user")
        )
        return reply(200, res.get("Items", []))
    return reply(405, {"message": "Method Not Allowed"})

def reply(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
 }