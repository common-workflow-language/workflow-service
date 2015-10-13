import argparse
import requests
import urlparse
import os
import yaml

def search_refs(item, base):
    r = []
    if isinstance(item, dict):
        for i in ("@import", "import"):
            if i in item:
                r.extend(discover_refs(item[i], base))

        for i in ("@include", "include"):
            if i in item:
                with open(item[i]) as f:
                    data = f.read()
                r.append((item[i], data))

        for v in item.values():
            r.extend(search_refs(v, base))

    elif isinstance(item, list):
        for a in item:
            r.extend(search_refs(a, base))

    return r

def discover_refs(item, base):
    item = os.path.join(base, item)
    with open(item) as f:
        data = f.read()
    r = [(item, data)]
    r.extend(search_refs(yaml.load(data), os.path.dirname(item)))
    return r

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--upload", action="store_true", help="Upload new CWL tool or workflow.")
    parser.add_argument("endpoint")
    parser.add_argument("item", nargs="?")

    args = parser.parse_args()

    if not args.item:
        r = requests.get(args.endpoint)
        print r.text
        return

    if args.upload:
        (dr, fn) = os.path.split(args.item)
        plan = discover_refs(fn, dr)
        for p in plan:
            dest = urlparse.urljoin(args.endpoint, p[0][len(dr):].lstrip('/'))
            r = requests.put(dest, data=p[1])
            print r.text
    else:
        with open(args.item) as f:
            data = f.read()
        r = requests.post(args.endpoint, data=data)
        print r.text


if __name__ == "__main__":
    main()
