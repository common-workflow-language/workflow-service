import argparse
import requests

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--upload", action="store_true")
    parser.add_argument("endpoint")
    parser.add_argument("object")

    args = parser.parse_args()

    if args.upload:
        r = requests.put(args.endpoint)
    else:
        r = requests.post(args.endpoint)

if __name__ == "__main__":
    main()
