import json
import os
import subprocess
import urllib
import uuid

from wes_service.util import WESBackend


class Workflow(object):
    def __init__(self, workflow_id):
        super(Workflow, self).__init__()
        self.workflow_id = workflow_id
        self.workdir = os.path.join(os.getcwd(), "workflows", self.workflow_id)

    def run(self, request, opts):
        """
        Constructs a command to run a cwl/json from requests and opts,
        runs it, and deposits the outputs in outdir.

        Runner:
        opts.getopt("runner", default="cwl-runner")

        CWL (url):
        request["workflow_url"] == a url to a cwl file
        or
        request["workflow_descriptor"] == input cwl text (written to a file and a url constructed for that file)

        JSON File:
        request["workflow_params"] == input json text (to be written to a file)

        :param dict request: A dictionary containing the cwl/json information.
        :param wes_service.util.WESBackend opts: contains the user's arguments;
                                                 specifically the runner and runner options
        :return: {"workflow_id": self.workflow_id, "state": state}
        """
        os.makedirs(self.workdir)
        outdir = os.path.join(self.workdir, "outdir")
        os.mkdir(outdir)

        with open(os.path.join(self.workdir, "request.json"), "w") as f:
            json.dump(request, f)

        input_json = os.path.join(self.workdir, "cwl.input.json")
        with open(input_json, "w") as inputtemp:
            json.dump(request["workflow_params"], inputtemp)

        if request.get("workflow_descriptor"):
            workflow_descriptor = request.get('workflow_descriptor')
            with open(os.path.join(self.workdir, "workflow.cwl"), "w") as f:
                # FIXME #14 workflow_descriptor isn't defined
                f.write(workflow_descriptor)
            workflow_url = urllib.pathname2url(os.path.join(self.workdir, "workflow.cwl"))
        else:
            workflow_url = request.get("workflow_url")

        output = open(os.path.join(self.workdir, "cwl.output.json"), "w")
        stderr = open(os.path.join(self.workdir, "stderr"), "w")

        runner = opts.getopt("runner", default="cwl-runner")
        extra = opts.getoptlist("extra")  # if the user specified none, returns []
        command_args = [runner] + extra + [workflow_url, input_json]
        proc = subprocess.Popen(command_args,
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
        """
        Returns RUNNING, -1
                COMPLETE, 0
                or
                EXECUTOR_ERROR, 255
        """
        state = "RUNNING"
        exit_code = -1

        exitcode_file = os.path.join(self.workdir, "exit_code")
        pid_file = os.path.join(self.workdir, "pid")

        if os.path.exists(exitcode_file):
            with open(exitcode_file) as f:
                exit_code = int(f.read())
        elif os.path.exists(pid_file):
            with open(pid_file, "r") as pid:
                pid = int(pid.read())
            try:
                (_pid, exit_status) = os.waitpid(pid, os.WNOHANG)
                if _pid != 0:
                    exit_code = exit_status >> 8
                    with open(exitcode_file, "w") as f:
                        f.write(str(exit_code))
                    os.unlink(pid_file)
            except OSError:
                os.unlink(pid_file)
                exit_code = 255

        if exit_code == 0:
            state = "COMPLETE"
        elif exit_code != -1:
            state = "EXECUTOR_ERROR"

        return state, exit_code

    def getstatus(self):
        state, exit_code = self.getstate()

        return {
            "workflow_id": self.workflow_id,
            "state": state
        }

    def getlog(self):
        state, exit_code = self.getstate()

        with open(os.path.join(self.workdir, "request.json"), "r") as f:
            request = json.load(f)

        with open(os.path.join(self.workdir, "stderr"), "r") as f:
            stderr = f.read()

        outputobj = {}
        if state == "COMPLETE":
            output_path = os.path.join(self.workdir, "cwl.output.json")
            with open(output_path, "r") as outputtemp:
                outputobj = json.load(outputtemp)

        return {
            "workflow_id": self.workflow_id,
            "request": request,
            "state": state,
            "workflow_log": {
                "cmd": [""],
                "start_time": "",
                "end_time": "",
                "stdout": "",
                "stderr": stderr,
                "exit_code": exit_code
            },
            "task_logs": [],
            "outputs": outputobj
        }

    def cancel(self):
        pass


class CWLRunnerBackend(WESBackend):
    def GetServiceInfo(self):
        return {
            "workflow_type_versions": {
                "CWL": {"workflow_type_version": ["v1.0"]}
            },
            "supported_wes_versions": ["0.3.0"],
            "supported_filesystem_protocols": ["file", "http", "https"],
            "engine_versions": "cwl-runner",
            "system_state_counts": {},
            "key_values": {}
        }

    def ListWorkflows(self):
        # FIXME #15 results don't page
        wf = []
        for l in os.listdir(os.path.join(os.getcwd(), "workflows")):
            if os.path.isdir(os.path.join(os.getcwd(), "workflows", l)):
                wf.append(Workflow(l))

        workflows = [{"workflow_id": w.workflow_id, "state": w.getstate()[0]} for w in wf]  # NOQA
        return {
            "workflows": workflows,
            "next_page_token": ""
        }

    def RunWorkflow(self, body):
        # FIXME Add error responses #16
        if body["workflow_type"] == "CWL" and body["workflow_type_version"] != "v1.0":
            return
        workflow_id = uuid.uuid4().hex
        job = Workflow(workflow_id)
        job.run(body, self)
        return {"workflow_id": workflow_id}

    def GetWorkflowLog(self, workflow_id):
        job = Workflow(workflow_id)
        return job.getlog()

    def CancelJob(self, workflow_id):
        job = Workflow(workflow_id)
        job.cancel()
        return {"workflow_id": workflow_id}

    def GetWorkflowStatus(self, workflow_id):
        job = Workflow(workflow_id)
        return job.getstatus()


def create_backend(app, opts):
    return CWLRunnerBackend(opts)
