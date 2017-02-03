from bravado.client import SwaggerClient
from bravado.requests_client import RequestsClient
import json
import pprint

f = open("swagger/proto/workflow_execution.swagger.json")
client = SwaggerClient.from_spec(json.load(f), origin_url="http://localhost:8080")

r = client.WorkflowService.RunWorkflow(body={
    "workflow_url": "http://xyz",
    "inputs": {"message": "hello"}}).result()

pprint.pprint(r)
