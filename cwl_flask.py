from flask import Flask
from flask import request, redirect
import os
import subprocess
import tempfile
import json
import yaml
import urlparse
import signal
import threading

app = Flask(__name__)

jobs_lock = threading.Lock()
jobs = []

class Job(threading.Thread):
    def __init__(self, jobid, path, inputobj):
        super(Job, self).__init__()
        self.jobid = jobid
        self.path = path
        self.inputobj = inputobj
        self.updatelock = threading.Lock()
        self.begin()

    def begin(self):
        with self.updatelock:
            self.outdir = tempfile.mkdtemp()
            self.proc = subprocess.Popen(["cwl-runner", self.path, "-"],
                                         stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE,
                                         close_fds=True,
                                         cwd=self.outdir)
            self.status = {
                "id": "%sjobs/%i" % (request.url_root, self.jobid),
                "run": self.path,
                "state": "Running",
                "input": self.inputobj,
                "output": None,
                "message": ""}

    def run(self):
        self.stdoutdata, self.stderrdata = self.proc.communicate(self.inputobj)
        if self.proc.returncode == 0:
            outobj = yaml.load(self.stdoutdata)
            with self.updatelock:
                self.status["state"] = "Success"
                self.status["output"] = outobj
        else:
            with self.updatelock:
                self.status["state"] = "Failed"
                self.status["message"] = self.stderrdata

    def getstatus(self):
        with self.updatelock:
            return self.status.copy()

    def cancel(self):
        if self.status["state"] == "Running":
            self.proc.send_signal(signal.SIGQUIT)
            with self.updatelock:
                self.status["state"] = "Canceled"

    def pause(self):
        if self.status["state"] == "Running":
            self.proc.send_signal(signal.SIGTSTP)
            with self.updatelock:
                self.status["state"] = "Paused"

    def resume(self):
        if self.status["state"] == "Paused":
            self.proc.send_signal(signal.SIGCONT)
            with self.updatelock:
                self.status["state"] = "Running"


@app.route("/run", methods=['POST'])
def runworkflow():
    path = request.args["wf"]
    with jobs_lock:
        jobid = len(jobs)
        job = Job(jobid, path, request.stream.read())
        job.start()
        jobs.append(job)
    return redirect("/jobs/%i" % jobid, code=303)


@app.route("/jobs/<int:jobid>", methods=['GET', 'POST'])
def jobcontrol(jobid):
    with jobs_lock:
        job = jobs[jobid]
    if request.method == 'POST':
        action = request.args.get("action")
        if action:
            if action == "cancel":
                job.cancel()
            elif action == "pause":
                job.pause()
            elif action == "resume":
                job.resume()

    status = job.getstatus()
    return json.dumps(status, indent=4), 200, ""


if __name__ == "__main__":
    app.debug = True
    app.run()
