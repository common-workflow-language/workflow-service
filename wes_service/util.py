import tempfile
import json
import os
import logging

from six import itervalues, iterlists
import connexion
from werkzeug.utils import secure_filename


def visit(d, op):
    """Recursively call op(d) for all list subelements and dictionary 'values' that d may have."""
    op(d)
    if isinstance(d, list):
        for i in d:
            visit(i, op)
    elif isinstance(d, dict):
        for i in itervalues(d):
            visit(i, op)


class WESBackend(object):
    """Stores and retrieves options.  Intended to be inherited."""
    def __init__(self, opts):
        """Parse and store options as a list of tuples."""
        self.pairs = []
        for o in opts if opts else []:
            k, v = o.split("=", 1)
            self.pairs.append((k, v))

    def getopt(self, p, default=None):
        """Returns the first option value stored that matches p or default."""
        for k, v in self.pairs:
            if k == p:
                return v
        return default

    def getoptlist(self, p):
        """Returns all option values stored that match p as a list."""
        optlist = []
        for k, v in self.pairs:
            if k == p:
                optlist.append(v)
        return optlist

    def log_for_run(self, run_id, message):
        logging.info("Workflow %s: %s", run_id, message)

    def collect_attachments(self, run_id=None):
        tempdir = tempfile.mkdtemp()
        body = {}
        for k, ls in iterlists(connexion.request.files):
            for v in ls:
                if k == "workflow_attachment":
                    filename = secure_filename(v.filename)
                    dest = os.path.join(tempdir, filename)
                    self.log_for_run(run_id, "Staging attachment '%s' to '%s'" % (v.filename, dest))
                    v.save(dest)
                    body[k] = "file://%s" % tempdir  # Reference to temp working dir.
                elif k in ("workflow_params", "tags", "workflow_engine_parameters"):
                    content = v.read()
                    body[k] = json.loads(content)
                else:
                    body[k] = v.read()

        if ":" not in body["workflow_url"]:
            body["workflow_url"] = "file://%s" % os.path.join(tempdir, secure_filename(body["workflow_url"]))

        self.log_for_run(run_id, "Using workflow_url '%s'" % body.get("workflow_url"))

        return tempdir, body
