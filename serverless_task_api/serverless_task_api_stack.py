from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_dynamodb as dynamodb,
    aws_lambda as _lambda,
    aws_apigateway as apigateway,
    aws_cognito as cognito,
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

        # Cognito User Pool
        pool = cognito.UserPool(
            self, "TaskUsers",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
        )

        client = pool.add_client(
            "TaskAppClient",
            auth_flows=cognito.AuthFlow(user_password=True),
            generate_secret=False,
        )

        authorizer = apigateway.CognitoUserPoolsAuthorizer(
            self, "TaskAuthorizer", cognito_user_pools=[pool]
        )

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
        # lambda function
        fn =_lambda.Function(
            self, "TasksHandler",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="tasks_handler.handler",
            code=_lambda.Code.from_asset("src"),
            timeout=Duration.seconds(15),
            environment={
                "TASKS_TABLE_NAME": tasks_table.table_name
            },
        )
        tasks_table.grant_read_write_data(fn)


        # API Gateway
        api = apigateway.RestApi(self, "TasksApi")
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