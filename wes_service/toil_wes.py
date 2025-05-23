"""Toil backed for the WES service."""

import errno
import json
import logging
import os
import shutil
import subprocess  # nosec B404
import time
import uuid
from multiprocessing import Process
from typing import Any, Optional, Union, cast

from wes_service.util import WESBackend

logging.basicConfig(level=logging.INFO)


class ToilWorkflow:
    def __init__(self, run_id: str) -> None:
        """
        Represents a toil workflow.

        :param run_id: A uuid string.  Used to name the folder that contains
            all of the files containing this particular workflow instance's information.
        """
        super().__init__()
        self.run_id = run_id

        self.workdir = os.path.join(os.getcwd(), "workflows", self.run_id)
        self.outdir = os.path.join(self.workdir, "outdir")
        if not os.path.exists(self.outdir):
            os.makedirs(self.outdir)

        self.outfile = os.path.join(self.workdir, "stdout")
        self.errfile = os.path.join(self.workdir, "stderr")
        self.starttime = os.path.join(self.workdir, "starttime")
        self.endtime = os.path.join(self.workdir, "endtime")
        self.pidfile = os.path.join(self.workdir, "pid")
        self.statcompletefile = os.path.join(self.workdir, "status_completed")
        self.staterrorfile = os.path.join(self.workdir, "status_error")
        self.cmdfile = os.path.join(self.workdir, "cmd")
        self.jobstorefile = os.path.join(self.workdir, "jobstore")
        self.request_json = os.path.join(self.workdir, "request.json")
        self.input_json = os.path.join(self.workdir, "wes_input.json")
        self.jobstore_default = "file:" + os.path.join(self.workdir, "toiljobstore")
        self.jobstore: Optional[str] = None

    def sort_toil_options(self, extra: list[str]) -> list[str]:
        """
        Sort the options in a toil-aware manner.

        Stores the jobstore location for later use.
        """
        # determine jobstore and set a new default if the user did not set one
        cloud = False
        extra2 = []
        for e in extra:
            if e.startswith("--jobStore="):
                self.jobstore = e[11:]
                if self.jobstore.startswith(("aws", "google", "azure")):
                    cloud = True
            if not e.startswith(("--outdir=", "-o=")):
                extra2.append(e)
        if not cloud:
            extra2.append("--outdir=" + self.outdir)
        if not self.jobstore:
            extra2.append("--jobStore=" + self.jobstore_default)
            self.jobstore = self.jobstore_default

        # store the jobstore location
        with open(self.jobstorefile, "w") as f:
            f.write(self.jobstore)

        return extra2

    def write_workflow(
        self, request: dict[str, Any], opts: WESBackend, cwd: str, wftype: str = "cwl"
    ) -> list[str]:
        """Writes a cwl, wdl, or python file as appropriate from the request dictionary."""

        workflow_url = cast(str, request.get("workflow_url"))

        # link the cwl and json into the cwd
        if workflow_url.startswith("file://"):
            try:
                os.link(workflow_url[7:], os.path.join(cwd, "wes_workflow." + wftype))
            except OSError:
                os.symlink(
                    workflow_url[7:], os.path.join(cwd, "wes_workflow." + wftype)
                )
            workflow_url = os.path.join(cwd, "wes_workflow." + wftype)
        try:
            os.link(self.input_json, os.path.join(cwd, "wes_input.json"))
        except OSError:
            os.symlink(self.input_json, os.path.join(cwd, "wes_input.json"))
        self.input_json = os.path.join(cwd, "wes_input.json")

        extra_options = self.sort_toil_options(opts.getoptlist("extra"))
        if wftype == "cwl":
            command_args = (
                ["toil-cwl-runner"] + extra_options + [workflow_url, self.input_json]
            )
        elif wftype == "wdl":
            command_args = (
                ["toil-wdl-runner"] + extra_options + [workflow_url, self.input_json]
            )
        elif wftype == "py":
            command_args = ["python"] + extra_options + [workflow_url]
        else:
            raise RuntimeError(
                'workflow_type is not "cwl", "wdl", or "py": ' + str(wftype)
            )

        return command_args

    def write_json(self, request_dict: dict[str, Any]) -> str:
        """Save the workflow_params to the input.json file and also return it."""
        input_json = os.path.join(self.workdir, "input.json")
        with open(input_json, "w") as f:
            json.dump(request_dict["workflow_params"], f)
        return input_json

    def call_cmd(self, cmd: Union[list[str], str], cwd: str) -> int:
        """
        Calls a command with Popen.
        Writes stdout, stderr, and the command to separate files.

        :param cmd: A string or array of strings.
        :param tempdir:
        :return: The pid of the command.
        """
        with open(self.cmdfile, "w") as f:
            f.write(str(cmd))
        stdout = open(self.outfile, "w")
        stderr = open(self.errfile, "w")
        logging.info(
            "Calling: %s, with outfile: %s and errfile: %s",
            (" ".join(cmd)),
            self.outfile,
            self.errfile,
        )
        process = subprocess.Popen(  # nosec B603
            cmd, stdout=stdout, stderr=stderr, close_fds=True, cwd=cwd
        )
        stdout.close()
        stderr.close()

        return process.pid

    def cancel(self) -> None:
        """Cancel the run (currently a no-op for Toil)."""

    def fetch(self, filename: str) -> str:
        """Retrieve a files contents, if it exists."""
        if os.path.exists(filename):
            with open(filename) as f:
                return f.read()
        return ""

    def getlog(self) -> dict[str, Any]:
        """Dump the log."""
        state, exit_code = self.getstate()

        with open(self.request_json) as f:
            request = json.load(f)

        with open(self.jobstorefile) as f:
            self.jobstore = f.read()

        stderr = self.fetch(self.errfile)
        starttime = self.fetch(self.starttime)
        endtime = self.fetch(self.endtime)
        cmd = [self.fetch(self.cmdfile)]

        outputobj = {}
        if state == "COMPLETE":
            # only tested locally
            if self.jobstore.startswith("file:"):
                for f2 in os.listdir(self.outdir):
                    if f2.startswith("out_tmpdir"):
                        shutil.rmtree(os.path.join(self.outdir, f2))
                for f3 in os.listdir(self.outdir):
                    outputobj[f3] = {
                        "location": os.path.join(self.outdir, f3),
                        "size": os.stat(os.path.join(self.outdir, f3)).st_size,
                        "class": "File",
                    }

        return {
            "run_id": self.run_id,
            "request": request,
            "state": state,
            "run_log": {
                "cmd": cmd,
                "start_time": starttime,
                "end_time": endtime,
                "stdout": "",
                "stderr": stderr,
                "exit_code": exit_code,
            },
            "task_logs": [],
            "outputs": outputobj,
        }

    def run(
        self, request: dict[str, Any], tempdir: str, opts: WESBackend
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
        :param tempdir: Folder where input files have been staged and the cwd to run at.
        :param opts: contains the user's arguments;
                                                 specifically the runner and runner options
        :return: {"run_id": self.run_id, "state": state}
        """
        wftype = request["workflow_type"].lower().strip()
        version = request["workflow_type_version"]

        if wftype == "cwl" and version not in ("v1.0", "v1.1", "v1.2"):
            raise RuntimeError(
                'workflow_type "cwl" requires '
                '"workflow_type_version" to be "v1.[012]": ' + str(version)
            )
        if version != "2.7" and wftype == "py":
            raise RuntimeError(
                'workflow_type "py" requires '
                '"workflow_type_version" to be "2.7": ' + str(version)
            )

        logging.info("Beginning Toil Workflow ID: " + str(self.run_id))

        with open(self.starttime, "w") as f:
            f.write(str(time.time()))
        with open(self.request_json, "w") as f:
            json.dump(request, f)
        with open(self.input_json, "w") as inputtemp:
            json.dump(request["workflow_params"], inputtemp)

        command_args = self.write_workflow(request, opts, tempdir, wftype=wftype)
        pid = self.call_cmd(command_args, tempdir)

        with open(self.endtime, "w") as f:
            f.write(str(time.time()))
        with open(self.pidfile, "w") as f:
            f.write(str(pid))

        return self.getstatus()

    def getstate(self) -> tuple[str, int]:
        """
        Returns QUEUED,          -1
                INITIALIZING,    -1
                RUNNING,         -1
                COMPLETE,         0
                or
                EXECUTOR_ERROR, 255
        """
        # the jobstore never existed
        if not os.path.exists(self.jobstorefile):
            logging.info("Workflow " + self.run_id + ": QUEUED")
            return "QUEUED", -1

        # completed earlier
        if os.path.exists(self.statcompletefile):
            logging.info("Workflow " + self.run_id + ": COMPLETE")
            return "COMPLETE", 0

        # errored earlier
        if os.path.exists(self.staterrorfile):
            logging.info("Workflow " + self.run_id + ": EXECUTOR_ERROR")
            return "EXECUTOR_ERROR", 255

        # the workflow is staged but has not run yet
        if not os.path.exists(self.errfile):
            logging.info("Workflow " + self.run_id + ": INITIALIZING")
            return "INITIALIZING", -1

        completed = False
        with open(self.errfile) as f:
            for line in f:
                if "Traceback (most recent call last)" in line:
                    logging.info("Workflow " + self.run_id + ": EXECUTOR_ERROR")
                    open(self.staterrorfile, "a").close()
                    return "EXECUTOR_ERROR", 255

        # get the jobstore
        with open(self.jobstorefile, "r") as f:
            jobstore = f.read().rstrip()
        if (
            subprocess.run(  # nosec B603
                [
                    shutil.which("toil") or "toil",
                    "status",
                    "--failIfNotComplete",
                    jobstore,
                ]
            ).returncode
            == 0
        ):
            # Get the PID of the running process
            with open(self.pidfile, "r") as f:
                pid = int(f.read())
            try:
                os.kill(pid, 0)
            except OSError as e:
                if e.errno == errno.ESRCH:
                    # Process is no longer running, could be completed
                    completed = True
                    # Reap zombie child processes in a non-blocking manner
                    # os.WNOHANG still raises an error if no child processes exist
                    try:
                        os.waitpid(pid, os.WNOHANG)
                    except OSError as e:
                        if e.errno != errno.ECHILD:
                            raise
                else:
                    raise
            # If no exception, process is still running
            # We can't rely on toil status as the process may not have created the jobstore yet
        if completed:
            logging.info("Workflow " + self.run_id + ": COMPLETE")
            open(self.statcompletefile, "a").close()
            return "COMPLETE", 0

        logging.info("Workflow " + self.run_id + ": RUNNING")
        return "RUNNING", -1

    def getstatus(self) -> dict[str, Any]:
        """Report the current status."""
        state, exit_code = self.getstate()

        return {"run_id": self.run_id, "state": state}


class ToilBackend(WESBackend):
    processes: dict[str, Process] = {}

    def GetServiceInfo(self) -> dict[str, Any]:
        """Report about this WES endpoint."""
        return {
            "workflow_type_versions": {
                "CWL": {"workflow_type_version": ["v1.0", "v1.1", "v1.2"]},
                "WDL": {"workflow_type_version": ["draft-2"]},
                "PY": {"workflow_type_version": ["2.7"]},
            },
            "supported_wes_versions": ["0.3.0", "1.0.0"],
            "supported_filesystem_protocols": ["file", "http", "https"],
            "workflow_engine_versions": ["3.16.0"],
            "system_state_counts": {},
            "key_values": {},
        }

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
                wf.append(ToilWorkflow(entry))

        workflows = [{"run_id": w.run_id, "state": w.getstate()[0]} for w in wf]  # NOQA
        return {"workflows": workflows, "next_page_token": ""}

    def RunWorkflow(self, **args: str) -> dict[str, str]:
        """Submit the workflow run request."""
        tempdir, body = self.collect_attachments(args)

        run_id = uuid.uuid4().hex
        job = ToilWorkflow(run_id)
        p = Process(target=job.run, args=(body, tempdir, self))
        p.start()
        self.processes[run_id] = p
        return {"run_id": run_id}

    def GetRunLog(self, run_id: str) -> dict[str, Any]:
        """Get the log for a particular workflow run."""
        job = ToilWorkflow(run_id)
        return job.getlog()

    def CancelRun(self, run_id: str) -> dict[str, str]:
        """Cancel a submitted run."""
        # should this block with `p.is_alive()`?
        if run_id in self.processes:
            self.processes[run_id].terminate()
        return {"run_id": run_id}

    def GetRunStatus(self, run_id: str) -> dict[str, str]:
        """Determine the status for a given run."""
        job = ToilWorkflow(run_id)
        return job.getstatus()


def create_backend(app: Any, opts: list[str]) -> ToilBackend:
    """Instantiate a ToilBackend."""
    return ToilBackend(opts)
