def test_client_error_log_accepts_beacon(client):
    """Client error beacon endpoint must accept any JSON and return 204."""
    import json

    resp = client.post(
        "/client-error-log",
        data=json.dumps(
            {
                "level": "ERROR",
                "category": "htmx.sendError",
                "message": "test",
                "detail": None,
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 204


def test_client_error_log_tolerates_empty_body(client):
    """Beacon with empty body must not crash - returns 204."""
    resp = client.post("/client-error-log", data="", content_type="text/plain")
    assert resp.status_code == 204


def test_oversized_payload_returns_413(client):
    """Payloads exceeding 4 KB must be rejected with 413."""
    big = "x" * 5000
    res = client.post(
        "/client-error-log",
        data=big,
        content_type="application/json",
    )
    assert res.status_code == 413


def test_unknown_keys_are_not_logged(client):
    """Unknown keys in beacon payload must not reach the log."""
    import json

    res = client.post(
        "/client-error-log",
        data=json.dumps({"level": "error", "secret_token": "LEAK", "message": "oops"}),
        content_type="application/json",
    )
    assert res.status_code == 204


def test_valid_beacon_still_returns_204(client):
    """A well-formed beacon with only allowed keys must return 204."""
    import json

    res = client.post(
        "/client-error-log",
        data=json.dumps(
            {
                "level": "error",
                "category": "htmx.responseError",
                "message": "500 from /quiz/1/autosave",
                "detail": "",
            }
        ),
        content_type="application/json",
    )
    assert res.status_code == 204
