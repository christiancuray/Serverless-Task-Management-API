# Serverless Task Management API

A serverless REST API built with **Python and AWS CDK** for creating and managing tasks.

This project is designed to strengthen my backend development and cloud computing skills while preparing for the **AWS Certified Developer – Associate** certification.

The API is developed locally using **Floci**, an AWS cloud emulator, and has been deployed to AWS. The implementation includes authenticated task CRUD using Cognito, API Gateway, Lambda, DynamoDB, and SQS-based background processing.

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
Client (Postman / Frontend)
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

The Lambda handler scopes tasks to the authenticated user's Cognito `sub` claim and publishes task-created events to SQS for worker processing.

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
| Amazon CloudWatch  | Logging and monitoring (planned) |
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

The `serverless_task_api` directory contains the infrastructure code, while `src` contains the application's backend logic.

## API Endpoints

| Method | Endpoint          | Description               | Status      |
| ------ | ----------------- | ------------------------- | ----------- |
| POST   | `/tasks`          | Create a task             | Implemented |
| GET    | `/tasks`          | Retrieve the user's tasks | Implemented |
| GET    | `/tasks/{taskId}` | Retrieve a specific task  | Implemented |
| PUT    | `/tasks/{taskId}` | Update a task             | Implemented |
| DELETE | `/tasks/{taskId}` | Delete a task             | Implemented |

## Local Development Setup

### Prerequisites

- Python 3.13
- Node.js and npm
- AWS CDK CLI
- AWS CLI
- Docker
- Floci

An AWS account is not required for the current local development phase.

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

Real AWS deployment is complete. The CDK infrastructure has been deployed and the API, authentication, and AWS service integrations have been validated in the target environment.

Deployment and operations include:

1. Configure an AWS account and CLI credentials securely.
2. Bootstrap the AWS CDK environment.
3. Deploy the infrastructure using `cdk deploy`.
4. Configure Cognito authentication and least-privilege IAM policies.
5. Test API Gateway, Lambda, DynamoDB, and SQS in AWS.
6. Configure CloudWatch logging and monitoring.
7. Implement CI/CD using GitHub Actions.
8. Set up AWS Budgets and monitor resource usage.

The AWS CDK definitions are used for both local development and the deployed AWS environment, with environment-specific configuration as needed.

## Development Roadmap

| Week   | Focus                                       | Status                                                               |
| ------ | ------------------------------------------- | -------------------------------------------------------------------- |
| Week 1 | AWS CDK, Lambda, API Gateway, DynamoDB      | Implemented                                                          |
| Week 2 | Complete CRUD, Cognito, IAM security        | CRUD and Cognito implemented; end-to-end security validation remains |
| Week 3 | SQS, asynchronous processing, monitoring    | Complete: SQS queue, DLQ, publisher, worker, and duplicate-event idempotency |
| Week 4 | Automated testing, CI/CD, documentation     | Complete: unit and opt-in Floci integration coverage and project documentation |
| Week 5 | Real AWS deployment and security validation | Complete                                                             |
| Week 6 | Frontend development and user experience    | Proposed extension; planned                                          |

## Project Status

Weeks 3–5 are complete. Task creation publishes SQS events, a worker processes task-created events, the queue is configured with a dead-letter queue, and the worker uses DynamoDB idempotency records so an event ID is processed once. Unit and opt-in Floci integration tests cover event publishing, worker behavior, and queue redrive. The application has also been deployed to AWS and its API, authentication, and service integrations have been validated. Documentation describes test scope and failure behavior. GitHub Actions CI and frontend development remain future work.

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
