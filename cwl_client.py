import argparse
import requests
import urlparse
import os

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

    with open(args.item) as f:
        data = f.read()

    if args.upload:
        dest = urlparse.urljoin(args.endpoint, os.path.basename(args.item))
        r = requests.put(dest, data=data)
    else:
        r = requests.post(args.endpoint, data=data)

    print r.text


if __name__ == "__main__":
    main()
