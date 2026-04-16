# Test Coverage Audit

## Backend Endpoint Inventory

Static source of truth:
- Route decorators in `app/routes/*.py` (`@*_bp.get/post/put/delete/patch`)
- Blueprint prefixes from `Blueprint(..., url_prefix=...)`

Resolved endpoint count by route file:
- `app/routes/admin.py`: 7
- `app/routes/admin_users.py`: 10
- `app/routes/assignments.py`: 12
- `app/routes/auth.py`: 12
- `app/routes/cohort.py`: 2
- `app/routes/grading.py`: 5
- `app/routes/main.py`: 3
- `app/routes/mfa.py`: 5
- `app/routes/org.py`: 16
- `app/routes/papers.py`: 10
- `app/routes/permissions.py`: 7
- `app/routes/questions.py`: 7
- `app/routes/quiz.py`: 7
- `app/routes/reports.py`: 11

Total resolved endpoints: **114**

Representative resolved endpoint shapes:
- Admin: `/admin/audit-logs`, `/admin/users/:id/reset-password`, `/admin/anomalies/:flag_id/review`
- Auth/session: `/login`, `/logout`, `/reauth`, `/change-password`, `/switch-role`
- Org/papers/questions/permissions: `/admin/org/*`, `/admin/papers/*`, `/admin/questions/*`, `/admin/permissions/*`
- Quiz/grading/reports: `/quiz/*`, `/grading/*`, `/reports/*`
- Misc: `/`, `/health`, `/client-error-log`, `/settings/mfa/*`, `/cohorts/*`

## API Test Mapping Table

Per-endpoint mapping result (static): every resolved endpoint has at least one HTTP path-level test call in:
- API client tests (`tests/api/*.py`) using Flask test client calls (`get/post/put/delete`)
- HTTP integration tests (`tests/integration/*.py`) using `requests.Session`
- E2E tests (`tests/e2e/test_core_flows.py`) using browser navigation (`page.goto`)

| Scope | Endpoints | Covered | Test Type | Evidence |
|---|---:|---|---|---|
| `admin.py` | 7 | yes | true no-mock HTTP | `tests/api/test_admin_api.py::test_get_audit_logs_non_admin_forbidden`, `test_anomaly_scan_post_creates_flags_and_audit_event` |
| `admin_users.py` | 10 | yes | true no-mock HTTP | `tests/api/test_admin_api.py::test_create_user_happy_path`, `test_update_user_with_reauth_succeeds`, `test_reveal_student_id_with_reauth_returns_decrypted` |
| `assignments.py` | 12 | yes | true no-mock HTTP | `tests/api/test_assignment_api.py::test_admin_can_create_assignment`, `test_student_can_submit`, `test_grader_can_grade` |
| `auth.py` | 12 | yes | true no-mock HTTP | `tests/api/test_auth_api.py::test_post_login_valid_redirects_dashboard`, `tests/integration/test_auth_http.py::test_logout_clears_session` |
| `cohort.py` | 2 | yes | true no-mock HTTP | `tests/api/test_admin_api.py::test_delegation_grants_access_to_delegated_cohort`, `tests/e2e/test_core_flows.py::test_cohort_view_reports_link_filters_papers` |
| `grading.py` | 5 | yes | true no-mock HTTP | `tests/api/test_grading_api.py::test_get_grading_dashboard_only_assigned_cohorts`, `test_post_grading_score_valid_returns_fragment` |
| `main.py` | 3 | yes | true no-mock HTTP | `tests/integration/test_missing_endpoints.py::test_root_unauthenticated_redirects_to_login`, `tests/api/test_client_log_api.py::test_client_error_log_accepts_beacon`, `tests/e2e/test_core_flows.py::test_health_endpoint` |
| `mfa.py` | 5 | yes | true no-mock HTTP | `tests/api/test_mfa_api.py::test_mfa_setup_generates_secret`, `test_mfa_disable_requires_reauth` |
| `org.py` | 16 | yes | true no-mock HTTP | `tests/api/test_org_api.py::test_create_school_success`, `test_update_cohort_success`, `tests/integration/test_missing_endpoints.py::test_cohort_members_admin_200` |
| `papers.py` | 10 | yes | true no-mock HTTP | `tests/api/test_paper_api.py::test_create_paper_redirects_to_builder`, `test_publish_paper_success` |
| `permissions.py` | 7 | yes | true no-mock HTTP | `tests/api/test_admin_api.py::test_post_permission_template_without_reauth_redirects`, `tests/integration/test_missing_endpoints.py::test_admin_permissions_grant_processes_after_reauth` |
| `questions.py` | 7 | yes | true no-mock HTTP | `tests/api/test_question_api.py::test_create_question_success`, `test_rubric_save_success`, `tests/integration/test_missing_endpoints.py::test_admin_questions_edit_admin_200` |
| `quiz.py` | 7 | yes | true no-mock HTTP | `tests/api/test_quiz_api.py::test_quiz_start_within_window_creates_attempt`, `test_quiz_submit_first_and_second_token_replay` |
| `reports.py` | 11 | yes | true no-mock HTTP | `tests/api/test_reports_api.py::test_get_reports_summary_has_score_data`, `test_get_reports_cohort_comparison_fragment_200`, `tests/integration/test_reports_http.py::test_export_summary_with_permission` |

## Coverage Summary

- Total endpoints: **114**
- Endpoints with HTTP tests: **114**
- Endpoints with TRUE no-mock tests: **114**
- HTTP coverage: **100.00%**
- True API coverage: **100.00%**

## Unit Test Summary

Unit test files:
- `tests/unit/test_anomaly_detection.py`
- `tests/unit/test_assignment_service.py`
- `tests/unit/test_attempt_service.py`
- `tests/unit/test_audit_service.py`
- `tests/unit/test_auth_service.py`
- `tests/unit/test_captcha.py`
- `tests/unit/test_encryption_service.py`
- `tests/unit/test_grading_service.py`
- `tests/unit/test_paper_service.py`
- `tests/unit/test_password_validation.py`
- `tests/unit/test_question_service.py`
- `tests/unit/test_rbac_gaps.py`
- `tests/unit/test_rbac_service.py`
- `tests/unit/test_report_service.py`
- `tests/unit/test_secret_key.py`
- `tests/unit/test_session_service.py`
- `tests/unit/test_vendor_assets.py`

Modules covered:
- Controllers/routes: broad route-level behavior coverage through API/integration/E2E tests.
- Services: strong direct unit coverage for assignment, attempt, audit, auth, encryption, grading, paper, question, RBAC, report, session.
- Repositories/data layer: exercised indirectly through SQLAlchemy-backed tests and service/HTTP flows.
- Auth/guards/middleware: strong behavioral coverage in auth, role/scope, reauth, and permission tests.

Important modules not directly unit-tested (isolated):
- `app/services/decorators.py`
- `app/services/mfa_service.py`
- `app/services/org_setup.py`
- Route handlers `GET /health` and `GET /cohorts` rely mainly on integration/E2E-level assertions rather than dedicated API-contract tests.

## Tests Check

### API Test Classification

1. **True No-Mock HTTP**
   - `tests/api/*.py`, `tests/integration/*.py`, and `tests/e2e/test_core_flows.py` exercise real HTTP paths.
2. **HTTP with Mocking**
   - None detected.
3. **Non-HTTP (unit/integration without HTTP)**
   - `tests/unit/*.py`
   - `tests/api/test_auth_api.py::test_session_lifetime_fallback_reads_session_lifetime_minutes_env` (configuration-focused, uses env monkeypatch).

### Mock Detection

Static mock scan findings:
- No `jest.mock`, `vi.mock`, `sinon.stub`, `patch(...)`, `MagicMock`, `Mock`, or `mocker.*` in HTTP endpoint test paths.
- `monkeypatch.setenv` appears in:
  - `tests/api/test_auth_api.py::test_session_lifetime_fallback_reads_session_lifetime_minutes_env`
  - `tests/unit/test_secret_key.py`
  - `tests/unit/test_audit_service.py`

Classification impact:
- These are env/config manipulations, not mocked HTTP transport/controllers/services on endpoint execution paths.

### API Observability Check

Strong:
- Endpoint method/path usage is explicit in API/integration tests.
- Request inputs and key response assertions are visible in most endpoint families.

Weak:
- A small subset (`/login`, `/cohorts`, `/health`, `/admin/org/schools`) has lighter contract assertions in some E2E-centric coverage paths.

### Test Quality & Sufficiency

- Success paths: broad.
- Failure/validation/permission paths: broad (`400/401/403/404` patterns heavily present).
- Integration boundaries: real HTTP integration + browser E2E present.
- Depth: generally strong; minor inconsistency in response-contract strictness for a few endpoints.

`run_tests.sh` check:
- Docker-based test entry is present (`docker compose --profile test run --rm test`) -> **OK**.

## Test Coverage Score (0–100)

**93/100**

## Score Rationale

- Very strong endpoint coverage and extensive security/role-flow testing.
- No endpoint-path mocking pattern detected in HTTP tests.
- Score is not maximal due to uneven response-contract depth on a few endpoints and some reliance on E2E-level assertions for those paths.

## Key Gaps

1. Add direct API-contract assertions for endpoints currently validated mostly through E2E navigation/status.
2. Add isolated unit tests for decorator/MFA/org-setup helper layers.
3. Keep strengthening response schema/body assertions for all endpoint variants.

## Confidence & Assumptions

- Confidence: **medium-high**
- Assumptions:
  - Endpoint total is derived from static route decorators + resolved blueprint prefixes.
  - Coverage mapping is static and based on visible test callsites and test-function evidence.
  - No runtime behavior was assumed.

Test Coverage Verdict: **PASS**

---

# README Audit

## Project Type Detection

- Declared near top: `Full-stack web application` in `repo/README.md` -> classified as **fullstack**.

## README Location

- Required file `repo/README.md` exists -> **PASS**.

## High Priority Issues

None.

## Medium Priority Issues

None.

## Low Priority Issues

1. Minor command duality (`docker-compose` and `docker compose`) may be redundant, but it improves operator compatibility.

## Hard Gate Failures

None.

## README Verdict (PASS / PARTIAL PASS / FAIL)

**PASS**

Gate evidence:
- Formatting/readability: structured markdown and sections -> pass.
- Startup instructions: includes exact `docker-compose up` -> pass.
- Access method: explicit URL/port and health endpoint -> pass.
- Verification method: includes concrete end-to-end UI checklist and API verification path -> pass.
- Environment rules: no install/manual DB setup required for normal startup instructions -> pass.
- Demo credentials: credentials for all listed roles (dept admin, advisor, mentor, student) -> pass.
- Engineering quality: tech stack, architecture overview, test instructions, and role workflows are documented -> pass.

README Audit Verdict: **PASS**

---

# Final Verdicts

- **Test Coverage Audit:** **PASS**
- **README Audit:** **PASS**
