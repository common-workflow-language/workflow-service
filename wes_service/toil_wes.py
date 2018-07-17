import os
import json
import uuid
import subprocess
import urllib
from multiprocessing import Process
import functools
import logging
import sys
from six import iteritems
from cwltool.main import load_job_order
from argparse import Namespace

from wes_service.util import WESBackend
from wes_service.cwl_runner import Workflow
from wes_service.arvados_wes import MissingAuthorization

logging.basicConfig(level=logging.INFO)


class LocalFiles(object):
    """
    Convenience class for (r)syncing local files to a server.
    """
    def __init__(self,
                 input_json,
                 wftype,
                 dest='~',
                 keypath='$HOME/.ssh/westest.pem',
                 domain='ubuntu@54.193.12.111'):
        self.json_path = input_json
        self.keypath = keypath
        self.domain = domain
        self.dest = dest
        self.wftype = wftype

        self.cwl_filemap = {}
        self.filelist = []

    def run_rsync(self, files):
        for f in files:
            cmd = 'rsync -Pav -e "ssh -i {}" {} {}:{}'.format(self.keypath, f, self.domain, self.dest)
            logging.info(cmd)
            p = subprocess.Popen(cmd, shell=True)  # shell=True may be insecure?  need advice
            p.communicate()  # block til finished

    def new_local_path(self, filepath):
        """Stores the path in a list and returns a path relative to self.dest."""
        self.filelist.append(filepath)
        return os.path.join(self.dest, os.path.basename(filepath))

    def wdl_pathmap(self, input):
        """
        Very naive gather of all local files included in a wdl json.

        Expects a json-like dictionary as input.
        These paths are stored as a list for later downloading.
        """
        # TODO: Parse and validate wdl to determine type
        if isinstance(input, basestring):
            if input.startswith('file://'):
                return self.new_local_path(input[7:])
            elif os.path.isfile(input):
                return self.new_local_path(input)
            else:
                return input
        if isinstance(input, list):
            j = []
            for i in input:
                j.append(self.wdl_pathmap(i))
            return j
        elif isinstance(input, dict):
            for k, v in iteritems(input):
                input[k] = self.wdl_pathmap(v)
            return input

    def cwl_pathmap(self, json_dict):
        """
        Gather local files included in a cwl json.

        Expects a json dictionary as input.
        These paths are stored as a list for later downloading.
        """
        assert isinstance(json_dict, dict)

        # use cwltool to parse the json and gather the filepaths
        options = Namespace(job_order=[self.json_path], basedir=None)
        json_vars, options.basedir, loader = load_job_order(options, sys.stdin, None, [], options.job_order)
        for j in json_vars:
            if isinstance(json_vars[j], dict):
                if json_vars[j]['class'] == 'File':
                    if json_vars[j]['path'].startswith('file://'):
                        self.cwl_filemap[j] = json_vars[j]['path'][7:]
        # replace all local top level key 'path's with new paths.
        for k in json_dict:
            if isinstance(json_dict[k], dict):
                if 'class' in json_dict[k]:
                    if json_dict[k]['class'] == 'File':
                        # assume that if k is not in self.cwl_filemap, it is a File, but not local (file://)
                        if k in self.cwl_filemap:
                            json_dict[k]['path'] = self.new_local_path(self.cwl_filemap[k])
        return json_dict

    def sync2server(self):
        """
        1. Opens a json, saves all filepaths within it as a list.
        2. Rsyncs all of these files to the server.
        3. Generates a new json for use on the server with server local paths.
        """
        with open(self.json_path, 'r') as json_data:
            json_dict = json.load(json_data)
            new_json = self.cwl_pathmap(json_dict)
        with open(self.json_path + '.new', 'w') as f:
            json.dump(new_json, f)

        logging.info('Importing local files from: ' + str(self.json_path))
        logging.info('To: {}:{}'.format(self.domain, self.dest))
        logging.info('New json with updated (server) paths created: ' + str(self.json_path + '.new'))
        self.run_rsync(set(self.filelist))
        return self.json_path + '.new'


def catch_toil_exceptions(orig_func):
    """Catch uncaught exceptions and turn them into http errors"""

    @functools.wraps(orig_func)
    def catch_exceptions_wrapper(self, *args, **kwargs):
        try:
            return orig_func(self, *args, **kwargs)
        except RuntimeError as e:
            return {"msg": str(e), "status_code": 500}, 500
        except subprocess.CalledProcessError as e:
            return {"msg": str(e), "status_code": 500}, 500
        except MissingAuthorization:
            return {"msg": "'Authorization' header is missing or empty, "
                           "expecting Toil Auth token", "status_code": 401}, 401

    return catch_exceptions_wrapper


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
        """Writes a cwl, wdl, or python file as appropriate from the request dictionary."""
        wf_filename = os.path.join(self.workdir, 'workflow.' + wftype)
        if request_dict.get('workflow_descriptor'):
            workflow_descriptor = request_dict.get('workflow_descriptor')
            with open(wf_filename, 'w') as f:
                # FIXME #14 workflow_descriptor isn't defined
                f.write(workflow_descriptor)
            workflow_url = urllib.pathname2url(wf_filename)
        else:
            workflow_url = request_dict.get('workflow_url')

        input_json = self.write_json(request_dict)

        if wftype == 'py':
            return [workflow_url]
        else:
            return [workflow_url, input_json]

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

    def run(self, request_dict, opts):
        wftype = request_dict['workflow_type'].lower().strip()
        version = request_dict['workflow_type_version']

        if version != 'v1.0' and wftype in ('cwl', 'wdl'):
            raise RuntimeError('workflow_type "cwl", "wdl" requires '
                               '"workflow_type_version" to be "v1.0": ' + str(version))
        if version != '2.7' and wftype == 'py':
            raise RuntimeError('workflow_type "py" requires '
                               '"workflow_type_version" to be "2.7": ' + str(version))

        if wftype in ('cwl', 'wdl'):
            runner = ['toil-' + wftype + '-runner']
        elif wftype == 'py':
            runner = ['python']
        else:
            raise RuntimeError('workflow_type is not "cwl", "wdl", or "py": ' + str(wftype))

        logging.info('Beginning Toil Workflow ID: ' + str(self.workflow_id))

        with open(self.request_json, 'w') as f:
            json.dump(request_dict, f)

        # write cwl/wdl, as appropriate
        input_wf = self.write_workflow(request_dict, wftype=wftype)

        cmd = runner + opts.getoptlist('extra') + input_wf
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
                'WDL': {'workflow_type_version': ['v1.0']},
                'py': {'workflow_type_version': ['2.7']}
            },
            'supported_wes_versions': '0.3.0',
            'supported_filesystem_protocols': ['file', 'http', 'https'],
            'engine_versions': ['3.16.0'],
            'system_state_counts': {},
            'key_values': {}
        }

    @catch_toil_exceptions
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

    @catch_toil_exceptions
    def RunWorkflow(self, body):
        workflow_id = uuid.uuid4().hex
        job = ToilWorkflow(workflow_id)
        p = Process(target=job.run, args=(body, self))
        p.start()
        self.processes[workflow_id] = p
        return {'workflow_id': workflow_id}

    @catch_toil_exceptions
    def GetWorkflowLog(self, workflow_id):
        job = ToilWorkflow(workflow_id)
        return job.getlog()

    @catch_toil_exceptions
    def CancelJob(self, workflow_id):
        # should this block with `p.is_alive()`?
        if workflow_id in self.processes:
            self.processes[workflow_id].terminate()
        return {'workflow_id': workflow_id}

    @catch_toil_exceptions
    def GetWorkflowStatus(self, workflow_id):
        job = ToilWorkflow(workflow_id)
        return job.getstatus()


def create_backend(opts):
    return ToilBackend(opts)
