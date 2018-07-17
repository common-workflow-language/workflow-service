from flask import Flask, Response, request, redirect
import subprocess
import tempfile
import json
import yaml
import signal
import threading
import time
import copy

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
        loghandle, self.logname = tempfile.mkstemp()
        with self.updatelock:
            self.outdir = tempfile.mkdtemp()
            self.proc = subprocess.Popen(["cwl-runner", self.path, "-"],
                                         stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE,
                                         stderr=loghandle,
                                         close_fds=True,
                                         cwd=self.outdir)
            self.status = {
                "id": "%sjobs/%i" % (request.url_root, self.jobid),
                "log": "%sjobs/%i/log" % (request.url_root, self.jobid),
                "run": self.path,
                "state": "Running",
                "input": json.loads(self.inputobj),
                "output": None}

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


def logspooler(job):
    with open(job.logname, "r") as f:
        while True:
            r = f.read(4096)
            if r:
                yield r
            else:
                with job.updatelock:
                    if job.status["state"] != "Running":
                        break
                time.sleep(1)


@app.route("/jobs/<int:jobid>/log", methods=['GET'])
def getlog(jobid):
    with jobs_lock:
        job = jobs[jobid]
    return Response(logspooler(job))


@app.route("/jobs", methods=['GET'])
def getjobs():
    with jobs_lock:
        jobscopy = copy.copy(jobs)

    def spool(jc):
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
