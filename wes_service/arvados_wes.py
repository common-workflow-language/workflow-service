import arvados

def GetServiceInfo():
    return {
        "workflow_type_versions": {
            "CWL": ["v1.0"]
        },
        "supported_wes_versions": "0.1.0",
        "supported_filesystem_protocols": ["file"],
        "engine_versions": "cwl-runner",
        "system_state_counts": {},
        "key_values": {}
    }

def ListWorkflows(body):
    # body["page_size"]
    # body["page_token"]
    # body["key_value_search"]

    wf = []
    for l in os.listdir(os.path.join(os.getcwd(), "workflows")):
        if os.path.isdir(os.path.join(os.getcwd(), "workflows", l)):
            wf.append(Workflow(l))
    return {
        "workflows": [{"workflow_id": w.workflow_id, "state": w.getstate()} for w in wf],
        "next_page_token": ""
    }

def RunWorkflow(body):
    if body["workflow_type"] != "CWL" or body["workflow_type_version"] != "v1.0":
        return
    workflow_id = uuid.uuid4().hex
    job = Workflow(workflow_id)
    job.run(body)
    return {"workflow_id": workflow_id}

def GetWorkflowLog(workflow_id):
    job = Workflow(workflow_id)
    return job.getlog()

def CancelJob(workflow_id):
    job = Workflow(workflow_id)
    job.cancel()
    return {"workflow_id": workflow_id}

def GetWorkflowStatus(workflow_id):
    job = Workflow(workflow_id)
    return job.getstatus()
