import json
import os
import subprocess  # nosec B404
import uuid
from typing import Any, cast

from wes_service.util import WESBackend


class Workflow:
    def __init__(self, run_id: str) -> None:
        """Construct a workflow runner."""
        super().__init__()
        self.run_id = run_id
        self.workdir = os.path.join(os.getcwd(), "workflows", self.run_id)
        self.outdir = os.path.join(self.workdir, "outdir")
        if not os.path.exists(self.outdir):
            os.makedirs(self.outdir)

    def run(
        self, request: dict[str, str], tempdir: str, opts: WESBackend
    ) -> dict[str, str]:
        """
        Constructs a command to run a cwl/json from requests and opts,
        runs it, and deposits the outputs in outdir.

        Runner:
        opts.getopt("runner", default="cwl-runner")

        CWL (url):
        request["workflow_url"] == a url to a cwl file
        or
        request["workflow_attachment"] == input cwl text
        (written to a file and a url constructed for that file)

        JSON File:
        request["workflow_params"] == input json text (to be written to a file)

        :param request: A dictionary containing the cwl/json information.
        :param opts: contains the user's arguments;
                     specifically the runner and runner options
        :return: {"run_id": self.run_id, "state": state}
        """
        with open(os.path.join(self.workdir, "request.json"), "w") as f:
            json.dump(request, f)

        with open(os.path.join(self.workdir, "cwl.input.json"), "w") as inputtemp:
            json.dump(request["workflow_params"], inputtemp)

        workflow_url = cast(
            str, request.get("workflow_url")
        )  # Will always be local path to descriptor cwl, or url.

        output = open(os.path.join(self.workdir, "cwl.output.json"), "w")
        stderr = open(os.path.join(self.workdir, "stderr"), "w")

        runner = cast(str, opts.getopt("runner", default="cwl-runner"))
        extra = opts.getoptlist("extra")

        # replace any locally specified outdir with the default
        extra2 = []
        for e in extra:
            if not e.startswith("--outdir="):
                extra2.append(e)
        extra2.append("--outdir=" + self.outdir)

        # link the cwl and json into the tempdir/cwd
        if workflow_url.startswith("file://"):
            os.symlink(workflow_url[7:], os.path.join(tempdir, "wes_workflow.cwl"))
            workflow_url = os.path.join(tempdir, "wes_workflow.cwl")
        os.symlink(inputtemp.name, os.path.join(tempdir, "cwl.input.json"))
        jsonpath = os.path.join(tempdir, "cwl.input.json")

        # build args and run
        command_args: list[str] = [runner] + extra2 + [workflow_url, jsonpath]
        proc = subprocess.Popen(  # nosec B603
            command_args, stdout=output, stderr=stderr, close_fds=True, cwd=tempdir
        )
        output.close()
        stderr.close()
        with open(os.path.join(self.workdir, "pid"), "w") as pid:
            pid.write(str(proc.pid))

        return self.getstatus()

    def getstate(self) -> tuple[str, int]:
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
            with open(pid_file) as pid_fh:
                pid = int(pid_fh.read())
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

    def getstatus(self) -> dict[str, str]:
        """Report the current status."""
        state, exit_code = self.getstate()

        return {"run_id": self.run_id, "state": state}

    def getlog(self) -> dict[str, Any]:
        """Dump the log."""
        state, exit_code = self.getstate()

        with open(os.path.join(self.workdir, "request.json")) as f:
            request = json.load(f)

        with open(os.path.join(self.workdir, "stderr")) as f:
            stderr = f.read()

        outputobj = {}
        if state == "COMPLETE":
            output_path = os.path.join(self.workdir, "cwl.output.json")
            with open(output_path) as outputtemp:
                outputobj = json.load(outputtemp)

        return {
            "run_id": self.run_id,
            "request": request,
            "state": state,
            "run_log": {
                "cmd": [""],
                "start_time": "",
                "end_time": "",
                "stdout": "",
                "stderr": stderr,
                "exit_code": exit_code,
            },
            "task_logs": [],
            "outputs": outputobj,
        }

    def cancel(self) -> None:
        """Cancel the workflow, if possible."""


class CWLRunnerBackend(WESBackend):
    def GetServiceInfo(self) -> dict[str, Any]:
        """Report metadata about this WES endpoint."""
        runner = cast(str, self.getopt("runner", default="cwl-runner"))
        stdout, stderr = subprocess.Popen(  # nosec B603
            [runner, "--version"], stderr=subprocess.PIPE
        ).communicate()
        r = {
            "workflow_type_versions": {
                "CWL": {"workflow_type_version": ["v1.0", "v1.1", "v1.2"]}
            },
            "supported_wes_versions": ["0.3.0", "1.0.0"],
            "supported_filesystem_protocols": ["file", "http", "https"],
            "workflow_engine_versions": {"cwl-runner": str(stderr)},
            "system_state_counts": {},
            "tags": {},
        }
        return r

    def ListRuns(
        self, page_size: Any = None, page_token: Any = None, state_search: Any = None
    ) -> dict[str, Any]:
        """List the known workflow runs."""
        # FIXME #15 results don't page
        if not os.path.exists(os.path.join(os.getcwd(), "workflows")):
            return {"workflows": [], "next_page_token": ""}
        wf = []
        for entry in os.listdir(os.path.join(os.getcwd(), "workflows")):
            if os.path.isdir(os.path.join(os.getcwd(), "workflows", entry)):
                wf.append(Workflow(entry))

        workflows = [{"run_id": w.run_id, "state": w.getstate()[0]} for w in wf]  # NOQA
        return {"workflows": workflows, "next_page_token": ""}

    def RunWorkflow(self, **args: str) -> dict[str, str]:
        """Submit the workflow run request."""
        tempdir, body = self.collect_attachments(args)

        run_id = uuid.uuid4().hex
        job = Workflow(run_id)

        job.run(body, tempdir, self)
        return {"run_id": run_id}

    def GetRunLog(self, run_id: str) -> dict[str, Any]:
        """Get the log for a particular workflow run."""
        job = Workflow(run_id)
        return job.getlog()

    def CancelRun(self, run_id: str) -> dict[str, str]:
        """Cancel a submitted run."""
        job = Workflow(run_id)
        job.cancel()
        return {"run_id": run_id}

    def GetRunStatus(self, run_id: str) -> dict[str, str]:
        """Determine the status for a given run."""
        job = Workflow(run_id)
        return job.getstatus()


def create_backend(app: Any, opts: list[str]) -> CWLRunnerBackend:
    """Instantiate the cwl-runner backend."""
    return CWLRunnerBackend(opts)
