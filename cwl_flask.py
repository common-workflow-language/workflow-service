from flask import Flask
from flask import request
import os
import subprocess
import tempfile

app = Flask(__name__)

@app.route("/<workflow>", methods=['GET', 'POST', 'PUT'])
def runjob(workflow):
    try:
        if request.method == 'PUT':
            with open(os.path.join("files", workflow), "w") as f:
                f.write(request.stream.read())
            return "Ok"

        wf = os.path.join("files", workflow)

        if not os.path.exists(wf):
            return "Not found", 404

        if request.method == 'POST':
            with tempfile.NamedTemporaryFile() as f:
                f.write(request.stream.read())
                f.flush()
                outdir = tempfile.mkdtemp()
                proc = subprocess.Popen(["cwl-runner", os.path.abspath(wf), f.name],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        close_fds=True,
                                        cwd=outdir)
                (stdoutdata, stderrdata) = proc.communicate()
                proc.wait()
                if proc.returncode == 0:
                    return stdoutdata
                else:
                    return stderrdata, 400
        else:
           with open(wf, "r") as f:
               return f.read()
    except Exception as e:
        return str(e), 500

if __name__ == "__main__":
    if not os.path.exists("files"):
        os.mkdir("files")
    app.run()
