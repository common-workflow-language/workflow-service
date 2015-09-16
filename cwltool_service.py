#!/usr/bin/env python

import sys
import cwltool.main
import tempfile
import logging

_logger = logging.getLogger("cwltool")
_logger.setLevel(logging.ERROR)

def main(args=None):
    if args is None:
        args = sys.argv[1:]

    if len(args) == 0:
        print "Workflow must be on command line"
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

        t = tempfile.NamedTemporaryFile()
        t.write(msg)
        t.flush()
        if cwltool.main.main(["--outdir="+outdir] + args + [t.name]) != 0:
            return 1
        sys.stdout.write("\n\n")

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
