import os
import json
import schema_salad.ref_resolver
from subprocess32 import check_call, DEVNULL, CalledProcessError
import yaml
import glob
import requests
import urllib
import logging

from wes_service.util import visit
from urllib import urlopen


def two_seven_compatible(filePath):
    """Determines if a python file is 2.7 compatible by seeing if it compiles in a subprocess"""
    try:
        check_call(['python2', '-m', 'py_compile', filePath], stderr=DEVNULL)
    except CalledProcessError:
        raise RuntimeError('Python files must be 2.7 compatible')
    return True


def get_version(extension, workflow_file):
    '''Determines the version of a .py, .wdl, or .cwl file.'''
    if extension == 'py' and two_seven_compatible(workflow_file):
        return '2.7'
    elif extension == 'cwl':
        return yaml.load(open(workflow_file))['cwlVersion']
    else:  # Must be a wdl file.
        # Borrowed from https://github.com/Sage-Bionetworks/synapse-orchestrator/blob/develop/synorchestrator/util.py#L142
        try:
            return [l.lstrip('version') for l in workflow_file.splitlines() if 'version' in l.split(' ')][0]
        except IndexError:
            return 'draft-2'


def wf_info(workflow_path):
    """
    Returns the version of the file and the file extension.

    Assumes that the file path is to the file directly ie, ends with a valid file extension.Supports checking local
    files as well as files at http:// and https:// locations. Files at these remote locations are recreated locally to
    enable our approach to version checking, then removed after version is extracted.
    """

    supported_formats = ['py', 'wdl', 'cwl']
    file_type = workflow_path.lower().split('.')[-1]  # Grab the file extension
    workflow_path = workflow_path if ':' in workflow_path else 'file://' + workflow_path

    if file_type in supported_formats:
        if workflow_path.startswith('file://'):
            version = get_version(file_type, workflow_path[7:])
        elif workflow_path.startswith('https://') or workflow_path.startswith('http://'):
            # If file not local go fetch it.
            html = urlopen(workflow_path).read()
            local_loc = os.path.join(os.getcwd(), 'fetchedFromRemote.' + file_type)
            with open(local_loc, 'w') as f:
                f.write(html)
            version = wf_info('file://' + local_loc)[0]  # Don't take the file_type here, found it above.
            os.remove(local_loc)  # TODO: Find a way to avoid recreating file before version determination.
        else:
            raise NotImplementedError('Unsupported workflow file location: {}. Must be local or HTTP(S).'.format(workflow_path))
    else:
        raise TypeError('Unsupported workflow type: .{}. Must be {}.'.format(file_type, '.py, .cwl, or .wdl'))
    return version, file_type.upper()


def modify_jsonyaml_paths(jsonyaml_file):
    """
    Changes relative paths in a json/yaml file to be relative
    to where the json/yaml file is located.

    :param jsonyaml_file: Path to a json/yaml file.
    """
    loader = schema_salad.ref_resolver.Loader({
        "location": {"@type": "@id"},
        "path": {"@type": "@id"}
    })
    input_dict, _ = loader.resolve_ref(jsonyaml_file, checklinks=False)
    basedir = os.path.dirname(jsonyaml_file)

    def fixpaths(d):
        """Make sure all paths have a URI scheme."""
        if isinstance(d, dict):
            if "path" in d:
                if ":" not in d["path"]:
                    local_path = os.path.normpath(os.path.join(os.getcwd(), basedir, d["path"]))
                    d["location"] = urllib.pathname2url(local_path)
                else:
                    d["location"] = d["path"]
                del d["path"]

    visit(input_dict, fixpaths)
    return json.dumps(input_dict)


def build_wes_request(workflow_file, json_path, attachments=None):
    """
    :param str workflow_file: Path to cwl/wdl file.  Can be http/https/file.
    :param json_path: Path to accompanying json file.
    :param attachments: Any other files needing to be uploaded to the server.

    :return: A list of tuples formatted to be sent in a post to the wes-server (Swagger API).
    """
    workflow_file = "file://" + workflow_file if ":" not in workflow_file else workflow_file
    if json_path.startswith("file://"):
        json_path = json_path[7:]
        with open(json_path) as f:
            wf_params = json.dumps(json.load(f))
    elif json_path.startswith("http"):
        wf_params = modify_jsonyaml_paths(json_path)
    else:
        wf_params = json_path
    wf_version, wf_type = wf_info(workflow_file)

    parts = [("workflow_params", wf_params),
             ("workflow_type", wf_type),
             ("workflow_type_version", wf_version)]

    if workflow_file.startswith("file://"):
        parts.append(("workflow_attachment", (os.path.basename(workflow_file[7:]), open(workflow_file[7:], "rb"))))
        parts.append(("workflow_url", os.path.basename(workflow_file[7:])))
    else:
        parts.append(("workflow_url", workflow_file))

    if attachments:
        for attachment in attachments:
            if attachment.startswith("file://"):
                attachment = attachment[7:]
                attach_f = open(attachment, "rb")
            elif attachment.startswith("http"):
                attach_f = urlopen(attachment)

            parts.append(("workflow_attachment", (os.path.basename(attachment), attach_f)))

    return parts


def expand_globs(attachments):
    expanded_list = []
    for filepath in attachments:
        if 'file://' in filepath:
            for f in glob.glob(filepath[7:]):
                expanded_list += ['file://' + os.path.abspath(f)]
        elif ':' not in filepath:
            for f in glob.glob(filepath):
                expanded_list += ['file://' + os.path.abspath(f)]
        else:
            expanded_list += [filepath]
    return set(expanded_list)


def wes_reponse(postresult):
    if postresult.status_code != 200:
        logging.error("%s", json.loads(postresult.text))
        exit(1)
    return json.loads(postresult.text)


class WESClient(object):
    def __init__(self, service):
        self.auth = service['auth']
        self.proto = service['proto']
        self.host = service['host']

    def get_service_info(self):
        """
        Get information about Workflow Execution Service. May
        include information related (but not limited to) the
        workflow descriptor formats, versions supported, the
        WES API versions supported, and information about general
        the service availability.

        :param str auth: String to send in the auth header.
        :param proto: Schema where the server resides (http, https)
        :param host: Port where the post request will be sent and the wes server listens at (default 8080)
        :return: The body of the get result as a dictionary.
        """
        postresult = requests.get("%s://%s/ga4gh/wes/v1/service-info" % (self.proto, self.host),
                                  headers=self.auth)
        return wes_reponse(postresult)

    def list_runs(self):
        """
        List the workflows, this endpoint will list the workflows
        in order of oldest to newest. There is no guarantee of
        live updates as the user traverses the pages, the behavior
        should be decided (and documented) by each implementation.

        :param str auth: String to send in the auth header.
        :param proto: Schema where the server resides (http, https)
        :param host: Port where the post request will be sent and the wes server listens at (default 8080)
        :return: The body of the get result as a dictionary.
        """
        postresult = requests.get("%s://%s/ga4gh/wes/v1/runs" % (self.proto, self.host),
                                  headers=self.auth)
        return wes_reponse(postresult)

    def run(self, wf, jsonyaml, attachments):
        """
        Composes and sends a post request that signals the wes server to run a workflow.

        :param str workflow_file: A local/http/https path to a cwl/wdl/python workflow file.
        :param str jsonyaml: A local path to a json or yaml file.
        :param list attachments: A list of local paths to files that will be uploaded to the server.
        :param str auth: String to send in the auth header.
        :param proto: Schema where the server resides (http, https)
        :param host: Port where the post request will be sent and the wes server listens at (default 8080)

        :return: The body of the post result as a dictionary.
        """
        attachments = list(expand_globs(attachments))
        parts = build_wes_request(wf, jsonyaml, attachments)
        postresult = requests.post("%s://%s/ga4gh/wes/v1/runs" % (self.proto, self.host),
                                   files=parts,
                                   headers=self.auth)
        return wes_reponse(postresult)

    def cancel(self, run_id):
        """
        Cancel a running workflow.

        :param run_id: String (typically a uuid) identifying the run.
        :param str auth: String to send in the auth header.
        :param proto: Schema where the server resides (http, https)
        :param host: Port where the post request will be sent and the wes server listens at (default 8080)
        :return: The body of the delete result as a dictionary.
        """
        postresult = requests.delete("%s://%s/ga4gh/wes/v1/runs/%s" % (self.proto, self.host, run_id),
                                     headers=self.auth)
        return wes_reponse(postresult)

    def get_run_log(self, run_id):
        """
        Get detailed info about a running workflow.

        :param run_id: String (typically a uuid) identifying the run.
        :param str auth: String to send in the auth header.
        :param proto: Schema where the server resides (http, https)
        :param host: Port where the post request will be sent and the wes server listens at (default 8080)
        :return: The body of the get result as a dictionary.
        """
        postresult = requests.get("%s://%s/ga4gh/wes/v1/runs/%s" % (self.proto, self.host, run_id),
                                  headers=self.auth)
        return wes_reponse(postresult)

    def get_run_status(self, run_id):
        """
        Get quick status info about a running workflow.

        :param run_id: String (typically a uuid) identifying the run.
        :param str auth: String to send in the auth header.
        :param proto: Schema where the server resides (http, https)
        :param host: Port where the post request will be sent and the wes server listens at (default 8080)
        :return: The body of the get result as a dictionary.
        """
        postresult = requests.get("%s://%s/ga4gh/wes/v1/runs/%s/status" % (self.proto, self.host, run_id),
                                  headers=self.auth)
        return wes_reponse(postresult)
