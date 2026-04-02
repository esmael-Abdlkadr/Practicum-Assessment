import os


VENDOR_DIR = os.path.join(os.path.dirname(__file__), "../../app/static/vendor")


def test_htmx_is_real_library():
    path = os.path.join(VENDOR_DIR, "htmx/htmx.min.js")
    assert os.path.exists(path), "htmx.min.js not found"
    content = open(path).read()
    assert len(content) > 40_000, "htmx.min.js looks like a stub (too small)"
    assert "htmx" in content.lower(), "htmx.min.js does not contain 'htmx'"
    assert "window.htmx = window.htmx || {};" not in content, "htmx.min.js is still the placeholder stub"


def test_bootstrap_bundle_is_real_library():
    path = os.path.join(VENDOR_DIR, "bootstrap/bootstrap.bundle.min.js")
    assert os.path.exists(path), "bootstrap.bundle.min.js not found"
    content = open(path).read()
    assert len(content) > 60_000, "bootstrap.bundle.min.js looks like a stub"


def test_bootstrap_css_is_real_library():
    path = os.path.join(VENDOR_DIR, "bootstrap/bootstrap.min.css")
    assert os.path.exists(path), "bootstrap.min.css not found"
    content = open(path).read()
    assert len(content) > 150_000, "bootstrap.min.css looks like a stub"
