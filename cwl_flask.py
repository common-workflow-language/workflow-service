from flask import Flask
from flask import request
import os
import subprocess
import tempfile
import json

app = Flask(__name__)

@app.route("/<path:workflow>", methods=['GET', 'POST', 'PUT'])
def handlecwl(workflow):
    try:
        if ".." in workflow:
            return "Path cannot contain ..", 400, {"Content-Type": "text/plain"}

        if request.method == 'PUT':
            (dr, fn) = os.path.split(workflow)
            dr = os.path.join("files", dr)
            if dr and not os.path.exists(dr):
                os.makedirs(dr)

            with open(os.path.join(dr, fn), "w") as f:
                f.write(request.stream.read())
            return "Ok"

        wf = os.path.join("files", workflow)

        if not os.path.exists(wf):
            return "Not found", 404, {"Content-Type": "text/plain"}

        if request.method == 'POST':
            with tempfile.NamedTemporaryFile() as f:
                f.write(request.stream.read())
                f.flush()
                outdir = tempfile.mkdtemp(dir=os.path.abspath("output"))
                proc = subprocess.Popen(["cwl-runner", os.path.abspath(wf), f.name],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        close_fds=True,
                                        cwd=outdir)
                (stdoutdata, stderrdata) = proc.communicate()
                proc.wait()
                if proc.returncode == 0:
                    return stdoutdata, 200, {"Content-Type": "application/json"}
                else:
                    return json.dumps({"cwl:error":stderrdata}), 400, {"Content-Type": "application/json"}
        else:
           with open(wf, "r") as f:
               return f.read(), 200, {"Content-Type": "application/x-common-workflow-language"}
    except Exception as e:
        print e
        return str(e), 500, {"Content-Type": "text/plain"}

@app.route("/")
def index():
    try:
        return json.dumps(["%s/%s" % (r[5:], f2) for r, _, f in os.walk("files") for f2 in f]), 200, {"Content-Type": "application/json"}
    except Exception as e:
        print e
        return str(e), 500, {"Content-Type": "text/plain"}

@app.route("/output")
def outindex():
    try:
        return json.dumps(["%s/%s" % (r[7:], f2) for r, _, f in os.walk("output") for f2 in f]), 200, {"Content-Type": "application/json"}
    except Exception as e:
        print e
        return str(e), 500, {"Content-Type": "text/plain"}

@app.route("/output/<path:fn>")
def outfile(fn):
    if ".." in fn:
        return "Path cannot contain ..", 400, {"Content-Type": "text/plain"}

    fn = os.path.join("output", fn)

    if not os.path.exists(fn):
        return "Not found", 404, {"Content-Type": "text/plain"}

    with open(fn, "r") as f:
        return f.read(), 200

if __name__ == "__main__":
    if not os.path.exists("files"):
        os.mkdir("files")
    if not os.path.exists("output"):
        os.mkdir("output")
    app.run()
