"""
Print the entire tree structure of a document, for eyeballing during testing.

Deliberately NOT a new API endpoint. It's built entirely on top of the
existing Browse API (GET /sections + GET /nodes/{id}), calling them
recursively client-side. The assignment's Browse API only requires
"list top-level sections" and "get a node + its immediate children" --
recursively walking the whole tree in one shot isn't something a reviewer
asked for, so it lives here as a dev convenience instead of adding scope
to the graded API surface.

Usage (server must already be running: uvicorn app.main:app --reload):

    python scratch/print_tree.py ct200_manual
    python scratch/print_tree.py ct200_manual --version 1
    python scratch/print_tree.py ct200_manual --host http://127.0.0.1:8000
"""
import argparse
import sys
import requests


def fetch_top_level(host, doc, version):
    params = {"version": version} if version is not None else {}
    r = requests.get(f"{host}/documents/{doc}/sections", params=params)
    r.raise_for_status()
    return r.json()


def fetch_node(host, doc, node_id, version):
    params = {"version": version} if version is not None else {}
    r = requests.get(f"{host}/documents/{doc}/nodes/{node_id}", params=params)
    r.raise_for_status()
    return r.json()


def print_node(host, doc, node, version, depth=0):
    prefix = "  " * depth
    number = f"{node['heading_number']} " if node.get("heading_number") else ""
    print(f"{prefix}- [{node['node_id']}] {number}{node['heading_text']}")

    # /sections gives shallow entries (no children field); /nodes/{id}
    # gives one level of children. Recurse by re-fetching each child node.
    full = fetch_node(host, doc, node["node_id"], version)
    for child in full.get("children", []):
        print_node(host, doc, child, version, depth + 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document_name")
    parser.add_argument("--version", type=int, default=None,
                         help="Version number (default: latest)")
    parser.add_argument("--host", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    try:
        top_level = fetch_top_level(args.host, args.document_name, args.version)
    except requests.exceptions.ConnectionError:
        print(f"Could not reach {args.host} -- is `uvicorn app.main:app --reload` running?")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"Request failed: {e}")
        sys.exit(1)

    if not top_level:
        print(f"No sections found for document '{args.document_name}'"
              f"{' at version ' + str(args.version) if args.version else ''}."
              " Has it been ingested yet?")
        sys.exit(1)

    label = f"version {args.version}" if args.version else "latest version"
    print(f"{args.document_name} ({label})")
    print("=" * 60)
    for node in top_level:
        print_node(args.host, args.document_name, node, args.version)


if __name__ == "__main__":
    main()
