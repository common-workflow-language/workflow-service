"""Simple webapp for running cwl-runner."""

import copy
import json
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Generator
from typing import Any

import werkzeug.wrappers.response
import yaml
from flask import Flask, Response, redirect, request

app = Flask(__name__)

jobs_lock = threading.Lock()
jobs: list["Job"] = []


class Job(threading.Thread):
    """cwl-runner webapp."""

    def __init__(self, jobid: int, path: str, inputobj: bytes) -> None:
        """Initialize the execution Job."""
        super().__init__()
        self.jobid = jobid
        self.path = path
        self.inputobj = inputobj
        self.updatelock = threading.Lock()
        self.begin()

    def begin(self) -> None:
        """Star executing using cwl-runner."""
        loghandle, self.logname = tempfile.mkstemp()
        with self.updatelock:
            self.outdir = tempfile.mkdtemp()
            self.proc = subprocess.Popen(
                [shutil.which("cwl-runner") or "cwl-runner", self.path, "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=loghandle,
                close_fds=True,
                cwd=self.outdir,
            )
            self.status = {
                "id": "%sjobs/%i" % (request.url_root, self.jobid),
                "log": "%sjobs/%i/log" % (request.url_root, self.jobid),
                "run": self.path,
                "state": "Running",
                "input": json.loads(self.inputobj),
                "output": None,
            }

    def run(self) -> None:
        """Wait for execution to finish and report the result."""
        self.stdoutdata, self.stderrdata = self.proc.communicate(self.inputobj)
        if self.proc.returncode == 0:
            outobj = yaml.load(self.stdoutdata, Loader=yaml.FullLoader)
            with self.updatelock:
                self.status["state"] = "Success"
                self.status["output"] = outobj
        else:
            with self.updatelock:
                self.status["state"] = "Failed"

    def getstatus(self) -> dict[str, Any]:
        """Report the current status."""
        with self.updatelock:
            return self.status.copy()

    def cancel(self) -> None:
        """Cancel the excution thread, if any."""
        if self.status["state"] == "Running":
            self.proc.send_signal(signal.SIGQUIT)
            with self.updatelock:
                self.status["state"] = "Canceled"

    def pause(self) -> None:
        """Pause the execution thread, if any."""
        if self.status["state"] == "Running":
            self.proc.send_signal(signal.SIGTSTP)
            with self.updatelock:
                self.status["state"] = "Paused"

    def resume(self) -> None:
        """If paused, then resume the execution thread."""
        if self.status["state"] == "Paused":
            self.proc.send_signal(signal.SIGCONT)
            with self.updatelock:
                self.status["state"] = "Running"


@app.route("/run", methods=["POST"])
def runworkflow() -> werkzeug.wrappers.response.Response:
    """Accept a workflow exection request and run it."""
    path = request.args["wf"]
    with jobs_lock:
        jobid = len(jobs)
        job = Job(jobid, path, request.stream.read())
        job.start()
        jobs.append(job)
    return redirect("/jobs/%i" % jobid, code=303)


@app.route("/jobs/<int:jobid>", methods=["GET", "POST"])
def jobcontrol(jobid: int) -> tuple[str, int]:
    """Accept a job related action and report the result."""
    with jobs_lock:
        job = jobs[jobid]
    if request.method == "POST":
        action = request.args.get("action")
        if action:
            if action == "cancel":
                job.cancel()
            elif action == "pause":
                job.pause()
            elif action == "resume":
                job.resume()

    status = job.getstatus()
    return json.dumps(status, indent=4), 200


def logspooler(job: Job) -> Generator[str, None, None]:
    """Yield 4 kilobytes of log text at a time."""
    with open(job.logname) as f:
        while True:
            r = f.read(4096)
            if r:
                yield r
            else:
                with job.updatelock:
                    if job.status["state"] != "Running":
                        break
                time.sleep(1)


@app.route("/jobs/<int:jobid>/log", methods=["GET"])
def getlog(jobid: int) -> Response:
    """Dump the log."""
    with jobs_lock:
        job = jobs[jobid]
    return Response(logspooler(job))


@app.route("/jobs", methods=["GET"])
def getjobs() -> Response:
    """Report all known jobs."""
    with jobs_lock:
        jobscopy = copy.copy(jobs)

    def spool(jc: list[Job]) -> Generator[str, None, None]:
        yield "["
        first = True
        for j in jc:
            if first:
                yield json.dumps(j.getstatus(), indent=4)
                first = False
            else:
                yield ", " + json.dumps(j.getstatus(), indent=4)
        yield "]"

    return Response(spool(jobscopy))


if __name__ == "__main__":
    # app.debug = True
    app.run()
