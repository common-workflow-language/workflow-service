import json
import logging
import os
import tempfile
from typing import Any, Callable, Optional

import connexion  # type: ignore[import-untyped]
from werkzeug.utils import secure_filename


def visit(d: Any, op: Callable[[Any], Any]) -> None:
    """Recursively call op(d) for all list subelements and dictionary 'values' that d may have."""
    op(d)
    if isinstance(d, list):
        for i in d:
            visit(i, op)
    elif isinstance(d, dict):
        for i in d.values():
            visit(i, op)


class WESBackend:
    """Stores and retrieves options.  Intended to be inherited."""

    def __init__(self, opts: list[str]) -> None:
        """Parse and store options as a list of tuples."""
        self.pairs: list[tuple[str, str]] = []
        for o in opts if opts else []:
            k, v = o.split("=", 1)
            self.pairs.append((k, v))

    def getopt(self, p: str, default: Optional[str] = None) -> Optional[str]:
        """Returns the first option value stored that matches p or default."""
        for k, v in self.pairs:
            if k == p:
                return v
        return default

    def getoptlist(self, p: str) -> list[str]:
        """Returns all option values stored that match p as a list."""
        optlist = []
        for k, v in self.pairs:
            if k == p:
                optlist.append(v)
        return optlist

    def log_for_run(self, run_id: Optional[str], message: str) -> None:
        """Report the log for a given run."""
        logging.info("Workflow %s: %s", run_id, message)

    def collect_attachments(
        self, run_id: Optional[str] = None
    ) -> tuple[str, dict[str, str]]:
        """Stage all attachments to a temporary directory."""
        tempdir = tempfile.mkdtemp()
        body: dict[str, str] = {}
        has_attachments = False
        for k, ls in connexion.request.files.lists():
            try:
                for v in ls:
                    if k == "workflow_attachment":
                        sp = v.filename.split("/")
                        fn = []
                        for p in sp:
                            if p not in ("", ".", ".."):
                                fn.append(secure_filename(p))
                        dest = os.path.join(tempdir, *fn)
                        if not os.path.isdir(os.path.dirname(dest)):
                            os.makedirs(os.path.dirname(dest))
                        self.log_for_run(
                            run_id,
                            f"Staging attachment {v.filename!r} to {dest!r}",
                        )
                        v.save(dest)
                        has_attachments = True
                        body[k] = (
                            "file://%s" % tempdir
                        )  # Reference to temp working dir.
                    elif k in ("workflow_params", "tags", "workflow_engine_parameters"):
                        content = v.read()
                        body[k] = json.loads(content.decode("utf-8"))
                    else:
                        body[k] = v.read().decode()
            except Exception as e:
                raise ValueError(f"Error reading parameter {k!r}: {e}") from e
        for k, ls in connexion.request.form.lists():
            try:
                for v in ls:
                    if not v:
                        continue
                    if k in ("workflow_params", "tags", "workflow_engine_parameters"):
                        body[k] = json.loads(v)
                    else:
                        body[k] = v
            except Exception as e:
                raise ValueError(f"Error reading parameter {k!r}: {e}") from e

        if "workflow_url" in body:
            if ":" not in body["workflow_url"]:
                if not has_attachments:
                    raise ValueError(
                        "Relative 'workflow_url' but missing 'workflow_attachment'"
                    )
                body["workflow_url"] = "file://%s" % os.path.join(
                    tempdir, secure_filename(body["workflow_url"])
                )
            self.log_for_run(
                run_id, "Using workflow_url '%s'" % body.get("workflow_url")
            )
        else:
            raise ValueError("Missing 'workflow_url' in submission")

        if "workflow_params" not in body:
            raise ValueError("Missing 'workflow_params' in submission")

        return tempdir, body
