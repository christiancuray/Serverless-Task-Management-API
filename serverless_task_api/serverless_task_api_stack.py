from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_dynamodb as dynamodb,
    aws_lambda as _lambda,
    aws_apigateway as apigateway,
    aws_cognito as cognito,
    aws_sqs as sqs,
    aws_lambda_event_sources as event_sources,
)
from constructs import Construct
class ServerlessTaskApiStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # The code that defines your stack goes here

        # example resource
        # queue = sqs.Queue(
        #     self, "ServerlessTaskApiQueue",
        #     visibility_timeout=Duration.seconds(300),
        # )
        frontend_origin = "http://localhost:5173"

        # Cognito User Pool
        pool = cognito.UserPool(
            self, "TaskUsers",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
        )

        client = pool.add_client(
            "TaskAppClient",
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=True,),
            generate_secret=False,
        )
        # Export identifiers needed by the opt-in deployed API test. These are
        # resource identifiers, not credentials.
        CfnOutput(self, "TaskUserPoolId", value=pool.user_pool_id)
        CfnOutput(self, "TaskAppClientId", value=client.user_pool_client_id)

        authorizer = apigateway.CognitoUserPoolsAuthorizer(
            self, "TaskAuthorizer", cognito_user_pools=[pool]
        )

        # Dead Letter Queue for SQS
        dlq = sqs.Queue(self, "TaskEventsDLQ",
        retention_period=Duration.days(14))

        # SQS Queue for Task Events
        queue = sqs.Queue(self, "TaskEventsQueue",
                          visibility_timeout=Duration.seconds(90),
                          dead_letter_queue=sqs.DeadLetterQueue(
                              max_receive_count=3,
                              queue=dlq
                          ))

        # dynamo db
        tasks_table = dynamodb.Table(
            self, "TasksTable",
            table_name="Tasks",
            partition_key=dynamodb.Attribute(
                name="userId",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="taskId",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY
        )

        task_event_idempotency_table = dynamodb.Table(
            self, "TaskEventIdempotencyTable",
            partition_key=dynamodb.Attribute(
                name="eventId",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expiresAt",
            removal_policy=RemovalPolicy.DESTROY,
        )

        # lambda function
        fn =_lambda.Function(
            self, "TasksHandler",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="tasks_handler.handler",
            code=_lambda.Code.from_asset("src"),
            timeout=Duration.seconds(15),
            environment={
                "TASKS_TABLE_NAME": tasks_table.table_name,
                "FRONTEND_ORIGIN": frontend_origin,
            },
        )
        tasks_table.grant_read_write_data(fn)

        # Allow Task Handler Lambda to publish events to SQS
        queue.grant_send_messages(fn)

        worker = _lambda.Function(self, "TaskEventsWorkers",
                                 runtime=_lambda.Runtime.PYTHON_3_13,
                                 handler="task_events_worker.handler",
                                 code=_lambda.Code.from_asset("src"),
                                 timeout=Duration.seconds(20),
                                 environment={
                                     "TASK_EVENT_IDEMPOTENCY_TABLE_NAME": task_event_idempotency_table.table_name,
                                 })
        task_event_idempotency_table.grant_read_write_data(worker)
        worker.add_event_source(event_sources.SqsEventSource(
            queue, batch_size=5, report_batch_item_failures=True))
        queue.grant_consume_messages(worker)
        fn.add_environment("TASK_EVENTS_QUEUE_URL", queue.queue_url)


        # API Gateway
        api = apigateway.RestApi(self, "TasksApi",
                                 rest_api_name="TasksServiceApi",
                                 default_cors_preflight_options=apigateway.CorsOptions(
                                     allow_origins=[frontend_origin],
                                     allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                                     allow_headers=["Authorization", "Content-Type"]
                                 ))

        cors_gateway_headers = {
            "Access-Control-Allow-Origin": f"'{frontend_origin}'",
            "Access-Control-Allow-Headers": "'Authorization,Content-Type'",
            "Access-Control-Allow-Methods": "'GET,POST,PUT,DELETE,OPTIONS'",
        }

        api.add_gateway_response(
            "Default4xx",
            type=apigateway.ResponseType.DEFAULT_4_XX,
            response_headers=cors_gateway_headers,
        )

        api.add_gateway_response(
            "Default5xx",
            type=apigateway.ResponseType.DEFAULT_5_XX,
            response_headers=cors_gateway_headers,
        )
        
        CfnOutput(self, "TasksApiUrl", value=api.url)
        CfnOutput(self, "TasksApiId", value=api.rest_api_id)
        CfnOutput(self, "TasksApiStage", value=api.deployment_stage.stage_name)
        CfnOutput(self, "TaskAuthorizerId", value=authorizer.authorizer_id)
        tasks = api.root.add_resource("tasks")
        for method in ("GET", "POST"):
            tasks.add_method(
                method,
                apigateway.LambdaIntegration(fn),
                authorizer=authorizer,
                authorization_type=apigateway.AuthorizationType.COGNITO,
            )
        item = tasks.add_resource("{taskId}")
        for method in ("GET", "PUT", "DELETE"):
            item.add_method(
                method,
                apigateway.LambdaIntegration(fn),
                authorizer=authorizer,
                authorization_type=apigateway.AuthorizationType.COGNITO,
            )
