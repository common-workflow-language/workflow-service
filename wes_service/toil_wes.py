from __future__ import print_function
import json
import os
import subprocess
import time
import logging
import uuid

from multiprocessing import Process
from wes_service.util import WESBackend

logging.basicConfig(level=logging.INFO)


class ToilWorkflow(object):
    def __init__(self, run_id):
        super(ToilWorkflow, self).__init__()
        self.run_id = run_id

        self.workdir = os.path.join(os.getcwd(), 'workflows', self.run_id)
        self.outdir = os.path.join(self.workdir, 'outdir')
        if not os.path.exists(self.outdir):
            os.makedirs(self.outdir)

        self.outfile = os.path.join(self.workdir, 'stdout')
        self.errfile = os.path.join(self.workdir, 'stderr')
        self.starttime = os.path.join(self.workdir, 'starttime')
        self.endtime = os.path.join(self.workdir, 'endtime')
        self.pidfile = os.path.join(self.workdir, 'pid')
        self.cmdfile = os.path.join(self.workdir, 'cmd')
        self.jobstorefile = os.path.join(self.workdir, 'jobstore')
        self.request_json = os.path.join(self.workdir, 'request.json')
        self.output_json = os.path.join(self.workdir, "output.json")
        self.input_wf_filename = os.path.join(self.workdir, "wes_workflow.cwl")
        self.input_json = os.path.join(self.workdir, "wes_input.json")
        self.jobstore_default = os.path.join(self.workdir, 'file:toiljobstore')
        self.jobstore = None

    def sort_toil_options(self, extra):
        # determine jobstore and set a new default if the user did not set one
        cloud = False
        for e in extra:
            if e.startswith('--jobStore='):
                self.jobstore = e[11:]
                if self.jobstore.startswith(('aws', 'google', 'azure')):
                    cloud = True
            if e.startswith(('--outdir=', '-o=')):
                extra.remove(e)
        if not cloud:
            extra.append('--outdir=' + self.outdir)
        if not self.jobstore:
            extra.append('--jobStore=' + self.jobstore_default)
            self.jobstore = self.jobstore_default

        # store the jobstore location
        with open(self.jobstorefile, 'w') as f:
            f.write(self.jobstore)

        return extra

    def write_workflow(self, request, opts, cwd, wftype='cwl'):
        """Writes a cwl, wdl, or python file as appropriate from the request dictionary."""
        self.input_wf_filename = os.path.join(self.workdir, 'workflow.' + wftype)

        workflow_url = request.get("workflow_url")

        # link the cwl and json into the cwd
        if workflow_url.startswith('file://'):
            os.link(workflow_url[7:], os.path.join(cwd, "wes_workflow.cwl"))
            workflow_url = os.path.join(cwd, "wes_workflow.cwl")
        os.link(self.input_json, os.path.join(cwd, "wes_input.json"))
        self.input_json = os.path.join(cwd, "wes_input.json")

        extra_options = self.sort_toil_options(opts.getoptlist("extra"))
        if wftype == 'cwl':
            command_args = ['toil-cwl-runner'] + extra_options + [workflow_url, self.input_json]
        elif wftype == 'wdl':
            command_args = ['toil-wdl-runner'] + extra_options + [workflow_url, self.input_json]
        elif wftype == 'py':
            command_args = ['python'] + extra_options + [self.input_wf_filename]
        else:
            raise RuntimeError('workflow_type is not "cwl", "wdl", or "py": ' + str(wftype))

        return command_args

    def write_json(self, request_dict):
        input_json = os.path.join(self.workdir, 'input.json')
        with open(input_json, 'w') as f:
            json.dump(request_dict['workflow_params'], f)
        return input_json

    def call_cmd(self, cmd, cwd):
        """
        Calls a command with Popen.
        Writes stdout, stderr, and the command to separate files.

        :param cmd: A string or array of strings.
        :param tempdir:
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
                                   cwd=cwd)
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
        cmd = [self.fetch(self.cmdfile)]

        outputobj = {}
        if state == "COMPLETE":
            with open(self.output_json, "r") as f:
                outputobj = json.load(f)

        return {
            "run_id": self.run_id,
            "request": request,
            "state": state,
            "workflow_log": {
                "cmd": cmd,
                "start_time": starttime,
                "end_time": endtime,
                "stdout": "",
                "stderr": stderr,
                "exit_code": exit_code
            },
            "task_logs": [],
            "outputs": outputobj
        }

    def run(self, request, tempdir, opts):
        """
        Constructs a command to run a cwl/json from requests and opts,
        runs it, and deposits the outputs in outdir.

        Runner:
        opts.getopt("runner", default="cwl-runner")

        CWL (url):
        request["workflow_url"] == a url to a cwl file
        or
        request["workflow_attachment"] == input cwl text (written to a file and a url constructed for that file)

        JSON File:
        request["workflow_params"] == input json text (to be written to a file)

        :param dict request: A dictionary containing the cwl/json information.
        :param str tempdir: Folder where input files have been staged and the cwd to run at.
        :param wes_service.util.WESBackend opts: contains the user's arguments;
                                                 specifically the runner and runner options
        :return: {"run_id": self.run_id, "state": state}
        """
        wftype = request['workflow_type'].lower().strip()
        version = request['workflow_type_version']

        if version != 'v1.0' and wftype in ('cwl', 'wdl'):
            raise RuntimeError('workflow_type "cwl", "wdl" requires '
                               '"workflow_type_version" to be "v1.0": ' + str(version))
        if version != '2.7' and wftype == 'py':
            raise RuntimeError('workflow_type "py" requires '
                               '"workflow_type_version" to be "2.7": ' + str(version))

        logging.info('Beginning Toil Workflow ID: ' + str(self.run_id))

        with open(self.starttime, 'w') as f:
            f.write(str(time.time()))
        with open(self.request_json, 'w') as f:
            json.dump(request, f)
        with open(self.input_json, "w") as inputtemp:
            json.dump(request["workflow_params"], inputtemp)

        command_args = self.write_workflow(request, opts, tempdir, wftype=wftype)
        pid = self.call_cmd(command_args, tempdir)

        with open(self.endtime, 'w') as f:
            f.write(str(time.time()))
        with open(self.pidfile, 'w') as f:
            f.write(str(pid))

        return self.getstatus()

    def getstate(self):
        """
        Returns INITIALIZING, -1
                RUNNING, -1
                COMPLETE, 0
                or
                EXECUTOR_ERROR, 255
        """
        state = "RUNNING"
        exit_code = -1

        with open(self.jobstorefile, 'r') as f:
            self.jobstore = f.read()

        logs = subprocess.check_output(['toil', 'status', 'file:' + self.jobstore, '--printLogs'])
        if 'ERROR:toil.worker:Exiting' in logs:
            state = "EXECUTOR_ERROR"
            exit_code = 255
        elif 'Root job is absent.  The workflow may have completed successfully.' in logs:
            state = "COMPLETE"
            exit_code = 0
        elif 'No job store found.' in logs:
            state = "INITIALIZING"
            exit_code = -1

        return state, exit_code

    def getstatus(self):
        state, exit_code = self.getstate()

        return {
            "run_id": self.run_id,
            "state": state
        }


class ToilBackend(WESBackend):
    processes = {}

    def GetServiceInfo(self):
        return {
            'workflow_type_versions': {
                'CWL': {'workflow_type_version': ['v1.0']},
                'WDL': {'workflow_type_version': ['v1.0']},
                'PY': {'workflow_type_version': ['2.7']}
            },
            'supported_wes_versions': '0.3.0',
            'supported_filesystem_protocols': ['file', 'http', 'https'],
            'engine_versions': ['3.16.0'],
            'system_state_counts': {},
            'key_values': {}
        }

    def ListRuns(self):
        # FIXME #15 results don't page
        wf = []
        for l in os.listdir(os.path.join(os.getcwd(), "workflows")):
            if os.path.isdir(os.path.join(os.getcwd(), "workflows", l)):
                wf.append(ToilWorkflow(l))

        workflows = [{"run_id": w.run_id, "state": w.getstate()[0]} for w in wf]  # NOQA
        return {
            "workflows": workflows,
            "next_page_token": ""
        }

    def RunWorkflow(self):
        tempdir, body = self.collect_attachments()

        run_id = uuid.uuid4().hex
        job = ToilWorkflow(run_id)
        p = Process(target=job.run, args=(body, tempdir, self))
        p.start()
        self.processes[run_id] = p
        return {'run_id': run_id}

    def GetRunLog(self, run_id):
        job = ToilWorkflow(run_id)
        return job.getlog()

    def CancelRun(self, run_id):
        # should this block with `p.is_alive()`?
        if run_id in self.processes:
            self.processes[run_id].terminate()
        return {'run_id': run_id}

    def GetRunStatus(self, run_id):
        job = ToilWorkflow(run_id)
        return job.getstatus()


def create_backend(app, opts):
    return ToilBackend(opts)
