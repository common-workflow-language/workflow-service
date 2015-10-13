import cwltool
from flask import Flask
from flask import request
import os
import StringIO

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
            out = StringIO.StringIO()
            err = StringIO.StringIO()
            if cwltool.main(args=[wf, "-"],
                            stdin=request.stream.read(),
                            stdout=out,
                            stderr=err) != 0:
                return err.getvalue(), 400
            else:
                return out.getvalue()

        else:
           with open(wf, "r") as f:
               return f.read()
    except Exception as e:
        return str(e), 500

if __name__ == "__main__":
    if not os.path.exists("files"):
        os.mkdir("files")
    app.run()
