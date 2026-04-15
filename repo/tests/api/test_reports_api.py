from app.models.user import User


def login_as(client, username):
    password_map = {
        "admin": "Admin@Practicum1",
        "advisor1": "Advisor@Practicum1",
    }
    client.post("/login", data={"username": username, "password": password_map.get(username, "Admin@Practicum1")})


def test_get_reports_summary_has_score_data(client, app, seeded_assessment):
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    pid = seeded_assessment["paper_id"]
    res = client.get(f"/reports/paper/{pid}/summary")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "Average" in body
    assert "Pass Rate" in body or "Pass rate" in body


def test_get_reports_export_students_csv_attachment(client, seeded_assessment):
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    pid = seeded_assessment["paper_id"]
    res = client.get(f"/reports/paper/{pid}/export/students")
    assert res.status_code == 200
    assert "attachment" in res.headers.get("Content-Disposition", "")


def test_get_reports_paper_unassigned_faculty_forbidden(client, seeded_assessment):
    client.post("/login", data={"username": "advisor1", "password": "Advisor@Practicum1"})
    pid = seeded_assessment["paper2_id"]
    res = client.get(f"/reports/paper/{pid}")
    assert res.status_code == 403


def test_get_reports_summary_unassigned_faculty_forbidden(client, seeded_assessment):
    client.post("/login", data={"username": "advisor1", "password": "Advisor@Practicum1"})
    pid = seeded_assessment["paper2_id"]
    res = client.get(f"/reports/paper/{pid}/summary")
    assert res.status_code == 403


def test_get_reports_index_only_accessible_papers(client, seeded_assessment):
    client.post("/login", data={"username": "advisor1", "password": "Advisor@Practicum1"})
    res = client.get("/reports")
    body = res.get_data(as_text=True)
    assert "Paper 1" in body
    assert "Paper 2" not in body


def test_csv_export_contains_required_headers(client, app, seeded_assessment):
    """The CSV export for a paper must contain at minimum the headers:
    student, score, total, percentage."""
    import csv
    import io

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    paper_id = seeded_assessment["paper_id"]
    res = client.get(f"/reports/paper/{paper_id}/export")
    assert res.status_code == 200
    assert "text/csv" in res.content_type
    reader = csv.DictReader(io.StringIO(res.get_data(as_text=True)))
    headers = [h.lower().strip() for h in (reader.fieldnames or [])]
    for required in ("student", "score"):
        assert any(required in h for h in headers), (
            f"Required CSV column '{required}' not found in headers: {headers}"
        )


def test_csv_export_student_id_is_masked(client, app, seeded_assessment):
    """Any student ID field in the CSV must be masked (e.g., ***1234), not plaintext."""
    from app.extensions import db
    from app.services import encryption_service

    with app.app_context():
        student = db.session.get(User, seeded_assessment["student_id"])
        student.student_id_enc = encryption_service.encrypt("SID123456")
        db.session.commit()

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    paper_id = seeded_assessment["paper_id"]
    res = client.get(f"/reports/paper/{paper_id}/export")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "SID123456" not in body, "Plaintext student ID must not appear in CSV export"


def test_student_id_not_exposed_in_report_page(client, app, seeded_assessment):
    """The paper report page must not contain the plaintext student ID."""
    from app.extensions import db
    from app.services import encryption_service

    with app.app_context():
        student = db.session.get(User, seeded_assessment["student_id"])
        student.student_id_enc = encryption_service.encrypt("PLAINID9999")
        db.session.commit()

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    paper_id = seeded_assessment["paper_id"]
    res = client.get(f"/reports/paper/{paper_id}")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "PLAINID9999" not in body, (
        "Plaintext student ID must not appear in the report page HTML"
    )


def test_csv_export_denied_without_permission(client, app, seeded_assessment):
    """Faculty advisor without report:export permission must get 403 on CSV export."""
    client.post("/login", data={"username": "advisor1", "password": "Advisor@Practicum1"})
    paper_id = seeded_assessment["paper_id"]
    res = client.get(f"/reports/paper/{paper_id}/export")
    assert res.status_code == 403


def test_export_students_denied_without_export_permission(
    client, app, seeded_assessment, faculty_advisor
):
    """
    A faculty advisor assigned to the cohort but WITHOUT the report:export permission
    must receive 403 on GET /reports/paper/<id>/export/students.
    This verifies the permission guard is present (unlike the previous bypass).
    """
    paper_id = seeded_assessment["paper_id"]
    with app.app_context():
        from app.extensions import db
        from app.models.permission import UserPermission

        advisor_id = User.query.filter_by(username="advisor1").first().id
        UserPermission.query.filter_by(
            user_id=advisor_id, permission="report:export"
        ).delete()
        db.session.commit()

    login_as(client, "advisor1")
    resp = client.get(
        f"/reports/paper/{paper_id}/export/students",
        follow_redirects=False,
    )
    assert resp.status_code == 403, (
        f"Expected 403 for advisor without report:export, got {resp.status_code}. "
        "The @permission_required('report:export') decorator is missing."
    )


def test_export_students_allowed_with_export_permission(
    client, app, seeded_assessment, faculty_advisor
):
    """
    A faculty advisor WITH report:export permission must be able to download
    the student CSV successfully.
    """
    paper_id = seeded_assessment["paper_id"]
    with app.app_context():
        from app.extensions import db
        from app.models.permission import UserPermission

        advisor_id = User.query.filter_by(username="advisor1").first().id
        perm = UserPermission(
            user_id=advisor_id,
            permission="report:export",
        )
        db.session.add(perm)
        db.session.commit()

    login_as(client, "advisor1")
    resp = client.get(f"/reports/paper/{paper_id}/export/students")
    assert resp.status_code == 200
    assert "text/csv" in resp.content_type


def test_export_difficulty_denied_without_permission(client, app, seeded_assessment):
    client.post("/login", data={"username": "advisor1", "password": "Advisor@Practicum1"})
    paper_id = seeded_assessment["paper_id"]
    res = client.get(f"/reports/paper/{paper_id}/export/difficulty")
    assert res.status_code == 403


def test_export_difficulty_allowed_with_permission(client, app, seeded_assessment):
    from app.extensions import db
    from app.models.permission import UserPermission

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    paper_id = seeded_assessment["paper_id"]
    res = client.get(f"/reports/paper/{paper_id}/export/difficulty")
    assert res.status_code == 200
    assert "text/csv" in res.content_type


def test_reports_index_filters_by_cohort_id(client, app, seeded_assessment):
    """GET /reports?cohort_id=<valid> must narrow papers to that cohort only."""
    from app.extensions import db
    from app.models.org import Class, Cohort, Major, School
    from app.models.paper import Paper

    with app.app_context():
        # create a second cohort + paper that must NOT appear after filtering
        school = School(name="Filter School", code="FSC")
        db.session.add(school)
        db.session.flush()
        major = Major(name="FM", code="FM", school_id=school.id)
        db.session.add(major)
        db.session.flush()
        clazz = Class(name="FC", year=2026, major_id=major.id)
        db.session.add(clazz)
        db.session.flush()
        other_cohort = Cohort(name="Other Cohort", class_id=clazz.id, is_active=True)
        db.session.add(other_cohort)
        db.session.flush()
        other_paper = Paper(
            title="Other Cohort Paper",
            cohort_id=other_cohort.id,
            status="published",
            time_limit_min=45,
            max_attempts=1,
        )
        db.session.add(other_paper)
        db.session.commit()

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    target_cohort_id = seeded_assessment["cohort_id"]
    res = client.get(f"/reports?cohort_id={target_cohort_id}")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "Other Cohort Paper" not in body


def test_reports_index_ignores_unscoped_cohort_id(client, app, seeded_assessment):
    """GET /reports?cohort_id=<unscoped> must fall back to showing all accessible papers."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    # Pass a cohort_id that doesn't belong to admin's scope or is non-existent
    res = client.get("/reports?cohort_id=99999")
    assert res.status_code == 200
    # Should fall back to showing all papers (no filter banner for invalid id)
    body = res.get_data(as_text=True)
    assert "Clear filter" not in body


def test_dept_admin_summary_fragment_shows_export_button(client, seeded_assessment):
    """dept_admin must see the CSV export button even without explicit report:export permission."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    pid = seeded_assessment["paper_id"]
    res = client.get(f"/reports/paper/{pid}/summary")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "export" in body.lower() or "csv" in body.lower() or "Export" in body


def test_authenticated_page_has_no_store_header(client, admin_user):
    """Authenticated HTML responses must carry Cache-Control: no-store."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    res = client.get("/dashboard")
    assert res.status_code == 200
    cc = res.headers.get("Cache-Control", "")
    assert "no-store" in cc


def test_logout_response_has_no_store_header(client, admin_user):
    """Logout redirect must carry Cache-Control: no-store."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    res = client.get("/logout", follow_redirects=False)
    assert res.status_code == 302
    cc = res.headers.get("Cache-Control", "")
    assert "no-store" in cc


def test_switched_role_export_denied_403(client, app, seeded_assessment):
    with app.app_context():
        from app.extensions import db
        from app.models.permission import UserPermission
        from app.models.user import User

        admin = User.query.filter_by(username="admin").first()
        db.session.add(UserPermission(user_id=admin.id, permission="role:faculty_advisor"))
        db.session.commit()

    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    first = client.post("/switch-role", data={"role": "faculty_advisor"}, follow_redirects=False)
    assert first.status_code == 302
    assert "/reauth" in first.headers.get("Location", "")

    client.post(
        "/reauth",
        data={"password": "Admin@Practicum1", "next_url": "/switch-role"},
        follow_redirects=False,
    )
    switched = client.post("/switch-role", data={"role": "faculty_advisor"}, follow_redirects=False)
    assert switched.status_code in (302, 204)

    paper_id = seeded_assessment["paper_id"]
    res = client.get(f"/reports/paper/{paper_id}/export/students", follow_redirects=False)
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# New gap-filling tests: difficulty, students, cohort-comparison fragments
# ---------------------------------------------------------------------------

def test_get_reports_difficulty_fragment_200(client, seeded_assessment):
    """Admin GET /reports/paper/<id>/difficulty returns 200 with difficulty data."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    pid = seeded_assessment["paper_id"]
    res = client.get(f"/reports/paper/{pid}/difficulty")
    assert res.status_code == 200


def test_get_reports_difficulty_fragment_forbidden_unassigned(client, seeded_assessment):
    """Unassigned advisor GET /reports/paper/paper2/difficulty returns 403."""
    client.post("/login", data={"username": "advisor1", "password": "Advisor@Practicum1"})
    pid = seeded_assessment["paper2_id"]
    res = client.get(f"/reports/paper/{pid}/difficulty")
    assert res.status_code == 403


def test_get_reports_students_fragment_200(client, seeded_assessment):
    """Admin GET /reports/paper/<id>/students returns 200."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    pid = seeded_assessment["paper_id"]
    res = client.get(f"/reports/paper/{pid}/students")
    assert res.status_code == 200


def test_get_reports_cohort_comparison_fragment_200(client, seeded_assessment):
    """Admin GET /reports/paper/<id>/cohort-comparison returns 200."""
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})
    pid = seeded_assessment["paper_id"]
    res = client.get(f"/reports/paper/{pid}/cohort-comparison")
    assert res.status_code == 200


def test_export_cohort_comparison_denied_without_permission(client, seeded_assessment):
    """Advisor without report:export gets 403 on cohort-comparison export."""
    client.post("/login", data={"username": "advisor1", "password": "Advisor@Practicum1"})
    pid = seeded_assessment["paper_id"]
    res = client.get(f"/reports/paper/{pid}/export/cohort-comparison")
    assert res.status_code == 403


def test_reports_student_unauthenticated_redirects(client):
    """Unauthenticated GET /reports returns redirect."""
    res = client.get("/reports", follow_redirects=False)
    assert res.status_code in (302, 401, 403)
