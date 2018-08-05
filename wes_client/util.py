import os
import json
import urlparse
from bravado.client import SwaggerClient
import urllib
import logging
import schema_salad.ref_resolver

from wes_service.util import visit


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
    workflow_file = "file://" + workflow_file if ":" not in workflow_file else workflow_file
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
            if ':' in attachment:
                raise TypeError('Only local files supported for attachment: %s' % attachment)
            parts.append(("workflow_attachment", (os.path.basename(attachment), open(attachment, "rb"))))

    return parts


def wes_client(http_client, auth, proto, host):
    split = urlparse.urlsplit("%s://%s/" % (proto, host))
    http_client.set_api_key(split.hostname, auth, param_name="Authorization", param_in="header")
    client = SwaggerClient.from_url("%s://%s/ga4gh/wes/v1/swagger.json" % (proto, host),
                                    http_client=http_client, config={"use_models": False})
    return client.WorkflowExecutionService


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
    input_dict, _ = loader.resolve_ref(jsonyaml_file)
    basedir = os.path.dirname(jsonyaml_file)

    def fixpaths(d):
        """Make sure all paths have a schema."""
        if isinstance(d, dict):
            if "path" in d:
                if ":" not in d["path"]:
                    local_path = os.path.normpath(os.path.join(os.getcwd(), basedir, d["path"]))
                    d["location"] = urllib.pathname2url(local_path)
                else:
                    d["location"] = d["path"]
                del d["path"]

    visit(input_dict, fixpaths)


def run_wf(workflow_file, jsonyaml, attachments, http_client, auth, proto, host):
    """
    Composes and sends a post request that signals the wes server to run a workflow.

    :param str workflow_file: A local/http/https path to a cwl/wdl/python workflow file.
    :param str jsonyaml: A local path to a json or yaml file.
    :param list attachments: A list of local paths to files that will be uploaded to the server.
    :param object http_client: bravado.requests_client.RequestsClient
    :param str auth: String to send in the auth header.
    :param proto: Schema where the server resides (http, https)
    :param host: Port where the post request will be sent and the wes server listens at (default 8080)

    :return: The body of the post result as a dictionary.
    """
    parts = build_wes_request(workflow_file, jsonyaml, attachments)
    postresult = http_client.session.post("%s://%s/ga4gh/wes/v1/runs" % (proto, host),
                                          files=parts,
                                          headers={"Authorization": auth})
    if postresult.status_code != 200:
        logging.error("%s", json.loads(postresult.text))
        exit(1)
    return json.loads(postresult.text)


def cancel_wf(run_id, http_client, auth, proto, host):
    """
    Cancel a running workflow.

    :param run_id:
    :param object http_client: bravado.requests_client.RequestsClient
    :param str auth: String to send in the auth header.
    :param proto: Schema where the server resides (http, https)
    :param host: Port where the post request will be sent and the wes server listens at (default 8080)
    :return: The body of the delete result as a dictionary.
    """
    postresult = http_client.session.delete("%s://%s/ga4gh/wes/v1/runs/%s" % (proto, host, run_id),
                                            headers={"Authorization": auth})
    if postresult.status_code != 200:
        logging.error("%s", json.loads(postresult.text))
        exit(1)
    return json.loads(postresult.text)


def get_status(run_id, http_client, auth, proto, host):
    """
    Get quick status info about a running workflow.

    :param run_id:
    :param object http_client: bravado.requests_client.RequestsClient
    :param str auth: String to send in the auth header.
    :param proto: Schema where the server resides (http, https)
    :param host: Port where the post request will be sent and the wes server listens at (default 8080)
    :return: The body of the get result as a dictionary.
    """
    postresult = http_client.session.get("%s://%s/ga4gh/wes/v1/runs/%s/status" % (proto, host, run_id),
                                         headers={"Authorization": auth})
    if postresult.status_code != 200:
        logging.error("%s", json.loads(postresult.text))
        exit(1)
    return json.loads(postresult.text)


def get_wf_details(run_id, http_client, auth, proto, host):
    """
    Get detailed info about a running workflow.

    :param run_id:
    :param object http_client: bravado.requests_client.RequestsClient
    :param str auth: String to send in the auth header.
    :param proto: Schema where the server resides (http, https)
    :param host: Port where the post request will be sent and the wes server listens at (default 8080)
    :return: The body of the get result as a dictionary.
    """
    postresult = http_client.session.get("%s://%s/ga4gh/wes/v1/runs/%s" % (proto, host, run_id),
                                         headers={"Authorization": auth})
    if postresult.status_code != 200:
        logging.error("%s", json.loads(postresult.text))
        exit(1)
    return json.loads(postresult.text)


def get_wf_list(http_client, auth, proto, host):
    """
    List the workflows, this endpoint will list the workflows
    in order of oldest to newest. There is no guarantee of
    live updates as the user traverses the pages, the behavior
    should be decided (and documented) by each implementation.

    :param object http_client: bravado.requests_client.RequestsClient
    :param str auth: String to send in the auth header.
    :param proto: Schema where the server resides (http, https)
    :param host: Port where the post request will be sent and the wes server listens at (default 8080)
    :return: The body of the get result as a dictionary.
    """
    postresult = http_client.session.get("%s://%s/ga4gh/wes/v1/runs" % (proto, host),
                                         headers={"Authorization": auth})
    if postresult.status_code != 200:
        logging.error("%s", json.loads(postresult.text))
        exit(1)
    return json.loads(postresult.text)


def get_service_info(http_client, auth, proto, host):
    """
    Get information about Workflow Execution Service. May
    include information related (but not limited to) the
    workflow descriptor formats, versions supported, the
    WES API versions supported, and information about general
    the service availability.

    :param object http_client: bravado.requests_client.RequestsClient
    :param str auth: String to send in the auth header.
    :param proto: Schema where the server resides (http, https)
    :param host: Port where the post request will be sent and the wes server listens at (default 8080)
    :return: The body of the get result as a dictionary.
    """
    postresult = http_client.session.get("%s://%s/ga4gh/wes/v1/service-info" % (proto, host),
                                         headers={"Authorization": auth})
    if postresult.status_code != 200:
        logging.error("%s", json.loads(postresult.text))
        exit(1)
    return json.loads(postresult.text)
