from html.parser import HTMLParser
from urllib.parse import urlsplit

from cmfgen_viewer.app import create_app
from cmfgen_viewer.documentation import MENU_ORDER, discover_docs, render_document


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.extend(value for key, value in attrs if key == "href" and value)


def test_documentation_menu_and_reference_routes(tmp_path):
    app = create_app(basepath=str(tmp_path))
    client = app.test_client()
    docs = discover_docs()
    assert tuple(doc["slug"] for doc in docs if doc["in_menu"]) == MENU_ORDER
    assert len([doc for doc in docs if not doc["in_menu"]]) == 5
    assert client.get("/documentation/").headers["Location"].endswith("/documentation/getting-started")

    response = client.get("/documentation/getting-started")
    parser = Links()
    parser.feed(response.get_data(as_text=True))
    menu_links = [href for href in parser.hrefs if href.startswith("/documentation/")]
    assert not any("/reference/" in href for href in menu_links)
    for doc in docs:
        assert client.get("/documentation/" + doc["slug"]).status_code == 200

    reference = client.get("/documentation/reference/cmfgen-input-files")
    assert b"\xe2\x86\x90 File reference" in reference.data
    for slug in ["developer/parser-implementation-queue", "developer/runner-smoke-tests", "../README", "cmfgen-workflow-plans"]:
        assert client.get("/documentation/" + slug).status_code == 404


def test_rendered_documentation_links_resolve(tmp_path):
    client = create_app(basepath=str(tmp_path)).test_client()
    for doc in discover_docs():
        html, _ = render_document(doc["path"])
        parser = Links()
        parser.feed(str(html))
        for href in parser.hrefs:
            url = urlsplit(href)
            if url.scheme or url.netloc or not url.path:
                continue
            assert url.path.startswith("/documentation/"), (doc["slug"], href)
            response = client.get(url.path)
            assert response.status_code == 200, (doc["slug"], href)
            if url.fragment:
                assert f'id="{url.fragment}"' in response.get_data(as_text=True), (doc["slug"], href)


def test_main_computation_lists_every_automatic_policy(tmp_path):
    from cmfgen_viewer.auto_policies import manifest

    response = create_app(basepath=str(tmp_path)).test_client().get('/documentation/main-computation')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="automatic-convergence-and-recovery-rules"' in html
    for policy in manifest():
        assert f"<code>{policy['id']}</code>" in html, policy['id']
    assert '<code>continue</code>' in html and '<code>unhandled</code>' in html
