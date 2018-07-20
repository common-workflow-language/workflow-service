from __future__ import print_function
import json
import os
import subprocess
import tempfile
import time
import logging
import urllib
import uuid

import connexion
from multiprocessing import Process
from werkzeug.utils import secure_filename
from wes_service.util import WESBackend

logging.basicConfig(level=logging.INFO)


class ToilWorkflow(object):
    def __init__(self, workflow_id):
        super(ToilWorkflow, self).__init__()
        self.workflow_id = workflow_id

        self.workdir = os.path.join(os.getcwd(), 'workflows', self.workflow_id)
        self.outdir = os.path.join(self.workdir, 'outdir')
        if not os.path.exists(self.outdir):
            os.makedirs(self.outdir)

        self.outfile = os.path.join(self.workdir, 'stdout')
        self.errfile = os.path.join(self.workdir, 'stderr')
        self.starttime = os.path.join(self.workdir, 'starttime')
        self.endtime = os.path.join(self.workdir, 'endtime')
        self.pidfile = os.path.join(self.workdir, 'pid')
        self.cmdfile = os.path.join(self.workdir, 'cmd')
        self.request_json = os.path.join(self.workdir, 'request.json')
        self.output_json = os.path.join(self.workdir, "output.json")
        self.input_wf_filename = os.path.join(self.workdir, "workflow.cwl")
        self.input_json = os.path.join(self.workdir, "input.json")

    def write_workflow(self, request, opts, wftype='cwl'):
        """Writes a cwl, wdl, or python file as appropriate from the request dictionary."""
        self.input_wf_filename = os.path.join(self.workdir, 'workflow.' + wftype)

        if request.get("workflow_descriptor"):
            workflow_descriptor = request.get('workflow_descriptor')
            with open(self.input_wf_filename, "w") as f:
                f.write(workflow_descriptor)
            workflow_url = urllib.pathname2url(self.input_wf_filename)
        else:
            workflow_url = request.get("workflow_url")

        extra = opts.getoptlist("extra")
        if wftype == 'cwl':
            command_args = ['toil-cwl-runner'] + extra + [workflow_url, self.input_json]
        elif wftype == 'wdl':
            command_args = ['toil-wdl-runner'] + extra + [workflow_url, self.input_json]
        elif wftype == 'py':
            command_args = ['python'] + extra + [workflow_url]
        else:
            raise RuntimeError('workflow_type is not "cwl", "wdl", or "py": ' + str(wftype))

        return command_args

    def write_json(self, request_dict):
        input_json = os.path.join(self.workdir, 'input.json')
        with open(input_json, 'w') as inputtemp:
            json.dump(request_dict['workflow_params'], inputtemp)
        return input_json

    def call_cmd(self, cmd):
        """
        Calls a command with Popen.
        Writes stdout, stderr, and the command to separate files.

        :param cmd: A string or array of strings.
        :return: The pid of the command.
        """
        with open(self.cmdfile, 'w') as f:
            f.write(str(cmd))
        stdout = open(self.outfile, 'w')
        stderr = open(self.errfile, 'w')
        logging.info('Calling: ' + ' '.join(cmd))
        process = subprocess.Popen(cmd,
                                   stdout=stdout,
                                   stderr=stderr,
                                   close_fds=True,
                                   cwd=self.outdir)
        stdout.close()
        stderr.close()
        return process.pid

    def cancel(self):
        pass

    def fetch(self, filename):
        if os.path.exists(filename):
            with open(filename, "r") as f:
                return f.read()
        return ''

    def getlog(self):
        state, exit_code = self.getstate()

        with open(self.request_json, "r") as f:
            request = json.load(f)

        stderr = self.fetch(self.errfile)
        starttime = self.fetch(self.starttime)
        endtime = self.fetch(self.endtime)
        cmd = self.fetch(self.cmdfile)


        outputobj = {}
        if state == "COMPLETE":
            with open(self.output_json, "r") as outputtemp:
                outputobj = json.load(outputtemp)

        return {
            "workflow_id": self.workflow_id,
            "request": request,
            "state": state,
            "workflow_log": {
                "cmd": cmd,  # array?
                "start_time": starttime,
                "end_time": endtime,
                "stdout": "",
                "stderr": stderr,
                "exit_code": exit_code
            },
            "task_logs": [],
            "outputs": outputobj
        }

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
        wftype = request['workflow_type'].lower().strip()
        version = request['workflow_type_version']

        if version != 'v1.0' and wftype in ('cwl', 'wdl'):
            raise RuntimeError('workflow_type "cwl", "wdl" requires '
                               '"workflow_type_version" to be "v1.0": ' + str(version))
        if version != '2.7' and wftype == 'py':
            raise RuntimeError('workflow_type "py" requires '
                               '"workflow_type_version" to be "2.7": ' + str(version))

        logging.info('Beginning Toil Workflow ID: ' + str(self.workflow_id))

        with open(self.starttime, 'w') as f:
            f.write(str(time.time()))
        with open(self.request_json, 'w') as f:
            json.dump(request, f)
        with open(self.input_json, "w") as inputtemp:
            json.dump(request["workflow_params"], inputtemp)

        command_args = self.write_workflow(request, opts, wftype=wftype)
        pid = self.call_cmd(command_args)

        with open(self.endtime, 'w') as f:
            f.write(str(time.time()))
        with open(self.pidfile, 'w') as f:
            f.write(str(pid))

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

        if os.path.exists(exitcode_file):
            with open(exitcode_file) as f:
                exit_code = int(f.read())
        elif os.path.exists(self.pidfile):
            with open(self.pidfile, "r") as pid:
                pid = int(pid.read())
            try:
                (_pid, exit_status) = os.waitpid(pid, os.WNOHANG)
                if _pid != 0:
                    exit_code = exit_status >> 8
                    with open(exitcode_file, "w") as f:
                        f.write(str(exit_code))
                    os.unlink(self.pidfile)
            except OSError:
                os.unlink(self.pidfile)
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


class ToilBackend(WESBackend):
    processes = {}

    def GetServiceInfo(self):
        return {
            'workflow_type_versions': {
                'CWL': {'workflow_type_version': ['v1.0']},
                'WDL': {'workflow_type_version': ['v1.0']},
                'py': {'workflow_type_version': ['2.7']}
            },
            'supported_wes_versions': '0.3.0',
            'supported_filesystem_protocols': ['file', 'http', 'https'],
            'engine_versions': ['3.16.0'],
            'system_state_counts': {},
            'key_values': {}
        }

    def ListWorkflows(self):
        # FIXME #15 results don't page
        wf = []
        for l in os.listdir(os.path.join(os.getcwd(), "workflows")):
            if os.path.isdir(os.path.join(os.getcwd(), "workflows", l)):
                wf.append(ToilWorkflow(l))

        workflows = [{"workflow_id": w.workflow_id, "state": w.getstate()[0]} for w in wf]  # NOQA
        return {
            "workflows": workflows,
            "next_page_token": ""
        }

    def RunWorkflow(self):
        tempdir = tempfile.mkdtemp()
        body = {}
        for k, ls in connexion.request.files.iterlists():
            for v in ls:
                if k == "workflow_descriptor":
                    filename = secure_filename(v.filename)
                    v.save(os.path.join(tempdir, filename))
                elif k in ("workflow_params", "tags", "workflow_engine_parameters"):
                    body[k] = json.loads(v.read())
                else:
                    body[k] = v.read()

        if body['workflow_type'] != "CWL" or \
                body['workflow_type_version'] != "v1.0":
            return

        body["workflow_url"] = "file:///%s/%s" % (tempdir, body["workflow_url"])
        index = body["workflow_url"].find("http")
        if index > 0:
            body["workflow_url"] = body["workflow_url"][index:]

        workflow_id = uuid.uuid4().hex
        job = ToilWorkflow(workflow_id)
        p = Process(target=job.run, args=(body, self))
        p.start()
        self.processes[workflow_id] = p
        return {"workflow_id": workflow_id}

    def GetWorkflowLog(self, workflow_id):
        job = ToilWorkflow(workflow_id)
        return job.getlog()

    def CancelJob(self, workflow_id):
        # should this block with `p.is_alive()`?
        if workflow_id in self.processes:
            self.processes[workflow_id].terminate()
        return {'workflow_id': workflow_id}

    def GetWorkflowStatus(self, workflow_id):
        job = ToilWorkflow(workflow_id)
        return job.getstatus()


def create_backend(app, opts):
    return ToilBackend(opts)
