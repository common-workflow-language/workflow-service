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
        path = os.path.abspath(path)
        os.mkdir(self.workdir)
        outdir = os.path.join(self.workdir, "outdir")
        os.mkdir(outdir)
        with open(os.path.join(self.workdir, "cwl.input.json"), "w") as inputtemp:
            json.dump(inputobj, inputtemp)
        with open(os.path.join(self.workdir, "workflow_url"), "w") as f:
            f.write(path)
        output = open(os.path.join(self.workdir, "cwl.output.json"), "w")
        stderr = open(os.path.join(self.workdir, "stderr"), "w")

        proc = subprocess.Popen(["cwl-runner", path, inputtemp.name],
                                stdout=output,
                                stderr=stderr,
                                close_fds=True,
                                cwd=outdir)
        output.close()
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
        else:
            with open(os.path.join(self.workdir, "pid"), "r") as pid:
                pid = int(pid.read())
            (_pid, exit_status) = os.waitpid(pid, os.WNOHANG)
            if _pid != 0:
                exit_code = exit_status >> 8
                with open(exc, "w") as f:
                    f.write(str(exit_code))
                os.unlink(os.path.join(self.workdir, "pid"))

        if exit_code == 0:
            state = "Complete"
        elif exit_code != -1:
            state = "Failed"

        return (state, exit_code)

    def getstatus(self):
        state, exit_code = self.getstate()

        with open(os.path.join(self.workdir, "cwl.input.json"), "r") as inputtemp:
            inputobj = json.load(inputtemp)
        with open(os.path.join(self.workdir, "workflow_url"), "r") as f:
            workflow_url = f.read()

        outputobj = {}
        if state == "Complete":
            with open(os.path.join(self.workdir, "cwl.output.json"), "r") as outputtemp:
                outputobj = json.load(outputtemp)

        return {
            "workflow_ID": self.workflow_ID,
            "workflow_url": workflow_url,
            "input": inputobj,
            "output": outputobj,
            "state": state
        }


    def getlog(self):
        state, exit_code = self.getstate()

        with open(os.path.join(self.workdir, "stderr"), "r") as f:
            stderr = f.read()

        return {
            "workflow_ID": self.workflow_ID,
            "log": {
                "cmd": [""],
                "startTime": "",
                "endTime": "",
                "stdout": "",
                "stderr": stderr,
                "exitCode": exit_code
            }
        }

    def cancel(self):
        pass

def GetWorkflowStatus(workflow_ID):
    job = Workflow(workflow_ID)
    return job.getstatus()

def GetWorkflowLog(workflow_ID):
    job = Workflow(workflow_ID)
    return job.getlog()

def CancelWorkflow(workflow_ID):
    job = Workflow(workflow_ID)
    job.cancel()
    return job.getstatus()

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
