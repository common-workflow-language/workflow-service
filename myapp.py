def GetWorkflowStatus(workflow_ID):
    return {"workflow_ID": workflow_ID}

def GetWorkflowLog():
    pass

def CancelJob():
    pass

def RunWorkflow(body):
    print body
    return {"workflow_ID": "1"}
