"""API tests for Org CRUD: School / Major / Class / Cohort endpoints."""
import pytest

from app.extensions import db
from app.models.org import Class, Cohort, Major, School


def login_admin(client):
    client.post("/login", data={"username": "admin", "password": "Admin@Practicum1"})


# ---------------------------------------------------------------------------
# School
# ---------------------------------------------------------------------------

def test_create_school_success(client, admin_user):
    login_admin(client)
    res = client.post(
        "/admin/org/schools",
        data={"name": "Engineering School", "code": "ENG"},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    assert b"Engineering School" in res.data


def test_create_school_missing_name_400(client, admin_user):
    login_admin(client)
    res = client.post(
        "/admin/org/schools",
        data={"name": "", "code": "XX"},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 400


def test_create_school_unauthenticated_redirects(client):
    res = client.post(
        "/admin/org/schools",
        data={"name": "School X"},
        follow_redirects=False,
    )
    assert res.status_code in (302, 401, 403)


def test_update_school_success(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        school = School(name="Old Name", code="ON", is_active=True)
        db.session.add(school)
        db.session.commit()
        sid = school.id

    res = client.put(
        f"/admin/org/schools/{sid}",
        data={"name": "New Name"},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    assert b"New Name" in res.data


def test_delete_school_soft_deletes(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        school = School(name="Del School", code="DS", is_active=True)
        db.session.add(school)
        db.session.commit()
        sid = school.id

    res = client.delete(
        f"/admin/org/schools/{sid}",
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    with app.app_context():
        s = db.session.get(School, sid)
        assert s.is_active is False


# ---------------------------------------------------------------------------
# Major
# ---------------------------------------------------------------------------

def test_create_major_success(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        school = School(name="Sci", code="SC", is_active=True)
        db.session.add(school)
        db.session.commit()
        sid = school.id

    res = client.post(
        "/admin/org/majors",
        data={"name": "Computer Science", "code": "CS", "school_id": sid},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    assert b"Computer Science" in res.data


def test_delete_major_removes_record(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        school = School(name="Sci2", code="SC2", is_active=True)
        db.session.add(school)
        db.session.flush()
        major = Major(name="Math", code="MT", school_id=school.id)
        db.session.add(major)
        db.session.commit()
        mid = major.id

    res = client.delete(
        f"/admin/org/majors/{mid}",
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    with app.app_context():
        assert db.session.get(Major, mid) is None


# ---------------------------------------------------------------------------
# Class
# ---------------------------------------------------------------------------

def test_create_class_success(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        school = School(name="Sci3", code="SC3", is_active=True)
        db.session.add(school)
        db.session.flush()
        major = Major(name="Physics", code="PH", school_id=school.id)
        db.session.add(major)
        db.session.commit()
        mid = major.id

    res = client.post(
        "/admin/org/classes",
        data={"name": "Class 2026", "year": "2026", "major_id": mid},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200


def test_create_class_invalid_year_400(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        school = School(name="Sci4", code="SC4", is_active=True)
        db.session.add(school)
        db.session.flush()
        major = Major(name="Bio", code="BI", school_id=school.id)
        db.session.add(major)
        db.session.commit()
        mid = major.id

    res = client.post(
        "/admin/org/classes",
        data={"name": "Class X", "year": "not-a-year", "major_id": mid},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# Cohort
# ---------------------------------------------------------------------------

def test_create_cohort_success(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        school = School(name="SciCo", code="SCO", is_active=True)
        db.session.add(school)
        db.session.flush()
        major = Major(name="Chem", code="CH", school_id=school.id)
        db.session.add(major)
        db.session.flush()
        clazz = Class(name="Chem 2026", year=2026, major_id=major.id)
        db.session.add(clazz)
        db.session.commit()
        cid = clazz.id

    res = client.post(
        "/admin/org/cohorts",
        data={"name": "Spring 2026", "internship_term": "2026 Spring", "class_id": cid},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    assert b"Spring 2026" in res.data


def test_create_cohort_invalid_start_date_400(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        school = School(name="SciBadStart", code="SBS", is_active=True)
        db.session.add(school)
        db.session.flush()
        major = Major(name="ChemStart", code="CS", school_id=school.id)
        db.session.add(major)
        db.session.flush()
        clazz = Class(name="Chem Start", year=2026, major_id=major.id)
        db.session.add(clazz)
        db.session.commit()
        cid = clazz.id

    res = client.post(
        "/admin/org/cohorts",
        data={
            "name": "Start Bad Cohort",
            "internship_term": "2026 Spring",
            "class_id": cid,
            "start_date": "not-a-date",
        },
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 400


def test_create_cohort_invalid_end_date_400(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        school = School(name="SciBadEnd", code="SBE", is_active=True)
        db.session.add(school)
        db.session.flush()
        major = Major(name="ChemEnd", code="CE", school_id=school.id)
        db.session.add(major)
        db.session.flush()
        clazz = Class(name="Chem End", year=2026, major_id=major.id)
        db.session.add(clazz)
        db.session.commit()
        cid = clazz.id

    res = client.post(
        "/admin/org/cohorts",
        data={
            "name": "End Bad Cohort",
            "internship_term": "2026 Spring",
            "class_id": cid,
            "end_date": "bad",
        },
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 400


def test_delete_cohort_soft_deletes(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        school = School(name="SciDel", code="SDL", is_active=True)
        db.session.add(school)
        db.session.flush()
        major = Major(name="Eng", code="EN", school_id=school.id)
        db.session.add(major)
        db.session.flush()
        clazz = Class(name="Eng 26", year=2026, major_id=major.id)
        db.session.add(clazz)
        db.session.flush()
        cohort = Cohort(name="Del Cohort", class_id=clazz.id, internship_term="T1", is_active=True)
        db.session.add(cohort)
        db.session.commit()
        coid = cohort.id

    res = client.delete(
        f"/admin/org/cohorts/{coid}",
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    with app.app_context():
        co = db.session.get(Cohort, coid)
        assert co.is_active is False


def test_add_cohort_member_invalid_role_400(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        from app.models.user import User as _User
        admin_db = _User.query.filter_by(username="admin").first()
        admin_id = admin_db.id

        school = School(name="SciM", code="SM", is_active=True)
        db.session.add(school)
        db.session.flush()
        major = Major(name="IT", code="IT", school_id=school.id)
        db.session.add(major)
        db.session.flush()
        clazz = Class(name="IT 26", year=2026, major_id=major.id)
        db.session.add(clazz)
        db.session.flush()
        cohort = Cohort(name="IT Cohort", class_id=clazz.id, internship_term="T2", is_active=True)
        db.session.add(cohort)
        db.session.commit()
        coid = cohort.id

    res = client.post(
        f"/admin/org/cohorts/{coid}/members",
        data={"user_id": admin_id, "role_in_cohort": "invalid_role"},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# Blank-name validation for major / class / cohort
# ---------------------------------------------------------------------------

def test_create_major_blank_name_400(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        school = School(name="Blank Test School", code="BTS")
        db.session.add(school)
        db.session.commit()
        sid = school.id

    res = client.post(
        "/admin/org/majors",
        data={"school_id": sid, "name": ""},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 400


def test_create_class_blank_name_400(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        school = School(name="Blank School 2", code="BS2")
        db.session.add(school)
        db.session.flush()
        major = Major(name="BM", code="BM", school_id=school.id)
        db.session.add(major)
        db.session.commit()
        mid = major.id

    res = client.post(
        "/admin/org/classes",
        data={"major_id": mid, "name": ""},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 400


def test_create_cohort_blank_name_400(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        school = School(name="Blank School 3", code="BS3")
        db.session.add(school)
        db.session.flush()
        major = Major(name="BM3", code="BM3", school_id=school.id)
        db.session.add(major)
        db.session.flush()
        clazz = Class(name="BC3", year=2026, major_id=major.id)
        db.session.add(clazz)
        db.session.commit()
        cid = clazz.id

    res = client.post(
        "/admin/org/cohorts",
        data={"class_id": cid, "name": ""},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# Major update
# ---------------------------------------------------------------------------

def test_update_major_success(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        school = School(name="UpdMajorSchool", code="UMS")
        db.session.add(school)
        db.session.flush()
        major = Major(name="Old Major", code="OM", school_id=school.id)
        db.session.add(major)
        db.session.commit()
        mid = major.id

    res = client.put(
        f"/admin/org/majors/{mid}",
        data={"name": "Updated Major", "code": "UM2"},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    assert b"Updated Major" in res.data


def test_update_major_student_forbidden(client, app, student_user):
    client.post("/login", data={"username": "student1", "password": "Student@Practicum1"})
    res = client.put("/admin/org/majors/1", data={"name": "Hack"}, follow_redirects=False)
    assert res.status_code in (302, 403)


# ---------------------------------------------------------------------------
# Class update / delete
# ---------------------------------------------------------------------------

def test_update_class_success(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        school = School(name="UpdClsSchool", code="UCS")
        db.session.add(school)
        db.session.flush()
        major = Major(name="UpdClsMajor", code="UCM", school_id=school.id)
        db.session.add(major)
        db.session.flush()
        clazz = Class(name="Old Class", year=2025, major_id=major.id)
        db.session.add(clazz)
        db.session.commit()
        cid = clazz.id

    res = client.put(
        f"/admin/org/classes/{cid}",
        data={"name": "Updated Class", "year": "2027"},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    assert b"Updated Class" in res.data


def test_delete_class_removes_record(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        school = School(name="DelClsSchool", code="DCS")
        db.session.add(school)
        db.session.flush()
        major = Major(name="DelClsMajor", code="DCM", school_id=school.id)
        db.session.add(major)
        db.session.flush()
        clazz = Class(name="Del Class", year=2026, major_id=major.id)
        db.session.add(clazz)
        db.session.commit()
        cid = clazz.id

    res = client.delete(f"/admin/org/classes/{cid}", headers={"HX-Request": "true"})
    assert res.status_code == 200
    with app.app_context():
        assert db.session.get(Class, cid) is None


# ---------------------------------------------------------------------------
# Cohort update
# ---------------------------------------------------------------------------

def test_update_cohort_success(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        school = School(name="UpdCoSchool", code="UCO")
        db.session.add(school)
        db.session.flush()
        major = Major(name="UpdCoMajor", code="UCOM", school_id=school.id)
        db.session.add(major)
        db.session.flush()
        clazz = Class(name="UpdCoClass", year=2026, major_id=major.id)
        db.session.add(clazz)
        db.session.flush()
        cohort = Cohort(name="Old Cohort", class_id=clazz.id, internship_term="T1", is_active=True)
        db.session.add(cohort)
        db.session.commit()
        coid = cohort.id

    res = client.put(
        f"/admin/org/cohorts/{coid}",
        data={"name": "Updated Cohort", "internship_term": "T2"},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
    assert b"Updated Cohort" in res.data


# ---------------------------------------------------------------------------
# Cohort members happy path
# ---------------------------------------------------------------------------

def test_add_cohort_member_success(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        from app.models.user import User as _User
        admin_db = _User.query.filter_by(username="admin").first()
        admin_id = admin_db.id
        school = School(name="MemberSchool", code="MSC")
        db.session.add(school)
        db.session.flush()
        major = Major(name="MemberMajor", code="MMJ", school_id=school.id)
        db.session.add(major)
        db.session.flush()
        clazz = Class(name="MemberClass", year=2026, major_id=major.id)
        db.session.add(clazz)
        db.session.flush()
        cohort = Cohort(name="MemberCohort", class_id=clazz.id, internship_term="T3", is_active=True)
        db.session.add(cohort)
        db.session.commit()
        coid = cohort.id

    res = client.post(
        f"/admin/org/cohorts/{coid}/members",
        data={"user_id": admin_id, "role_in_cohort": "faculty_advisor"},
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200


def test_remove_cohort_member_success(client, app, admin_user):
    login_admin(client)
    with app.app_context():
        from app.models.user import User as _User
        from app.models.assignment import CohortMember
        admin_db = _User.query.filter_by(username="admin").first()
        admin_id = admin_db.id
        school = School(name="RemMemberSchool", code="RMS")
        db.session.add(school)
        db.session.flush()
        major = Major(name="RemMemberMajor", code="RMM", school_id=school.id)
        db.session.add(major)
        db.session.flush()
        clazz = Class(name="RemMemberClass", year=2026, major_id=major.id)
        db.session.add(clazz)
        db.session.flush()
        cohort = Cohort(name="RemMemberCohort", class_id=clazz.id, internship_term="T4", is_active=True)
        db.session.add(cohort)
        db.session.flush()
        member = CohortMember(cohort_id=cohort.id, user_id=admin_id, role_in_cohort="faculty_advisor")
        db.session.add(member)
        db.session.commit()
        coid = cohort.id

    res = client.delete(
        f"/admin/org/cohorts/{coid}/members/{admin_id}",
        headers={"HX-Request": "true"},
    )
    assert res.status_code == 200
