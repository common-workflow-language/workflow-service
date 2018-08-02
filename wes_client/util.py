import os
import json


def wf_type(workflow_file):
    if workflow_file.lower().endswith('wdl'):
        return 'WDL'
    elif workflow_file.lower().endswith('cwl'):
        return 'CWL'
    elif workflow_file.lower().endswith('py'):
        return 'PY'
    else:
        raise ValueError('Unrecognized/unsupported workflow file extension: %s' % workflow_file.lower().split('.')[-1])


def wf_version(workflow_file):
    # TODO: Check inside of the file, handling local/http/etc.
    if wf_type(workflow_file) == 'PY':
        return '2.7'
    # elif wf_type(workflow_file) == 'CWL':
    #     # only works locally
    #     return yaml.load(open(workflow_file))['cwlVersion']
    else:
        # TODO: actually check the wdl file
        return "v1.0"


def build_wes_request(workflow_file, json_path, attachments=None):
    """
    :param str workflow_file: Path to cwl/wdl file.  Can be http/https/file.
    :param json_path: Path to accompanying json file.  Currently must be local.
    :param attachments: Any other files needing to be uploaded to the server.

    :return: A list of tuples formatted to be sent in a post to the wes-server (Swagger API).
    """
    workflow_file = "file://" + workflow_file if "://" not in workflow_file else workflow_file
    json_path = json_path[7:] if json_path.startswith("file://") else json_path

    parts = [("workflow_params", json.dumps(json.load(open(json_path)))),
             ("workflow_type", wf_type(workflow_file)),
             ("workflow_type_version", wf_version(workflow_file))]

    if workflow_file.startswith("file://"):
        parts.append(("workflow_attachment", (os.path.basename(workflow_file[7:]), open(workflow_file[7:], "rb"))))
        parts.append(("workflow_url", os.path.basename(workflow_file[7:])))
    else:
        parts.append(("workflow_url", workflow_file))

    if attachments:
        for attachment in attachments:
            attachment = attachment[7:] if attachment.startswith("file://") else attachment
            parts.append(("workflow_attachment", (os.path.basename(attachment), open(attachment, "rb"))))

    return parts
