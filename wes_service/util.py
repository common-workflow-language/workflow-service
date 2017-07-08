def visit(d, op):
    op(d)
    if isinstance(d, list):
        for i in d:
            visit(i, op)
    elif isinstance(d, dict):
        for i in d.itervalues():
            visit(i, op)

class WESBackend(object):
    def __init__(self, opts):
        self.pairs = []
        for o in opts:
            k, v = o.split("=", 1)
            self.pairs.append((k, v))

    def getopt(self, p, default=None):
        for k,v in self.pairs:
            if k == p:
                return v
        return default

    def getoptlist(self, p):
        l = []
        for k, v in self.pairs:
            if k == p:
                l.append(v)
        return l
