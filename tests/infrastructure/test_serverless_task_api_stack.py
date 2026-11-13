import aws_cdk as core
import aws_cdk.assertions as assertions

from serverless_task_api.serverless_task_api_stack import ServerlessTaskApiStack

def test_tasks_api_resources_created():
    app = core.App()
    stack = ServerlessTaskApiStack(app, "serverless-task-api")
    template = assertions.Template.from_stack(stack)
    template.resource_count_is("AWS::ApiGateway::RestApi", 1)
    template.resource_count_is("AWS::Lambda::Function", 1)
