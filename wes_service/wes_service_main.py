#!/usr/bin/env python
import argparse
import logging
import os
import sys
from importlib.metadata import version
from typing import Optional, cast

import connexion  # type: ignore[import-untyped]
import connexion.utils as utils  # type: ignore[import-untyped]
import ruamel.yaml
from connexion.resolver import Resolver  # type: ignore[import-untyped]

logging.basicConfig(level=logging.INFO)


def setup(args: Optional[argparse.Namespace] = None) -> connexion.App:
    """Config a Connexion App using the provided arguments."""
    if args is None:
        args = get_parser().parse_args([])  # grab the defaults

    configfile = "config.yml"
    if os.path.isfile(configfile):
        logging.info("Loading %s", configfile)
        with open(configfile) as f:
            config = ruamel.yaml.safe_load(f)
        for c in config:
            setattr(args, c, config[c])

    logging.info("Using config:")
    for n in args.__dict__:
        logging.info("  %s: %s", n, getattr(args, n))

    app = connexion.App(__name__)
    backend = utils.get_function_from_name(args.backend + ".create_backend")(
        app, args.opt
    )

    def rs(x: str) -> str:
        return cast(str, getattr(backend, x.split(".")[-1]))

    app.add_api(
        "openapi/workflow_execution_service.swagger.yaml", resolver=Resolver(rs)
    )

    return app


def get_parser() -> argparse.ArgumentParser:
    """Construct an argument parser."""
    parser = argparse.ArgumentParser(description="Workflow Execution Service")
    parser.add_argument(
        "--backend",
        type=str,
        default="wes_service.cwl_runner",
        help="Either: '--backend=wes_service.arvados_wes' or '--backend=wes_service.cwl_runner'",
    )
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--opt",
        type=str,
        action="append",
        help="Example: '--opt runner=cwltoil --opt extra=--logLevel=CRITICAL' "
        "or '--opt extra=--workDir=/'.  Accepts multiple values.",
    )
    parser.add_argument("--version", action="store_true", default=False)
    return parser


def main(argv: list[str] = sys.argv[1:]) -> None:
    """Run the WES Service app."""
    args = get_parser().parse_args(argv)

    if args.version:
        print(version("wes_service"))
        exit(0)

    app = setup(args)

    app.run(port=args.port)


if __name__ == "__main__":
    main(sys.argv[1:])
