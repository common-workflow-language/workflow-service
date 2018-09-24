#!/usr/bin/env python
import pkg_resources  # part of setuptools
import json
import time
import sys
import os
import argparse
import logging
import requests
from requests.exceptions import InvalidSchema, MissingSchema
from wes_client.util import modify_jsonyaml_paths, WESClient


def main(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser(description="Workflow Execution Service")
    parser.add_argument("--host", type=str, default=os.environ.get("WES_API_HOST"),
                        help="Example: '--host=localhost:8080'.  Defaults to WES_API_HOST.")
    parser.add_argument("--auth", type=str, default=os.environ.get("WES_API_AUTH"), help="Format is 'Header: value' or just 'value'.  If header name is not provided, value goes in the 'Authorization'.  Defaults to WES_API_AUTH.")
    parser.add_argument("--proto", type=str, default=os.environ.get("WES_API_PROTO", "https"),
                        help="Options: [http, https].  Defaults to WES_API_PROTO (https).")
    parser.add_argument("--quiet", action="store_true", default=False)
    parser.add_argument("--outdir", type=str)
    parser.add_argument("--attachments", type=str, default=None,
                        help='A comma separated list of attachments to include.  Example: '
                             '--attachments="testdata/dockstore-tool-md5sum.cwl,testdata/md5sum.input"')
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

    auth = {}
    if args.auth:
        if ": " in args.auth:
            sp = args.auth.split(": ")
            auth[sp[0]] = sp[1]
        else:
            auth["Authorization"] = args.auth

    client = WESClient({'auth': auth, 'proto': args.proto, 'host': args.host})

    if args.list:
        response = client.list_runs()  # how to include: page_token=args.page, page_size=args.page_size ?
        json.dump(response, sys.stdout, indent=4)
        return 0

    if args.log:
        response = client.get_run_log(run_id=args.log)
        sys.stdout.write(response["workflow_log"]["stderr"])
        return 0

    if args.get:
        response = client.get_run_log(run_id=args.get)
        json.dump(response, sys.stdout, indent=4)
        return 0

    if args.info:
        response = client.get_service_info()
        json.dump(response, sys.stdout, indent=4)
        return 0

    if not args.workflow_url:
        parser.print_help()
        return 1

    if not args.job_order:
        logging.error("Missing json/yaml file.")
        return 1

    job_order = modify_jsonyaml_paths(args.job_order)

    if args.quiet:
        logging.basicConfig(level=logging.WARNING)
    else:
        logging.basicConfig(level=logging.INFO)

    args.attachments = "" if not args.attachments else args.attachments.split(',')
    r = client.run(args.workflow_url, job_order, args.attachments)

    if args.wait:
        logging.info("Workflow run id is %s", r["run_id"])
    else:
        sys.stdout.write(r["run_id"] + "\n")
        exit(0)

    r = client.get_run_status(run_id=r["run_id"])
    while r["state"] in ("QUEUED", "INITIALIZING", "RUNNING"):
        time.sleep(8)
        r = client.get_run_status(run_id=r["run_id"])

    logging.info("State is %s", r["state"])

    s = client.get_run_log(run_id=r["run_id"])

    try:
        # TODO: Only works with Arvados atm
        logging.info(str(s["run_log"]["stderr"]))
        logs = requests.get(s["run_log"]["stderr"], headers=auth).text
        logging.info("Run log:\n" + logs)
    except InvalidSchema:
        logging.info("Run log:\n" + str(s["run_log"]["stderr"]))
    except MissingSchema:
        logging.info("Run log:\n" + str(s["run_log"]["stderr"]))

    # print the output json
    if "fields" in s["outputs"] and s["outputs"]["fields"] is None:
        del s["outputs"]["fields"]
    json.dump(s["outputs"], sys.stdout, indent=4)

    if r["state"] == "COMPLETE":
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
