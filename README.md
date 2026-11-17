# Serverless Task Management API

A serverless REST API built with **Python and AWS CDK** for creating and managing tasks.

This project is designed to strengthen my backend development and cloud computing skills while preparing for the **AWS Certified Developer – Associate** certification.

The API is developed locally using **Floci**, an AWS cloud emulator, and has been deployed to AWS. The completed backend includes authenticated task CRUD using Cognito, API Gateway, Lambda, DynamoDB, and SQS-based background processing.

The separate frontend application is documented in the [Tasky-UI repository](https://github.com/christiancuray/Tasky-UI).

## Project Goals

- Build a serverless REST API using Python.
- Learn how AWS services communicate with each other.
- Practice Infrastructure as Code (IaC) using AWS CDK.
- Implement authentication, database operations, and asynchronous processing.
- Gain hands-on experience with AWS development, deployment, security, and monitoring.
- Prepare the application for deployment to real AWS.

## Architecture

The application follows a serverless architecture:

```text
API Client
            |
            v
       API Gateway
            |
            v
        AWS Lambda
         (Python)
            |
            v
        DynamoDB
       (Task Storage)
```

The current infrastructure also includes Cognito authentication and SQS-based background task event processing:

```text
Amazon Cognito
      |
      v
 API Gateway
      |
      v
 AWS Lambda --------> DynamoDB
      |
      v
  Amazon SQS
      |
      v
 Worker Lambda
```

**Request flow:**

1. A client sends an HTTP request to API Gateway.
2. API Gateway routes the request to a Python Lambda function.
3. Lambda processes the request and interacts with DynamoDB.
4. DynamoDB stores or retrieves task information.
5. Lambda returns an HTTP response through API Gateway.

## Tech Stack

| Technology         | Purpose                          |
| ------------------ | -------------------------------- |
| Python 3.13        | Backend development              |
| AWS CDK            | Infrastructure as Code           |
| AWS Lambda         | Serverless application logic     |
| Amazon API Gateway | REST API endpoints               |
| Amazon DynamoDB    | NoSQL task storage               |
| Amazon Cognito     | User authentication              |
| Amazon SQS         | Background task event processing |
| Amazon CloudWatch  | AWS logging and monitoring       |
| Floci              | Local AWS service emulation      |
| Docker             | Local container environment      |
| boto3              | AWS SDK for Python               |
| pytest             | Automated testing                |

## Project Structure

```text
serverless-task-api/
├── .venv/                         # Python virtual environment
├── .gitignore
├── app.py                         # AWS CDK entry point
├── cdk.json                       # CDK configuration
├── requirements.txt               # Python CDK dependencies
│
├── serverless_task_api/
│   ├── __init__.py
│   └── serverless_task_api_stack.py
│                                    # AWS infrastructure definitions
│
├── src/
│   ├── __init__.py
│   └── tasks_handler.py           # Python Lambda handler
│
├── tests/                         # Automated tests
├── cdk.out/                       # Generated CloudFormation templates
└── README.md
```

## Local Development Setup

### Prerequisites

- Python 3.13
- Node.js and npm
- AWS CDK CLI
- AWS CLI
- Docker
- Floci

An AWS account is not required to run the automated unit tests. A deployed backend is required for AWS-based API validation.

### 1. Clone the repository

```bash
git clone <repository-url>
cd serverless-task-api
```

Replace `<repository-url>` with the actual GitHub repository URL.

### 2. Create and activate a virtual environment

```bash
python3.13 -m venv .venv
source .venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 4. Configure Floci

Start Floci locally using its installed application or configured Docker environment.

Set the local AWS endpoint and development credentials:

```bash
export AWS_ENDPOINT_URL=http://localhost:4566
export AWS_DEFAULT_REGION=us-east-1
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
```

These credentials are placeholders for local development and are not real AWS credentials.

### 5. Verify the local connection

```bash
aws --endpoint-url=http://localhost:4566 dynamodb list-tables
```

This command checks whether the local DynamoDB emulator is accessible.

### 6. Generate the CloudFormation template

```bash
cdk synth
```

AWS CDK generates the CloudFormation template from the Python infrastructure definitions.

**Note:** `cdk synth` does not deploy AWS resources.

## Local Testing

The project uses Floci to test supported AWS services locally before deploying to real AWS.

### Run automated tests

Install development dependencies and run the unit suite (uses mocked DynamoDB; no Floci instance is needed):

```bash
pip install -r requirements-dev.txt
pytest
```

The Floci handler integration test is kept separate. It creates and deletes a uniquely named disposable DynamoDB table, so run it only against a disposable Floci environment:

```bash
RUN_FLOCI_INTEGRATION=1 pytest tests/integration -q
```

Set `AWS_ENDPOINT_URL` if Floci is not at `http://localhost:4566`. The integration test uses the configured AWS credentials and region, defaulting to `test` / `test` and `us-east-1`.

### List DynamoDB tables

```bash
aws --endpoint-url=http://localhost:4566 dynamodb list-tables
```

### Inspect the Tasks table

```bash
aws --endpoint-url=http://localhost:4566 dynamodb describe-table \
  --table-name Tasks
```

### Test the Lambda handler locally

After the `Tasks` table exists in Floci:

```bash
export TASKS_TABLE_NAME=Tasks
export AWS_REGION=us-east-1

python - <<'PY'
import json
from src.tasks_handler import handler

response = handler({
    "httpMethod": "POST",
    "body": json.dumps({"title": "Study AWS Lambda"})
}, None)

print(response)
PY
```

This directly tests the Python handler. It does not test API Gateway or the deployed Lambda runtime.

The integration test directly invokes the handler; it does not test API Gateway or Cognito token validation.

## Floci and Local Development Limitations

Floci allows AWS-style development without requiring an AWS account. However, local emulation does not always behave exactly like real AWS.

Some limitations include:

- Certain AWS features or API operations may be unsupported.
- IAM permissions and authentication may not behave exactly as they do in AWS.
- CloudFormation and CDK deployment compatibility may vary.
- Lambda execution environments may differ from AWS-managed runtimes.
- CloudWatch monitoring and production-scale performance cannot be fully validated locally.

For these reasons, successful local testing does not guarantee identical behavior in AWS.

The project will be designed to minimize environment-specific code so that migration to real AWS is easier.

## AWS Deployment

The backend has been deployed to AWS. The CDK stack defines the API, authentication, data storage, queue, worker, and event idempotency resources. Local development and automated tests can also use Floci without changing application logic.

## Project Status

The backend is complete for its current scope and has been deployed to AWS. It provides authenticated task CRUD, publishes task-created events to SQS, and processes events with a worker and dead-letter queue. The worker uses DynamoDB idempotency records to prevent processing the same event ID more than once. Unit and opt-in Floci integration tests cover handler, publisher, worker, and queue behavior. Automated CI remains a possible future improvement.

## Learning Outcomes

Through this project, I aim to gain practical experience with:

- Serverless application development
- REST API design
- AWS SDK for Python (boto3)
- DynamoDB data modeling
- Infrastructure as Code
- Cloud security and IAM
- Event-driven architecture
- Monitoring and troubleshooting
- Automated testing and CI/CD

This project serves as both a hands-on AWS learning experience and a portfolio project demonstrating backend and cloud development skills.
