import threading
import tempfile
import subprocess

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
            self.inputtemp = tempfile.NamedTemporaryFile()
            json.dump(self.inputtemp, self.inputobj)
            self.proc = subprocess.Popen(["cwl-runner", self.path, self.inputtemp.name],
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


def GetWorkflowStatus(workflow_ID):
    return {"workflow_ID": workflow_ID}

def GetWorkflowLog():
    pass

def CancelJob():
    pass

def RunWorkflow(body):
    with jobs_lock:
        jobid = len(jobs)
        job = Job(jobid, body["workflow_url"], body["inputs"])
        job.start()
        jobs.append(job)
    return {"workflow_ID": str(jobid)}
