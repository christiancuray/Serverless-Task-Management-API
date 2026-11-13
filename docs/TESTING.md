# Serverless Task Management API — Testing and Review

## Summary

Reviewed `test_tasks_handler_floci.py` and `tasks_handler.py`. The original test is **an opt-in integration smoke test**, not a unit test: it creates a real disposable DynamoDB table through Floci and exercises create/list/get/update/delete. It is valuable and should be kept under `tests/integration/`. It does not test all negative/security cases and it does not exercise API Gateway or Cognito's JWT validation.

Added an isolated `tests/unit/test_tasks_handler.py` using `pytest` and `unittest.mock`. The tests patch `boto3.resource` **before** importing the Lambda module, because the production handler constructs its DynamoDB table at module import time. The unit tests do not need Floci, Docker, real AWS, or network access.

## Test layout

```text
serverless-task-api/
├── src/tasks_handler.py                 # existing application code
├── tests/unit/test_tasks_handler.py     # new mocked tests
├── tests/integration/test_tasks_handler_floci.py  # original integration smoke test
├── pytest.ini
├── requirements-dev.txt
└── docs/TESTING.md
```

## Install and run

From the project root with your virtual environment activated:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The default pytest configuration searches **only** `tests/unit`.

To run the existing integration test, start Floci, verify the endpoint is local, and opt in:

```bash
export AWS_ENDPOINT_URL=http://localhost:4566
export AWS_DEFAULT_REGION=us-east-1
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
RUN_FLOCI_INTEGRATION=1 python -m pytest tests/integration -q
```

**Safety:** the integration fixture creates and deletes a uniquely named table. Never set `AWS_ENDPOINT_URL` to a real AWS endpoint when running this test. The original integration fixture should be hardened to reject non-loopback endpoints and to use disposable credentials explicitly before broader use.

## Test coverage

| Scenario | Test | Expected |
|---|---|---|
| Create task | `test_create_task` | 201; trims title, sets `TODO`, uses JWT `sub` |
| List tasks | `test_list_tasks` | 200; queries current user's partition |
| Get task | `test_get_task` | 200; composite key includes user ID |
| Update task | `test_update_task` | 200; conditional update |
| Delete task | `test_delete_task` | 204; conditional delete |
| Missing/invalid title | `test_missing_or_invalid_title_on_create` | 400 |
| Invalid status | `test_invalid_status_on_update` | 400 |
| Malformed JSON | `test_malformed_json` | 400 |
| Missing authorizer claims | `test_missing_claims_returns_401` | 401 |
| Cross-user read | `test_user_b_cannot_read_user_a_task` | 404; lookup uses user B's key |
| Missing task | `test_missing_task_returns_404` | 404 |
| Missing task on update/delete | `test_missing_task_on_mutation_returns_404` | 404 |
| Unsupported method | `test_unsupported_method` | 405 |

The unit isolation test verifies the **handler's query-key behavior**, not Cognito JWT verification or DynamoDB's actual isolation guarantees. End-to-end security still needs API Gateway + Cognito integration testing.

## Findings in production handler

1. **Import-time dependencies:** `table = boto3.resource(...).Table(os.environ['TASKS_TABLE_NAME'])` runs on import. Tests must mock boto3 and configure the environment before importing. Consider lazy initialization or a small dependency-injection function for maintainability.
2. **HTTP 204 response body:** `DELETE` returns 204 with a JSON body. HTTP 204 responses should have no body; return `body: ''` instead. This is an application-code improvement, not silently changed in the supplied handler.
3. **Missing body:** `json.loads(event.get('body', '{}'))` can raise a TypeError for `None` (handled as 400), which is acceptable; distinguish malformed and missing bodies if the API contract requires it.
4. **Cognito trust boundary:** handler uses `requestContext.authorizer.claims.sub`, which is appropriate only if invocation is restricted to a trusted API Gateway integration or JWTs are independently verified. The unit test does not verify signatures.
5. **No cross-user mutation:** conditional PUT and DELETE are scoped to `{'userId': sub, 'taskId': id}`. Add integration coverage proving user B cannot update/delete user A's item.
6. **Consistency:** `from boto3.dynamodb.conditions import Key` is already imported; use `Key('userId').eq(user_id)` rather than the longer `boto3.dynamodb.conditions.Key(...)`.
7. **Error handling:** POST, list GET and single GET do not catch DynamoDB ClientError; consider consistent safe 500 responses and structured logs without exposing secrets.

## Recommended integration improvements

- Assert actual returned item content after list/get, not just status codes.
- Add user B isolation checks for GET, PUT, and DELETE, then confirm user A's item still exists.
- Assert missing/invalid input and conditional failures against disposable Floci DynamoDB.
- Keep separate HTTP integration tests for API Gateway JWT acceptance/rejection; direct handler invocation bypasses the authorizer.
- Use a loopback-only endpoint guard before creating or deleting any table.
- Ensure module import/reload doesn't interfere with other tests in the same pytest process.

## Lessons learned

- Unit tests validate business logic quickly and deterministically by mocking dependencies.
- Integration tests validate actual interactions with the emulator, but require startup, cleanup, and isolation.
- An API Gateway 401 response cannot be fully tested by directly calling a Lambda handler; JWT validation belongs to the gateway/authorizer layer.
- User ownership must come from trusted authentication claims, not client-provided JSON.
- Test setup should never touch a shared development table.

## Review status

These files were reviewed against the uploaded handler. Execute `python -m pytest -q` in the project root to verify compatibility with your repository. The original Floci integration test was not executed against your local emulator in this environment.
