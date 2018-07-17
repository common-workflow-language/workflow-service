#!/usr/bin/env python

import sys
import cwltool.main
import tempfile
import logging
import StringIO
import json

_logger = logging.getLogger("cwltool")
_logger.setLevel(logging.ERROR)


def main(args=None):
    if args is None:
        args = sys.argv[1:]

    if len(args) == 0:
        print("Workflow must be on command line")
        return 1

    parser = cwltool.main.arg_parser()
    parsedargs = parser.parse_args(args)

    a = True
    while a:
        a = True
        msg = ""
        while a and a != "\n":
            a = sys.stdin.readline()
            msg += a

        outdir = tempfile.mkdtemp("", parsedargs.tmp_outdir_prefix)

        t = StringIO.StringIO(msg)
        err = StringIO.StringIO()
        if cwltool.main.main(["--outdir="+outdir] + args + ["-"], stdin=t, stderr=err) != 0:
            sys.stdout.write(json.dumps({"cwl:error": err.getvalue()}))
        sys.stdout.write("\n\n")
        sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
