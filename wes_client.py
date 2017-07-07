#!/usr/bin/env python

from bravado.client import SwaggerClient
from bravado.requests_client import RequestsClient
import json
import time
import pprint
import sys

f = open("swagger/proto/workflow_execution.swagger.json")
client = SwaggerClient.from_spec(json.load(f), origin_url="http://localhost:8080")

with open(sys.argv[2]) as f:
    input = json.load(f)

r = client.WorkflowExecutionService.RunWorkflow(body={
    "workflow_url": sys.argv[1],
    "workflow_params": input,
    "workflow_type": "CWL",
    "workflow_type_version": "v1.0"}).result()

sys.stderr.write(r.workflow_id+"\n")

r = client.WorkflowExecutionService.GetWorkflowStatus(workflow_id=r.workflow_id).result()
while r.state == "Running":
    time.sleep(1)
    r = client.WorkflowExecutionService.GetWorkflowStatus(workflow_id=r.workflow_id).result()

s = client.WorkflowExecutionService.GetWorkflowLog(workflow_id=r.workflow_id).result()
sys.stderr.write(s.workflow_log.stderr+"\n")

d = {k: s.outputs[k] for k in s.outputs if k != "fields"}
json.dump(d, sys.stdout, indent=4)
