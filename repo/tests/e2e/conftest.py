import os
import socket
import threading
import time

import pytest

from app import create_app


def _find_free_port() -> int:
    """Bind to port 0 to get an OS-assigned free port, then release it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_app():
    """Spin up a real Flask dev server on a random free port for E2E tests."""
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    os.environ.setdefault("SECRET_KEY", "e2e-test-secret")
    app = create_app("testing")

    port = _find_free_port()
    app.config["E2E_PORT"] = port

    def run():
        app.run(host="127.0.0.1", port=port, use_reloader=False, threaded=True)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    time.sleep(1.5)
    yield app


@pytest.fixture(scope="session")
def base_url(live_app):
    port = live_app.config["E2E_PORT"]
    return f"http://127.0.0.1:{port}"
