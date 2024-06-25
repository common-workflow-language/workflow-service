#!/usr/bin/env python

import json
import logging
import sys
import tempfile
from io import StringIO
from typing import List, Union

import cwltool.main

_logger = logging.getLogger("cwltool")
_logger.setLevel(logging.ERROR)


def main(args: List[str] = sys.argv[1:]) -> int:
    if len(args) == 0:
        print("Workflow must be on command line")
        return 1

    parser = cwltool.argparser.arg_parser()
    parsedargs = parser.parse_args(args)

    a: Union[bool, str] = True
    while a:
        msg = ""
        while a and a != "\n":
            a = sys.stdin.readline()
            msg += a

        outdir = tempfile.mkdtemp("", parsedargs.tmp_outdir_prefix)

        t = StringIO(msg)
        err = StringIO()
        if (
            cwltool.main.main(
                ["--outdir=" + outdir] + args + ["-"], stdin=t, stderr=err
            )
            != 0
        ):
            sys.stdout.write(json.dumps({"cwl:error": err.getvalue()}))
        sys.stdout.write("\n\n")
        sys.stdout.flush()
        a = True
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
