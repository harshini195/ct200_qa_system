"""
View the document tree in a browser instead of the terminal.

This runs its OWN tiny local web server (separate from your FastAPI app)
on port 8001. It fetches the tree server-side using the same recursive
calls as print_tree.py, then renders a plain HTML page. Opening a browser
tab that fetches http://127.0.0.1:8000 directly would get blocked by
CORS (your FastAPI app doesn't send Access-Control-Allow-Origin headers,
and deliberately isn't being changed to -- see print_tree.py's docstring
for why the API surface itself stays untouched). Doing the fetch here,
server-side, sidesteps that entirely.

Usage:
    # In one terminal: your actual app
    uvicorn app.main:app --reload

    # In another terminal: this viewer
    python scratch/tree_view_server.py

    Then open http://127.0.0.1:8001/?document=ct200_manual in a browser.
    Add &version=1 to view a specific version instead of latest.
"""
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from html import escape
import requests

API_HOST = "http://127.0.0.1:8000"
VIEWER_PORT = 8001


def fetch_top_level(doc, version):
    params = {"version": version} if version is not None else {}
    r = requests.get(f"{API_HOST}/documents/{doc}/sections", params=params)
    r.raise_for_status()
    return r.json()


def fetch_node(doc, node_id, version):
    params = {"version": version} if version is not None else {}
    r = requests.get(f"{API_HOST}/documents/{doc}/nodes/{node_id}", params=params)
    r.raise_for_status()
    return r.json()


def render_node(doc, node, version):
    number = escape(node["heading_number"] + " ") if node.get("heading_number") else ""
    label = f"<code>[{node['node_id']}]</code> {number}{escape(node['heading_text'])}"

    full = fetch_node(doc, node["node_id"], version)
    children = full.get("children", [])
    if not children:
        return f"<li>{label}</li>"

    child_html = "".join(render_node(doc, c, version) for c in children)
    return f"<li>{label}<ul>{child_html}</ul></li>"


def render_page(doc, version):
    try:
        top_level = fetch_top_level(doc, version)
    except requests.exceptions.ConnectionError:
        return (f"<p>Could not reach {escape(API_HOST)} -- is "
                f"<code>uvicorn app.main:app --reload</code> running?</p>", 502)
    except requests.exceptions.HTTPError as e:
        return f"<p>Request failed: {escape(str(e))}</p>", e.response.status_code

    if not top_level:
        return (f"<p>No sections found for '{escape(doc)}'"
                f"{' at version ' + str(version) if version else ''}. "
                f"Has it been ingested yet?</p>", 404)

    label = f"version {version}" if version else "latest version"
    items = "".join(render_node(doc, n, version) for n in top_level)
    body = f"""
    <h1>{escape(doc)}</h1>
    <p style="color:#666">{escape(label)}</p>
    <ul>{items}</ul>
    """
    return body, 200


PAGE_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{doc} - tree view</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 700px; margin: 40px auto; padding: 0 20px; }}
  ul {{ list-style: none; border-left: 1px solid #ddd; margin: 4px 0 4px 8px; padding-left: 16px; }}
  li {{ margin: 6px 0; }}
  code {{ color: #888; font-size: 0.85em; }}
  form {{ margin-bottom: 24px; }}
  input {{ padding: 6px 10px; font-size: 14px; }}
  button {{ padding: 6px 14px; font-size: 14px; }}
</style>
</head>
<body>
<form method="get">
  <input name="document" placeholder="document_name" value="{doc}">
  <input name="version" placeholder="version (blank = latest)" value="{version}">
  <button type="submit">Load tree</button>
</form>
{content}
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep terminal quiet

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        doc = query.get("document", [""])[0]
        version_raw = query.get("version", [""])[0]
        version = int(version_raw) if version_raw.strip().isdigit() else None

        if not doc:
            content, status = "<p>Enter a document name above and click Load tree.</p>", 200
        else:
            content, status = render_page(doc, version)

        html = PAGE_TEMPLATE.format(
            doc=escape(doc), version=escape(version_raw), content=content
        )
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))


def main():
    print(f"Tree viewer running at http://127.0.0.1:{VIEWER_PORT}/")
    print(f"(fetching from your API at {API_HOST} -- make sure it's running)")
    try:
        HTTPServer(("127.0.0.1", VIEWER_PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
