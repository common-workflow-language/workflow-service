#!/usr/bin/env python

from bravado.client import SwaggerClient
from bravado.requests_client import RequestsClient
import json
import time
import sys
import os
import argparse
import logging
import urlparse
import pkg_resources  # part of setuptools
from wes_service.util import visit
import urllib
import ruamel.yaml as yaml
import schema_salad.ref_resolver

def main(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='Workflow Execution Service')
    parser.add_argument(
        "--host", type=str, default=os.environ.get("WES_API_HOST"))
    parser.add_argument(
        "--auth", type=str, default=os.environ.get("WES_API_AUTH"))
    parser.add_argument(
        "--proto", type=str, default=os.environ.get("WES_API_PROTO", "https"))
    parser.add_argument("--quiet", action="store_true", default=False)
    parser.add_argument("--outdir", type=str)

    exgroup = parser.add_mutually_exclusive_group()
    exgroup.add_argument("--run", action="store_true", default=False)
    exgroup.add_argument("--get", type=str, default=None)
    exgroup.add_argument("--log", type=str, default=None)
    exgroup.add_argument("--list", action="store_true", default=False)
    exgroup.add_argument("--info", action="store_true", default=False)
    exgroup.add_argument("--version", action="store_true", default=False)

    exgroup = parser.add_mutually_exclusive_group()
    exgroup.add_argument(
        "--wait", action="store_true", default=True, dest="wait")
    exgroup.add_argument(
        "--no-wait", action="store_false", default=True, dest="wait")

    parser.add_argument("workflow_url", type=str, nargs="?", default=None)
    parser.add_argument("job_order", type=str, nargs="?", default=None)
    args = parser.parse_args(argv)

    if args.version:
        pkg = pkg_resources.require("wes_service")
        print u"%s %s" % (sys.argv[0], pkg[0].version)
        exit(0)

    http_client = RequestsClient()
    split = urlparse.urlsplit("%s://%s/" % (args.proto, args.host))

    http_client.set_api_key(
        split.hostname, args.auth,
        param_name='Authorization', param_in='header')
    client = SwaggerClient.from_url(
        "%s://%s/ga4gh/wes/v1/swagger.json" % (args.proto, args.host),
        http_client=http_client, config={'use_models': False})

    if args.list:
        response = client.WorkflowExecutionService.ListWorkflows()
        json.dump(response.result(), sys.stdout, indent=4)
        return 0

    if args.log:
        response = client.WorkflowExecutionService.GetWorkflowLog(
            workflow_id=args.log)
        sys.stdout.write(response.result()["workflow_log"]["stderr"])
        return 0

    if args.get:
        response = client.WorkflowExecutionService.GetWorkflowLog(
            workflow_id=args.get)
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
    input, _ = loader.resolve_ref(args.job_order)

    basedir = os.path.dirname(args.job_order)

    def fixpaths(d):
        if isinstance(d, dict):
            if "path" in d:
                if ":" not in d["path"]:
                    local_path = os.path.normpath(
                        os.path.join(os.getcwd(), basedir, d["path"]))
                    d["location"] = urllib.pathname2url(local_path)
                else:
                    d["location"] = d["path"]
                del d["path"]
            loc = d.get("location", "")
            if d.get("class") == "Directory":
                if loc.startswith("http:") or loc.startswith("https:"):
                    logging.error("Directory inputs not supported with http references")
                    exit(33)
            if not (loc.startswith("http:") or loc.startswith("https:")
                    or args.job_order.startswith("http:") or args.job_order.startswith("https:")):
                logging.error("Upload local files not supported, must use http: or https: references.")
                exit(33)

    visit(input, fixpaths)

    workflow_url = args.workflow_url
    if not workflow_url.startswith("/") and ":" not in workflow_url:
        workflow_url = "file://" + os.path.abspath(workflow_url)

    if args.quiet:
        logging.basicConfig(level=logging.WARNING)
    else:
        logging.basicConfig(level=logging.INFO)

    body = {
        "workflow_params": input,
        "workflow_type": "CWL",
        "workflow_type_version": "v1.0"
    }

    if workflow_url.startswith("file://"):
        with open(workflow_url[7:], "r") as f:
            body["workflow_descriptor"] = f.read()
    else:
        body["workflow_url"] = workflow_url

    r = client.WorkflowExecutionService.RunWorkflow(body=body).result()

    if args.wait:
        logging.info("Workflow id is %s", r["workflow_id"])
    else:
        sys.stdout.write(r["workflow_id"]+"\n")
        exit(0)

    r = client.WorkflowExecutionService.GetWorkflowStatus(
        workflow_id=r["workflow_id"]).result()
    while r["state"] in ("QUEUED", "INITIALIZING", "RUNNING"):
        time.sleep(1)
        r = client.WorkflowExecutionService.GetWorkflowStatus(
            workflow_id=r["workflow_id"]).result()

    logging.info("State is %s", r["state"])

    s = client.WorkflowExecutionService.GetWorkflowLog(
        workflow_id=r["workflow_id"]).result()
    logging.info("Workflow log:\n"+s["workflow_log"]["stderr"])

    if "fields" in s["outputs"] and s["outputs"]["fields"] is None:
        del s["outputs"]["fields"]
    json.dump(s["outputs"], sys.stdout, indent=4)

    if r["state"] == "COMPLETE":
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
