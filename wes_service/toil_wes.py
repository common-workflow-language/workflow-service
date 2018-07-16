import os
import json
import uuid
import subprocess
import urllib
from multiprocessing import Process
import logging

from wes_service.util import WESBackend
from wes_service.cwl_runner import Workflow

logging.basicConfig(level=logging.INFO)


class ToilWorkflow(Workflow):
    def __init__(self, workflow_id):
        super(ToilWorkflow, self).__init__()
        self.workflow_id = workflow_id

        self.workdir = os.path.join(os.getcwd(), 'workflows', self.workflow_id)
        self.outdir = os.path.join(self.workdir, 'outdir')
        os.makedirs(self.outdir)

        self.outfile = os.path.join(self.workdir, 'stdout')
        self.errfile = os.path.join(self.workdir, 'stderr')
        self.pidfile = os.path.join(self.workdir, 'pid')
        self.cmdfile = os.path.join(self.workdir, 'cmd')
        self.request_json = os.path.join(self.workdir, 'request.json')

    def write_workflow(self, request_dict, wftype='cwl'):
        """Writes a cwl or wdl file as appropriate from the request dictionary."""
        wf_filename = os.path.join(self.workdir, 'workflow.' + wftype)
        if request_dict.get('workflow_descriptor'):
            workflow_descriptor = request_dict.get('workflow_descriptor')
            with open(wf_filename, 'w') as f:
                # FIXME #14 workflow_descriptor isn't defined
                f.write(workflow_descriptor)
            workflow_url = urllib.pathname2url(wf_filename)
        else:
            workflow_url = request_dict.get('workflow_url')
        return workflow_url

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
            f.write(cmd)
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

    def run(self, request_dict, opts):
        logging.info('Beginning Toil Workflow ID: ' + str(self.workflow_id))
        wftype = request_dict['workflow_type'].lower()

        with open(self.request_json, 'w') as f:
            json.dump(request_dict, f)

        # write cwl/wdl, as appropriate
        input_wf = self.write_workflow(request_dict, wftype=wftype)
        input_json = self.write_json(request_dict)

        # call the workflow + json with the appropriate toil method
        cmd = ['toil-' + wftype + '-runner'] + opts.getoptlist('extra') + [input_wf, input_json]
        pid = self.call_cmd(cmd)

        with open(self.pidfile, 'w') as f:
            f.write(str(pid))

        return self.getstatus()

    def getlog(self):
        state, exit_code = self.getstate()

        if os.path.exists(self.request_json):
            with open(self.request_json, 'r') as f:
                request = json.load(f)
            with open(self.errfile, 'r') as f:
                stderr = f.read()
            with open(self.cmdfile, 'r') as f:
                cmd = f.read()
        else:
            request = ''
            stderr = ''
            cmd = ['']

        outputobj = {}
        if state == 'COMPLETE':
            with open(self.outfile, 'r') as outputtemp:
                outputobj = json.load(outputtemp)

        return {
            'workflow_id': self.workflow_id,
            'request': request,
            'state': state,
            'workflow_log': {
                'cmd': cmd,
                'start_time': '',
                'end_time': '',
                'stdout': '',
                'stderr': stderr,
                'exit_code': exit_code
            },
            'task_logs': [],
            'outputs': outputobj
        }


class ToilBackend(WESBackend):
    processes = {}

    def GetServiceInfo(self):
        return {
            'workflow_type_versions': {
                'CWL': {'workflow_type_version': ['v1.0']},
                'WDL': {'workflow_type_version': ['v1.0']}
            },
            'supported_wes_versions': '0.3.0',
            'supported_filesystem_protocols': ['file', 'http', 'https'],
            'engine_versions': ['3.16.0'],
            'system_state_counts': {},
            'key_values': {}
        }

    def ListWorkflows(self):
        # FIXME #15 results don't page
        workflows = []
        for l in os.listdir(os.path.join(os.getcwd(), 'workflows')):
            if os.path.isdir(os.path.join(os.getcwd(), 'workflows', l)):
                w = ToilWorkflow(l)
                workflows.append({'workflow_id': w.workflow_id, 'state': w.getstate()[0]})

        return {
            'workflows': workflows,
            'next_page_token': ''
        }

    def RunWorkflow(self, body):
        if body['workflow_type_version'] != 'v1.0':
            return  # raise?
        if body['workflow_type'] not in ('CWL', 'WDL'):
            return  # raise?
        workflow_id = uuid.uuid4().hex
        job = ToilWorkflow(workflow_id)
        p = Process(target=job.run, args=(body, self))
        p.start()
        self.processes[workflow_id] = p
        return {'workflow_id': workflow_id}

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


def create_backend(opts):
    return ToilBackend(opts)
