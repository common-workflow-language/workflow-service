#!/usr/bin/env python
import urlparse
import pkg_resources  # part of setuptools
import urllib
import json
import time
import sys
import os
import argparse
import logging
import schema_salad.ref_resolver
import requests
from requests.exceptions import MissingSchema
from wes_service.util import visit
from bravado.client import SwaggerClient
from bravado.requests_client import RequestsClient


def main(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser(description="Workflow Execution Service")
    parser.add_argument("--host", type=str, default=os.environ.get("WES_API_HOST"),
                        help="Example: '--host=localhost:8080'.  Defaults to WES_API_HOST.")
    parser.add_argument("--auth", type=str, default=os.environ.get("WES_API_AUTH"), help="Defaults to WES_API_AUTH.")
    parser.add_argument("--proto", type=str, default=os.environ.get("WES_API_PROTO", "https"),
                        help="Options: [http, https].  Defaults to WES_API_PROTO (https).")
    parser.add_argument("--quiet", action="store_true", default=False)
    parser.add_argument("--outdir", type=str)
    parser.add_argument("--page", type=str, default=None)
    parser.add_argument("--page-size", type=int, default=None)

    exgroup = parser.add_mutually_exclusive_group()
    exgroup.add_argument("--run", action="store_true", default=False)
    exgroup.add_argument("--get", type=str, default=None,
                         help="Specify a <workflow-id>.  Example: '--get=<workflow-id>'")
    exgroup.add_argument("--log", type=str, default=None,
                         help="Specify a <workflow-id>.  Example: '--log=<workflow-id>'")
    exgroup.add_argument("--list", action="store_true", default=False)
    exgroup.add_argument("--info", action="store_true", default=False)
    exgroup.add_argument("--version", action="store_true", default=False)

    exgroup = parser.add_mutually_exclusive_group()
    exgroup.add_argument("--wait", action="store_true", default=True, dest="wait")
    exgroup.add_argument("--no-wait", action="store_false", default=True, dest="wait")

    parser.add_argument("workflow_url", type=str, nargs="?", default=None)
    parser.add_argument("job_order", type=str, nargs="?", default=None)
    args = parser.parse_args(argv)

    if args.version:
        pkg = pkg_resources.require("wes_service")
        print(u"%s %s" % (sys.argv[0], pkg[0].version))
        exit(0)

    http_client = RequestsClient()
    split = urlparse.urlsplit("%s://%s/" % (args.proto, args.host))

    http_client.set_api_key(
        split.hostname, args.auth,
        param_name="Authorization", param_in="header")
    client = SwaggerClient.from_url(
        "%s://%s/ga4gh/wes/v1/swagger.json" % (args.proto, args.host),
        http_client=http_client, config={"use_models": False})

    if args.list:
        response = client.WorkflowExecutionService.ListWorkflows(page_token=args.page, page_size=args.page_size)
        json.dump(response.result(), sys.stdout, indent=4)
        return 0

    if args.log:
        response = client.WorkflowExecutionService.GetWorkflowLog(workflow_id=args.log)
        sys.stdout.write(response.result()["workflow_log"]["stderr"])
        return 0

    if args.get:
        response = client.WorkflowExecutionService.GetWorkflowLog(workflow_id=args.get)
        json.dump(response.result(), sys.stdout, indent=4)
        return 0

    if args.info:
        response = client.WorkflowExecutionService.GetServiceInfo()
        json.dump(response.result(), sys.stdout, indent=4)
        return 0

    loader = schema_salad.ref_resolver.Loader({
        "location": {"@type": "@id"},
        "path": {"@type": "@id"}
    })
    input_dict, _ = loader.resolve_ref(args.job_order)

    basedir = os.path.dirname(args.job_order)

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

    workflow_url = args.workflow_url
    if not workflow_url.startswith("/") and ":" not in workflow_url:
        workflow_url = "file://" + os.path.abspath(workflow_url)

    if args.quiet:
        logging.basicConfig(level=logging.WARNING)
    else:
        logging.basicConfig(level=logging.INFO)

    parts = [
        ("workflow_params", json.dumps(input_dict)),
        ("workflow_type", "CWL"),
        ("workflow_type_version", "v1.0")
    ]
    if workflow_url.startswith("file://"):
        # with open(workflow_url[7:], "rb") as f:
        #     body["workflow_descriptor"] = f.read()
        rootdir = os.path.dirname(workflow_url[7:])
        dirpath = rootdir
        # for dirpath, dirnames, filenames in os.walk(rootdir):
        for f in os.listdir(rootdir):
            if f.startswith("."):
                continue
            fn = os.path.join(dirpath, f)
            if os.path.isfile(fn):
                parts.append(('workflow_descriptor', (fn[len(rootdir)+1:], open(fn, "rb"))))
        parts.append(("workflow_url", os.path.basename(workflow_url[7:])))
    else:
        parts.append(("workflow_url", workflow_url))

    postresult = http_client.session.post("%s://%s/ga4gh/wes/v1/workflows" % (args.proto, args.host),
                                          files=parts,
                                          headers={"Authorization": args.auth})

    r = json.loads(postresult.text)

    if postresult.status_code != 200:
        logging.error("%s", r)
        exit(1)

    if args.wait:
        logging.info("Workflow id is %s", r["workflow_id"])
    else:
        sys.stdout.write(r["workflow_id"] + "\n")
        exit(0)

    r = client.WorkflowExecutionService.GetWorkflowStatus(workflow_id=r["workflow_id"]).result()
    while r["state"] in ("QUEUED", "INITIALIZING", "RUNNING"):
        time.sleep(8)
        r = client.WorkflowExecutionService.GetWorkflowStatus(workflow_id=r["workflow_id"]).result()

    logging.info("State is %s", r["state"])

    s = client.WorkflowExecutionService.GetWorkflowLog(workflow_id=r["workflow_id"]).result()

    try:
        # TODO: Only works with Arvados atm
        logging.info(str(s["workflow_log"]["stderr"]))
        logs = requests.get(s["workflow_log"]["stderr"], headers={"Authorization": args.auth}).text
        logging.info("Workflow log:\n" + logs)
    except MissingSchema:
        logging.info("Workflow log:\n" + str(s["workflow_log"]["stderr"]))

    if "fields" in s["outputs"] and s["outputs"]["fields"] is None:
        del s["outputs"]["fields"]
    json.dump(s["outputs"], sys.stdout, indent=4)

    if r["state"] == "COMPLETE":
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
