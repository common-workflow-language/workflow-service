import argparse
import sys
import ruamel.yaml
import os
import logging

logging.basicConfig(level=logging.INFO)

import connexion
import connexion.utils as utils
from connexion.resolver import Resolver

def setup(args=None):
    if args is None:
        args = argparse.Namespace()

    configfile = "config.yml"
    if os.path.isfile(configfile):
        logging.info("Loading %s", configfile)
        with open(configfile, "r") as f:
            config = ruamel.yaml.safe_load(f)
        for c in config:
            setattr(args, c, config[c])


    logging.info("Using config:")
    for n in args.__dict__:
        logging.info("  %s: %s", n, getattr(args, n))

    app = connexion.App(__name__)
    backend = utils.get_function_from_name(
        args.backend + ".create_backend")(args.opt)

    def rs(x):
        return getattr(backend, x)

    app.add_api(
        'openapi/workflow_execution_service.swagger.yaml',
        resolver=Resolver(rs))

    return app


def main(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='Workflow Execution Service')
    parser.add_argument(
        "--backend", type=str, default="wes_service.cwl_runner")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--opt", type=str, action="append")
    parser.add_argument("--debug", action="store_true", default=False)
    args = parser.parse_args(argv)

    app = setup(args)

    app.run(port=args.port, debug=args.debug)


if __name__ == "__main__":
    main(sys.argv[1:])
