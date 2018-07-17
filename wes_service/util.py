from six import itervalues


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
