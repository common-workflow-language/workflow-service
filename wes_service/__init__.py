import connexion
from connexion.resolver import Resolver
import connexion.utils as utils

import threading
import tempfile
import subprocess
import uuid
import os
import json
import urllib
import argparse
import sys

from pkg_resources import resource_stream

def main(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='Workflow Execution Service')
    parser.add_argument("--backend", type=str, default="wes_service.cwl_runner")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--opt", type=str, action="append")
    args = parser.parse_args(argv)

    app = connexion.App(__name__)
    backend = utils.get_function_from_name(args.backend + ".create_backend")(args.opt)
    def rs(x):
        return getattr(backend, x)

    res = resource_stream(__name__, 'swagger/proto/workflow_execution.swagger.json')
    app.add_api(json.load(res), resolver=Resolver(rs))

    app.run(port=args.port)

if __name__ == "__main__":
    main(sys.argv[1:])
