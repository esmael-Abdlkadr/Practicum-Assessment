def test_get_cohorts_page_returns_200_for_authenticated_user(client, admin_user):
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    res = client.get("/cohorts")
    assert res.status_code == 200


def test_get_cohorts_page_redirects_for_unauthenticated_user(client):
    res = client.get("/cohorts", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers.get("Location", "")
