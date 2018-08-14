import os
import json
import subprocess
import yaml
import glob
import requests
import urllib
import logging
import schema_salad.ref_resolver

from wes_service.util import visit
from urllib import urlopen


def _twoSevenCompatible(filePath):
    """Determines if a python file is 2.7 compatible by seeing if it compiles in a subprocess"""
    try:
        passes = not subprocess.call(['python2', '-m', 'py_compile', filePath])
    except:
        raise RuntimeError('Python files must be 2.7 compatible')
    return passes


def _getVersion(extension, workflow_file):
    '''Determines the version of a .py, .wdl, or .cwl file.'''
    if extension == 'py' and _twoSevenCompatible(workflow_file):
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

    supportedFormats = ['py', 'wdl', 'cwl']
    fileType = workflow_path.lower().split('.')[-1]  # Grab the file extension
    workflow_path = workflow_path if ':' in workflow_path else 'file://' + workflow_path

    if fileType in supportedFormats:
        if workflow_path.startswith('file://'):
            version = _getVersion(fileType, workflow_path[7:])
        elif workflow_path.startswith('https://') or workflow_path.startswith('http://'):
            # If file not local go fetch it.
            html = urlopen(workflow_path).read()
            localLoc = os.path.join(os.getcwd(), 'fetchedFromRemote.' + fileType)
            with open(localLoc, 'w') as f:
                f.write(html)
            version = wf_info('file://' + localLoc)[0]  # Don't take the fileType here, found it above.
            os.remove(localLoc)  # TODO: Find a way to avoid recreating file before version determination.
        else:
            raise NotImplementedError('Unsupported workflow file location: {}. Must be local or HTTP(S).'.format(workflow_path))
    else:
        raise TypeError('Unsupported workflow type: .{}. Must be {}.'.format(fileType, '.py, .cwl, or .wdl'))
    return version, fileType.upper()


def build_wes_request(workflow_file, json_path, attachments=None):
    """
    :param str workflow_file: Path to cwl/wdl file.  Can be http/https/file.
    :param json_path: Path to accompanying json file.  Currently must be local.
    :param attachments: Any other files needing to be uploaded to the server.

    :return: A list of tuples formatted to be sent in a post to the wes-server (Swagger API).
    """
    workflow_file = "file://" + workflow_file if ":" not in workflow_file else workflow_file
    json_path = json_path[7:] if json_path.startswith("file://") else json_path
    wf_version, wf_type = wf_info(workflow_file)

    parts = [("workflow_params", json.dumps(json.load(open(json_path)))),
             ("workflow_type", wf_type),
             ("workflow_type_version", wf_version)]

    if workflow_file.startswith("file://"):
        parts.append(("workflow_attachment", (os.path.basename(workflow_file[7:]), open(workflow_file[7:], "rb"))))
        parts.append(("workflow_url", os.path.basename(workflow_file[7:])))
    else:
        parts.append(("workflow_url", workflow_file))

    if attachments:
        for attachment in attachments:
            attachment = attachment[7:] if attachment.startswith("file://") else attachment
            if ':' in attachment:
                raise TypeError('Only local files supported for attachment: %s' % attachment)
            parts.append(("workflow_attachment", (os.path.basename(attachment), open(attachment, "rb"))))

    return parts
