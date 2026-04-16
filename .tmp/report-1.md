# Static Delivery Acceptance & Architecture Audit

## 1. Verdict

- **Overall conclusion: Partial Pass**
- Reason: two independent **High** issues were confirmed statically:
  - Prompt-required hierarchical data-scope model is explicitly not fully implemented.
  - Default startup path uses predictable secret-key fallbacks, weakening session security.

## 2. Scope and Static Verification Boundary

- **Reviewed**
  - Docs and delivery entry points: `README.md`, `docker-compose.yml`, `Dockerfile`, `entrypoint.sh`, `run.sh`, `run_tests.sh`
  - App architecture and route registration: `app/__init__.py`, `app/routes/__init__.py`
  - Security and governance paths: `app/routes/auth.py`, `app/routes/admin.py`, `app/routes/permissions.py`, `app/routes/reports.py`, `app/routes/grading.py`, `app/routes/assignments.py`, `app/services/*`
  - Models and persistence: `app/models/*`
  - Static test evidence: `tests/unit/*`, `tests/api/*`, `tests/e2e/*`, `tests/conftest.py`
  - Requirement clarification document: `docs/questions.md`
- **Excluded**
  - `./.tmp/` and all subdirectories as evidence sources
- **Intentionally not executed**
  - App runtime, Docker, test suite, browser flows, external services
- **Cannot confirm statistically**
  - Runtime correctness of all HTMX swaps/timing behavior (including strict 15s autosave cadence in real browser timing conditions)
  - Concurrency guarantees under true parallel submit/load
  - Operational claims that require live deployment/traffic

## 3. Repository / Requirement Mapping Summary

- **Prompt core goal mapped**: offline Flask+SQLite access-governed practicum assessment system with role-based workflows, quiz/assignment lifecycle, grading, reports/CSV, auditing, encryption/masking, optional MFA.
- **Core flow mapping reviewed**:
  - Auth/session/reauth/MFA/captcha/lockout: `app/routes/auth.py`, `app/services/auth_service.py`, `app/services/session_service.py`, `app/routes/mfa.py`
  - RBAC/scope/delegation: `app/services/rbac_service.py`, `app/routes/permissions.py`, `app/services/decorators.py`
  - Assessment workflows: `app/routes/quiz.py`, `app/services/attempt_service.py`, `app/services/paper_service.py`
  - Grading/reporting/export: `app/routes/grading.py`, `app/routes/reports.py`, `app/services/grading_service.py`, `app/services/report_service.py`
  - Auditing/encryption: `app/services/audit_service.py`, `app/models/audit_log.py`, `app/services/encryption_service.py`

## 4. Section-by-section Review

### 4.1 Hard Gates

#### 4.1.1 Documentation and static verifiability
- **Conclusion: Pass**
- **Rationale**: startup/run/test instructions exist and are statically consistent with declared scripts and compose artifacts.
- **Evidence**: `README.md:18`, `README.md:67`, `docker-compose.yml:1`, `run_tests.sh:1`, `run.sh:1`
- **Manual verification note**: actual runtime success still requires manual execution.

#### 4.1.2 Material deviation from Prompt
- **Conclusion: Fail**
- **Rationale**: prompt mandates hierarchical scope model (self / own dept / sub-departments / global + org axes). Delivery explicitly documents a scoped-down cohort-only model and states full hierarchy was not implemented.
- **Evidence**: `docs/questions.md:20`, `docs/questions.md:21`, `docs/questions.md:22`, `docs/questions.md:24`, `docs/questions.md:25`
- **Manual verification note**: none (explicit static admission + implementation direction is sufficient).

### 4.2 Delivery Completeness

#### 4.2.1 Core explicit requirement coverage
- **Conclusion: Partial Pass**
- **Rationale**: major flows are implemented (auth, roles, quiz lifecycle, grading, reports, CSV, audit, encryption, MFA), but hierarchical scope semantics are materially incomplete versus prompt.
- **Evidence**: `app/routes/quiz.py:71`, `app/routes/grading.py:26`, `app/routes/reports.py:29`, `app/services/auth_service.py:25`, `app/services/encryption_service.py:27`, `docs/questions.md:20`
- **Manual verification note**: browser-timing claims (autosave/inline behavior) require manual run.

#### 4.2.2 End-to-end deliverable from 0 to 1
- **Conclusion: Pass**
- **Rationale**: coherent multi-module project with docs, compose, app, templates, services, tests; no evidence of snippet-only/demo-only shape.
- **Evidence**: `README.md:1`, `app/routes/__init__.py:17`, `tests/api/test_auth_api.py:15`, `tests/unit/test_rbac_service.py:11`

### 4.3 Engineering and Architecture Quality

#### 4.3.1 Structure and module decomposition
- **Conclusion: Pass**
- **Rationale**: clear layering across routes/services/models/templates with separated responsibilities.
- **Evidence**: `app/routes/__init__.py:1`, `app/services/attempt_service.py:10`, `app/services/report_service.py:18`, `app/models/user.py:5`

#### 4.3.2 Maintainability and extensibility
- **Conclusion: Partial Pass**
- **Rationale**: generally maintainable structure, but governance scope design is knowingly reduced from required policy model.
- **Evidence**: `app/services/rbac_service.py:140`, `docs/questions.md:20`

### 4.4 Engineering Details and Professionalism

#### 4.4.1 Error handling, logging, validation, API shape
- **Conclusion: Partial Pass**
- **Rationale**: broad validation/error handling/audit logging exists; however, default predictable secret-key fallback weakens baseline auth/session security posture.
- **Evidence**: `app/services/auth_service.py:25`, `app/routes/main.py:34`, `app/services/audit_service.py:41`, `app/config.py:4`, `docker-compose.yml:9`

#### 4.4.2 Product-like delivery vs demo-only
- **Conclusion: Pass**
- **Rationale**: integrated app with role workflows, org management, quiz, assignment grading, reports, and tests.
- **Evidence**: `app/routes/org.py:26`, `app/routes/assignments.py:18`, `app/routes/reports.py:29`, `tests/e2e/test_core_flows.py:27`

### 4.5 Prompt Understanding and Requirement Fit

#### 4.5.1 Business understanding and implicit constraints
- **Conclusion: Fail**
- **Rationale**: while much of workflow intent is implemented, required hierarchical governance semantics are intentionally narrowed.
- **Evidence**: `docs/questions.md:20`, `docs/questions.md:22`, `docs/questions.md:24`

### 4.6 Aesthetics (frontend/full-stack)

#### 4.6.1 Visual and interaction quality
- **Conclusion: Cannot Confirm Statistically**
- **Rationale**: static structure supports layout/components/states, but no runtime rendering evidence was executed.
- **Evidence**: `app/templates/base.html:25`, `app/templates/quiz/take.html:19`, `app/static/js/quiz_timer.js:45`
- **Manual verification note**: visual hierarchy/hover/transition correctness requires manual browser validation.

## 5. Issues / Suggestions (Severity-Rated)

### Blocker / High (root-cause first)

#### F-001
- **Severity**: High
- **Title**: Required hierarchical data-scope model materially incomplete
- **Conclusion**: Fail
- **Evidence**: `docs/questions.md:20`, `docs/questions.md:21`, `docs/questions.md:22`, `docs/questions.md:24`, `docs/questions.md:25`
- **Impact**: authorization semantics deviate from prompt; governance boundaries may not match required department/sub-department model.
- **Minimum actionable fix**:
  - Implement explicit policy resolution for `self`, `own department`, `sub-departments`, `global`, plus school/major/class/cohort axes.
  - Apply same policy engine to menu visibility and all relevant endpoints.
  - Add API and unit tests for each scope boundary.

#### F-002
- **Severity**: High
- **Title**: Predictable default secret key in default startup path
- **Conclusion**: Fail
- **Evidence**: `app/config.py:4`, `app/config.py:10`, `docker-compose.yml:9`, `README.md:20`
- **Impact**: predictable session signing secret can enable session forgery/privilege abuse in misconfigured deployments.
- **Minimum actionable fix**:
  - Remove static fallback in production-like paths; fail startup when `SECRET_KEY` is default/weak.
  - Generate per-install secret and persist securely if convenience is required.
  - Document mandatory override in quick-start path.

### Medium / Low

#### F-003
- **Severity**: Medium
- **Title**: Anomaly flags are not continuously generated by default flow
- **Conclusion**: Partial Pass
- **Evidence**: `app/routes/admin.py:68`, `app/routes/admin.py:127`
- **Impact**: admin dashboard anomaly view may lag until explicit scan endpoint is triggered.
- **Minimum actionable fix**:
  - Add scheduled/background scan trigger or on-login incremental anomaly evaluation with bounded cost.

#### F-004
- **Severity**: Medium
- **Title**: Audit immutability is partially relaxed by retention purge bulk delete
- **Conclusion**: Partial Pass
- **Evidence**: `app/models/audit_log.py:39`, `app/services/audit_service.py:178`, `app/services/audit_service.py:185`
- **Impact**: strict “immutable” interpretation is weakened by deletion path (even if policy-driven retention exists).
- **Minimum actionable fix**:
  - Clarify policy wording as append-only within retention period, or implement archival/WORM strategy before purge.

## 6. Security Review Summary

- **Authentication entry points**: **Pass**
  - Password hash/verify, captcha threshold, lockout, MFA pending flow implemented.
  - Evidence: `app/routes/auth.py:80`, `app/services/auth_service.py:14`, `app/services/auth_service.py:139`, `app/routes/auth.py:145`

- **Route-level authorization**: **Pass**
  - Common decorators enforce login/role/permission on protected routes.
  - Evidence: `app/services/decorators.py:9`, `app/services/decorators.py:33`, `app/services/decorators.py:77`

- **Object-level authorization**: **Pass**
  - Attempt/result/paper/cohort access checks are present in key routes.
  - Evidence: `app/routes/quiz.py:189`, `app/routes/grading.py:19`, `app/routes/reports.py:22`

- **Function-level authorization**: **Partial Pass**
  - Re-auth is correctly attached to role-switch and permission-edit critical paths, but global secret fallback weakens trust boundary.
  - Evidence: `app/routes/auth.py:315`, `app/routes/permissions.py:49`, `app/routes/admin_users.py:162`, `app/config.py:4`

- **Tenant / user data isolation**: **Pass**
  - Cohort-based access checks and student ownership checks exist in quiz/report/grading/assignment paths.
  - Evidence: `app/services/rbac_service.py:306`, `app/routes/assignments.py:124`, `app/services/report_service.py:132`

- **Admin/internal/debug endpoint protection**: **Pass**
  - Admin endpoints role-guarded; public technical endpoints limited to health and client error logging.
  - Evidence: `app/routes/admin.py:25`, `app/routes/main.py:16`, `app/routes/main.py:34`

## 7. Tests and Logging Review

- **Unit tests**: **Pass**
  - Broad service coverage across auth/rbac/attempt/paper/report/audit/encryption.
  - Evidence: `tests/unit/test_auth_service.py:9`, `tests/unit/test_rbac_service.py:11`, `tests/unit/test_attempt_service.py:10`

- **API / integration tests**: **Pass**
  - Extensive API route coverage including authz failures and business flows.
  - Evidence: `tests/api/test_auth_api.py:15`, `tests/api/test_reports_api.py:109`, `tests/api/test_admin_api.py:115`

- **Logging categories / observability**: **Pass**
  - Structured client error ingress and explicit audit events across critical actions.
  - Evidence: `app/routes/main.py:34`, `app/services/audit_service.py:41`, `app/static/js/htmx_logger.js:35`

- **Sensitive-data leakage risk in logs/responses**: **Partial Pass**
  - Student ID masking/encryption and temp credential reveal gating are present, but default secret-key weakness remains.
  - Evidence: `app/services/encryption_service.py:27`, `app/services/report_service.py:149`, `app/routes/admin_users.py:213`, `app/config.py:4`

## 8. Test Coverage Assessment (Static Audit)

### 8.1 Test Overview

- **Unit tests exist**: Yes (`tests/unit/`)
- **API/integration tests exist**: Yes (`tests/api/`)
- **E2E tests exist**: Yes (`tests/e2e/`, Playwright)
- **Frameworks**: `pytest`, `pytest-playwright`
- **Entry points**: `run_tests.sh`, direct `pytest` commands in README
- **Evidence**: `run_tests.sh:27`, `run_tests.sh:33`, `run_tests.sh:37`, `README.md:67`, `requirements-test.txt:2`

### 8.2 Coverage Mapping Table

| Requirement / Risk Point | Mapped Test Case(s) | Key Assertion / Fixture / Mock | Coverage Assessment | Gap | Minimum Test Addition |
|---|---|---|---|---|---|
| Login + lockout + captcha | `tests/api/test_auth_api.py:27`, `tests/api/test_auth_api.py:47` | lockout/captcha assertions | sufficient | none material | n/a |
| Session inactivity expiry (30m) | `tests/api/test_auth_api.py:70` | stale `last_active_at` redirects with reason | sufficient | none material | n/a |
| High-risk reauth on role/permission edits | `tests/api/test_auth_api.py:150`, `tests/api/test_admin_api.py:37` | redirect to `/reauth` assertions | sufficient | none material | n/a |
| Quiz duplicate submission prevention | `tests/api/test_quiz_api.py:61`, `tests/api/test_quiz_api.py:74` | second submit rejected + single finalize log | basically covered | true parallel race not proven | add concurrent-request test with two clients/threads |
| Cohort-scoped advisor access control | `tests/api/test_reports_api.py:30`, `tests/api/test_grading_api.py:100` | 403 for unassigned cohort | sufficient | none material | n/a |
| CSV export permission boundary | `tests/api/test_reports_api.py:109`, `tests/api/test_reports_api.py:147` | deny/allow by `report:export` | sufficient | none material | n/a |
| Student ID masking in report output | `tests/api/test_reports_api.py:71`, `tests/api/test_reports_api.py:89` | plaintext ID absent | sufficient | none material | n/a |
| Prompt-required hierarchical scope semantics | no direct comprehensive test set | docs explicitly scope down behavior | **missing** | required policy dimensions not tested or fully implemented | add unit+API matrix for self/dept/sub-dept/global + org-axis combinations |
| Secret-key hardening behavior | no startup-hardening test | static defaults in config/compose | **missing** | unsafe default path unguarded by tests | add startup test that fails when default secret used |

### 8.3 Security Coverage Audit

- **Authentication**: **sufficiently covered**
  - Evidence: `tests/api/test_auth_api.py:15`, `tests/api/test_mfa_api.py:51`
- **Route authorization**: **sufficiently covered**
  - Evidence: `tests/api/test_admin_api.py:115`, `tests/api/test_assignment_api.py:158`
- **Object-level authorization**: **basically covered**
  - Evidence: `tests/api/test_quiz_api.py:117`, `tests/api/test_grading_api.py:100`
  - Gap: no heavy concurrent/object-race stress tests.
- **Tenant/data isolation**: **basically covered**
  - Evidence: `tests/api/test_reports_api.py:44`, `tests/api/test_assignment_api.py:40`
  - Gap: hierarchical dept/sub-dept scope model not represented end-to-end.
- **Admin/internal protection**: **sufficiently covered**
  - Evidence: `tests/api/test_auth_api.py:253`, `tests/e2e/test_core_flows.py:231`

### 8.4 Final Coverage Judgment

- **Partial Pass**
- Covered major auth/authz and core flow risks, but severe defects could still evade tests where required hierarchical scope semantics are not fully implemented/tested, and startup secret hardening is not validated.

## 9. Final Notes

- Conclusions are static-only and evidence-based; no runtime claims are made beyond code/test artifacts.
- Highest-priority remediation is to close prompt-fit governance scope gaps and remove insecure secret defaults.
