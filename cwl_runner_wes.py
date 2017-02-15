import connexion
from connexion.resolver import Resolver
import connexion.utils as utils

import threading
import tempfile
import subprocess
import uuid
import os
import json

class Workflow(object):
    def __init__(self, workflow_ID):
        super(Workflow, self).__init__()
        self.workflow_ID = workflow_ID
        self.workdir = os.path.abspath(self.workflow_ID)

    def run(self, path, inputobj):
        outdir = os.path.join(self.workdir, "outdir")
        with open(os.path.join(self.workdir, "cwl.input.json"), "w") as inputtemp:
            json.dump(inputtemp, inputobj)
        with open(os.path.join(self.workdir, "workflow_url"), "w") as f:
            f.write(path)
        output = open(os.path.join(self.workdir, "cwl.output.json"), "w")
        stderr = open(os.path.join(self.workdir, "stderr"), "w")

        proc = subprocess.Popen(["cwl-runner", path, inputtemp.name],
                                stdout=output,
                                stderr=stderr,
                                close_fds=True,
                                cwd=outdir)
        stdout.close()
        stderr.close()
        with open(os.path.join(self.workdir, "pid"), "w") as pid:
            pid.write(str(proc.pid))

        return self.getstatus()

    def getstate(self):
        state = "Running"
        exit_code = -1

        exc = os.path.join(self.workdir, "exit_code")
        if os.path.exists(exc):
            with open(exc) as f:
                exit_code = int(f.read())
            if exit_code == 0:
                state = "Complete"
            else:
                state = "Failed"
        else:
            with open(os.path.join(self.workdir, "pid"), "r") as pid:
                pid = int(pid.read())
            (_pid, exit_status) = os.waitpid(pid, os.WNOHANG)
            # record exit code

        return (state, exit_code)

    def getstatus(self):
        state, exit_code = self.getstate()

        with open(os.path.join(self.workdir, "cwl.input.json"), "r") as inputtemp:
            inputobj = json.load(inputtemp)
        with open(os.path.join(self.workdir, "workflow_url"), "r") as f:
            workflow_url = f.read()

        outputobj = None
        if state == "Complete":
            with open(os.path.join(self.workdir, "cwl.output.json"), "r") as outputtemp:
                outputtobj = json.load(outputtemp)

        return {
            "workflow_ID": self.workflow_ID,
            "workflow_url": workflow_url,
            "input": inputobj,
            "output": outputobj,
            "state": state
        }


    def getlog(self):
        state, exit_code = self.getstate()

        return {
            "workflow_ID": self.workflow_ID,
            "log": {
                "cmd": "",
                "startTime": "",
                "endTime": "",
                "stdout": "",
                "stderr": "",
                "exitCode": exit_code
            }
        }

    def cancel(self):
        pass

def GetWorkflowStatus(workflow_ID):
    job = Workflow(workflow_ID)
    job.getstatus()

def GetWorkflowLog(workflow_ID):
    job = Workflow(workflow_ID)
    job.getlog()

def CancelWorkflow(workflow_ID):
    job = Workflow(workflow_ID)
    job.cancel()

def RunWorkflow(body):
    workflow_ID = uuid.uuid4().hex
    job = Workflow(workflow_ID)
    job.run(body["workflow_url"], body["input"])
    return job.getstatus()

def main():
    app = connexion.App(__name__, specification_dir='swagger/')
    def rs(x):
        return utils.get_function_from_name("cwl_runner_wes." + x)

    app.add_api('proto/workflow_execution.swagger.json', resolver=Resolver(rs))

    app.run(port=8080)

if __name__ == "__main__":
    main()
