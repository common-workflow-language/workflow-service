"""Client WES utilities."""

import glob
import json
import logging
import os
import sys
from subprocess import DEVNULL, CalledProcessError, check_call  # nosec B404
from typing import Any, Optional, Union, cast
from urllib.request import pathname2url, urlopen

import requests
import schema_salad.ref_resolver
import yaml

from wes_service.util import visit


def py3_compatible(filePath: str) -> bool:
    """
    Check file for Python 3.x compatibity.

    (By seeing if it compiles in a subprocess)
    """
    try:
        check_call(
            [sys.executable, "-m", "py_compile", os.path.normpath(filePath)],
            stderr=DEVNULL,
        )  # nosec B603
    except CalledProcessError as e:
        raise RuntimeError("Python files must be 3.x compatible") from e
    return True


def get_version(extension: str, workflow_file: str) -> str:
    """Determine the version of a .py, .wdl, or .cwl file."""
    if extension == "py" and py3_compatible(workflow_file):
        return "3"
    elif extension == "cwl":
        return cast(str, yaml.safe_load(open(workflow_file))["cwlVersion"])
    else:  # Must be a wdl file.
        # Borrowed from https://github.com/Sage-Bionetworks/synapse-orchestrator/
        #               blob/develop/synorchestrator/util.py#L142
        try:
            return [
                entry.lstrip("version")
                for entry in workflow_file.splitlines()
                if "version" in entry.split(" ")
            ][0]
        except IndexError:
            return "draft-2"


def wf_info(workflow_path: str) -> tuple[str, str]:
    """
    Return the version of the file and the file extension.

    Assumes that the file path is to the file directly ie, ends with a valid
    file extension. Supports checking local files as well as files at http://
    and https:// locations. Files at these remote locations are recreated locally to
    enable our approach to version checking, then removed after version is extracted.
    """
    supported_formats = ["py", "wdl", "cwl"]
    file_type = workflow_path.lower().split(".")[-1]  # Grab the file extension
    workflow_path = workflow_path if ":" in workflow_path else "file://" + workflow_path

    if file_type in supported_formats:
        if workflow_path.startswith("file://"):
            version = get_version(file_type, workflow_path[7:])
        elif workflow_path.startswith("https://") or workflow_path.startswith(
            "http://"
        ):
            # If file not local go fetch it.
            html = urlopen(workflow_path).read()  # nosec B310
            local_loc = os.path.join(os.getcwd(), "fetchedFromRemote." + file_type)
            with open(local_loc, "w") as f:
                f.write(html.decode())
            version = wf_info("file://" + local_loc)[
                0
            ]  # Don't take the file_type here, found it above.
            os.remove(
                local_loc
            )  # TODO: Find a way to avoid recreating file before version determination.
        else:
            raise NotImplementedError(
                "Unsupported workflow file location: {}. Must be local or HTTP(S).".format(
                    workflow_path
                )
            )
    else:
        raise TypeError(
            "Unsupported workflow type: .{}. Must be {}.".format(
                file_type, ".py, .cwl, or .wdl"
            )
        )
    return version, file_type.upper()


def modify_jsonyaml_paths(jsonyaml_file: str) -> str:
    """
    Changes relative paths in a json/yaml file to be relative
    to where the json/yaml file is located.

    :param jsonyaml_file: Path to a json/yaml file.
    """
    loader = schema_salad.ref_resolver.Loader(
        {"location": {"@type": "@id"}, "path": {"@type": "@id"}}
    )
    input_dict, _ = loader.resolve_ref(jsonyaml_file, checklinks=False)
    basedir = os.path.dirname(jsonyaml_file)

    def fixpaths(d: Any) -> None:
        """Make sure all paths have a URI scheme."""
        if isinstance(d, dict):
            if "path" in d:
                if ":" not in d["path"]:
                    local_path = os.path.normpath(
                        os.path.join(os.getcwd(), basedir, d["path"])
                    )
                    d["location"] = pathname2url(local_path)
                else:
                    d["location"] = d["path"]
                del d["path"]

    visit(input_dict, fixpaths)
    return json.dumps(input_dict)


def build_wes_request(
    workflow_file: str, json_path: str, attachments: Optional[list[str]] = None
) -> tuple[list[tuple[str, Any]], list[tuple[str, Any]]]:
    """
    :param workflow_file: Path to cwl/wdl file.  Can be http/https/file.
    :param json_path: Path to accompanying json file.
    :param attachments: Any other files needing to be uploaded to the server.

    :return: A list of tuples formatted to be sent in a post to the wes-server (Swagger API).
    """
    workflow_file = (
        "file://" + workflow_file if ":" not in workflow_file else workflow_file
    )
    wfbase = None
    if json_path.startswith("file://"):
        wfbase = os.path.dirname(json_path[7:])
        json_path = json_path[7:]
        with open(json_path) as f:
            wf_params = json.dumps(json.load(f))
    elif json_path.startswith("http"):
        wf_params = modify_jsonyaml_paths(json_path)
    else:
        wf_params = json_path
    wf_version, wf_type = wf_info(workflow_file)

    parts: list[tuple[str, Any]] = [
        ("workflow_params", wf_params),
        ("workflow_type", wf_type),
        ("workflow_type_version", wf_version),
    ]

    workflow_attachments = []

    if workflow_file.startswith("file://"):
        if wfbase is None:
            wfbase = os.path.dirname(workflow_file[7:])
        workflow_attachments.append(
            (
                "workflow_attachment",
                (os.path.basename(workflow_file[7:]), open(workflow_file[7:], "rb")),
            )
        )
        parts.append(("workflow_url", os.path.basename(workflow_file[7:])))
    else:
        parts.append(("workflow_url", workflow_file))

    if wfbase is None:
        wfbase = os.getcwd()
    if attachments:
        for attachment in attachments:
            if attachment.startswith("file://"):
                attachment = attachment[7:]
                attach_f: Any = open(attachment, "rb")
                relpath = os.path.relpath(attachment, wfbase)
            elif attachment.startswith("http"):
                attach_f = urlopen(attachment)  # nosec B310
                relpath = os.path.basename(attach_f)

            workflow_attachments.append(("workflow_attachment", (relpath, attach_f)))

    return parts, workflow_attachments


def expand_globs(attachments: Optional[Union[list[str], str]]) -> set[str]:
    """Expand any globs present in the attachment list."""
    expanded_list = []
    if attachments is None:
        attachments = []
    for filepath in attachments:
        if "file://" in filepath:
            for f in glob.glob(filepath[7:]):
                expanded_list += ["file://" + os.path.abspath(f)]
        elif ":" not in filepath:
            for f in glob.glob(filepath):
                expanded_list += ["file://" + os.path.abspath(f)]
        else:
            expanded_list += [filepath]
    return set(expanded_list)


def wes_response(postresult: requests.Response) -> dict[str, Any]:
    """Convert a Response object to JSON text."""
    if postresult.status_code != 200:
        error = str(json.loads(postresult.text))
        logging.error(error)
        raise Exception(error)

    return cast(dict[str, Any], json.loads(postresult.text))


class WESClient:
    """WES client."""

    def __init__(self, service: dict[str, Any]):
        """Initialize the cliet with the provided credentials and endpoint."""
        self.auth = service["auth"]
        self.proto = service["proto"]
        self.host = service["host"]

    def get_service_info(self) -> dict[str, Any]:
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
        postresult = requests.get(  # nosec B113
            f"{self.proto}://{self.host}/ga4gh/wes/v1/service-info",
            headers=self.auth,
        )
        return wes_response(postresult)

    def list_runs(self) -> dict[str, Any]:
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
        postresult = requests.get(  # nosec B113
            f"{self.proto}://{self.host}/ga4gh/wes/v1/runs", headers=self.auth
        )
        return wes_response(postresult)

    def run(
        self, wf: str, jsonyaml: str, attachments: Optional[list[str]]
    ) -> dict[str, Any]:
        """
        Composes and sends a post request that signals the wes server to run a workflow.

        :param wf: A local/http/https path to a cwl/wdl/python workflow file.
        :param jsonyaml: A local path to a json or yaml file.
        :param list attachments: A list of local paths to files that will be uploaded to the server.
        :param str auth: String to send in the auth header.
        :param proto: Schema where the server resides (http, https)
        :param host: Port where the post request will be sent and the wes server listens at (default 8080)

        :return: The body of the post result as a dictionary.
        """
        attachments = list(expand_globs(attachments))
        parts, files = build_wes_request(wf, jsonyaml, attachments)
        postresult = requests.post(  # nosec B113
            f"{self.proto}://{self.host}/ga4gh/wes/v1/runs",
            data=parts,
            files=files,
            # headers=self.auth,
        )
        return wes_response(postresult)

    def cancel(self, run_id: str) -> dict[str, Any]:
        """
        Cancel a running workflow.

        :param run_id: String (typically a uuid) identifying the run.
        :param str auth: String to send in the auth header.
        :param proto: Schema where the server resides (http, https)
        :param host: Port where the post request will be sent and the wes server listens at (default 8080)
        :return: The body of the delete result as a dictionary.
        """
        postresult = requests.post(  # nosec B113
            f"{self.proto}://{self.host}/ga4gh/wes/v1/runs/{run_id}/cancel",
            headers=self.auth,
        )
        return wes_response(postresult)

    def get_run_log(self, run_id: str) -> dict[str, Any]:
        """
        Get detailed info about a running workflow.

        :param run_id: String (typically a uuid) identifying the run.
        :param str auth: String to send in the auth header.
        :param proto: Schema where the server resides (http, https)
        :param host: Port where the post request will be sent and the wes server listens at (default 8080)
        :return: The body of the get result as a dictionary.
        """
        postresult = requests.get(  # nosec B113
            f"{self.proto}://{self.host}/ga4gh/wes/v1/runs/{run_id}",
            headers=self.auth,
        )
        return wes_response(postresult)

    def get_run_status(self, run_id: str) -> dict[str, Any]:
        """
        Get quick status info about a running workflow.

        :param run_id: String (typically a uuid) identifying the run.
        :param str auth: String to send in the auth header.
        :param proto: Schema where the server resides (http, https)
        :param host: Port where the post request will be sent and the wes server listens at (default 8080)
        :return: The body of the get result as a dictionary.
        """
        postresult = requests.get(  # nosec B113
            f"{self.proto}://{self.host}/ga4gh/wes/v1/runs/{run_id}/status",
            headers=self.auth,
        )
        return wes_response(postresult)
