# Static Delivery Acceptance & Architecture Audit (Re-scan)

## 1. Verdict

- **Overall conclusion: Fail**
- Re-scan result: previously reported high issues about hierarchical scope absence and weak default secret key are now fixed in current code, but a **new/current High** root issue remains in delegation scope enforcement.

## 2. Scope and Static Verification Boundary

- **Reviewed**
  - Delivery/docs/config: `README.md`, `docker-compose.yml`, `app/config.py`, `docs/questions.md`
  - Auth/RBAC/scope/delegation: `app/services/rbac_service.py`, `app/routes/permissions.py`, `app/services/decorators.py`
  - Security/audit/reporting paths and related templates/routes
  - Tests: `tests/unit/*`, `tests/api/*`, `tests/e2e/*` (static reading only)
- **Excluded**
  - `./.tmp/` as evidence source for conclusions (only current repo code/docs/tests used for findings)
- **Not executed**
  - App runtime, Docker, browser runtime, test execution
- **Manual verification required**
  - Runtime UI/HTMX timing correctness and full end-user visual behavior
  - Real concurrency behavior under parallel requests

## 3. Repository / Requirement Mapping Summary

- Prompt core objective is largely implemented: offline Flask+SQLite app with role-based workflows, quiz/assignment lifecycle, grading, reports/export, audit logging, encryption/masking, and optional TOTP MFA.
- Re-scan focus against prompt constraints:
  - Scope model and delegation consistency (self/dept/subdept/global + school/major/class/cohort)
  - Authorization consistency across menus/endpoints
  - Test coverage for high-risk authorization boundaries
- Main implementation areas mapped: `app/services/rbac_service.py`, `app/routes/permissions.py`, `app/routes/reports.py`, `app/routes/grading.py`, `app/routes/quiz.py`, plus corresponding API/unit tests.

## 4. Section-by-section Review

### 4.1 Hard Gates

#### 4.1.1 Documentation and static verifiability
- **Conclusion: Pass**
- **Rationale**: startup/run/test/config guidance is present and statically coherent with scripts/compose.
- **Evidence**: `README.md:18`, `README.md:74`, `docker-compose.yml:1`, `run_tests.sh:1`
- **Manual verification note**: runtime success still requires manual execution.

#### 4.1.2 Material deviation from Prompt
- **Conclusion: Fail**
- **Rationale**: hierarchical scope support is documented and partially coded, but temporary delegation scope handling is inconsistent and incomplete for non-cohort scopes, weakening prompt-required scope governance behavior.
- **Evidence**: `docs/questions.md:11`, `docs/questions.md:20`, `app/routes/permissions.py:15`, `app/services/rbac_service.py:242`, `app/services/rbac_service.py:451`

### 4.2 Delivery Completeness

#### 4.2.1 Core explicit requirement coverage
- **Conclusion: Partial Pass**
- **Rationale**: most core features are implemented, but temporary delegation does not reliably enforce full scope hierarchy.
- **Evidence**: `app/routes/quiz.py:71`, `app/routes/reports.py:29`, `app/routes/grading.py:26`, `app/services/rbac_service.py:242`

#### 4.2.2 End-to-end deliverable (0→1 shape)
- **Conclusion: Pass**
- **Rationale**: coherent multi-module full-stack deliverable with docs, containers, routes, services, tests.
- **Evidence**: `README.md:1`, `app/routes/__init__.py:17`, `tests/api/test_auth_api.py:15`, `tests/e2e/test_core_flows.py:27`

### 4.3 Engineering and Architecture Quality

#### 4.3.1 Structure and modularity
- **Conclusion: Pass**
- **Rationale**: clear separation across models/services/routes/templates/tests.
- **Evidence**: `app/routes/__init__.py:1`, `app/services/attempt_service.py:10`, `app/services/report_service.py:18`

#### 4.3.2 Maintainability/extensibility
- **Conclusion: Partial Pass**
- **Rationale**: architecture is generally maintainable, but delegation scope logic is split across validators/resolvers with inconsistent scope support.
- **Evidence**: `app/routes/permissions.py:15`, `app/services/rbac_service.py:91`, `app/services/rbac_service.py:242`

### 4.4 Engineering Details and Professionalism

#### 4.4.1 Error handling/logging/validation/API
- **Conclusion: Partial Pass**
- **Rationale**: strong baseline validation/logging exists; authorization detail has a material delegation-scope enforcement gap.
- **Evidence**: `app/services/auth_service.py:25`, `app/services/audit_service.py:41`, `app/services/rbac_service.py:451`

#### 4.4.2 Product-like delivery vs demo
- **Conclusion: Pass**
- **Rationale**: repository resembles a real system with connected role workflows and test surfaces.
- **Evidence**: `app/routes/org.py:26`, `app/routes/assignments.py:111`, `app/routes/reports.py:49`

### 4.5 Prompt Understanding and Requirement Fit

#### 4.5.1 Business understanding and fit
- **Conclusion: Partial Pass**
- **Rationale**: understanding improved (full scope model documented and coded), but delegation path does not fully realize that model in enforceable behavior.
- **Evidence**: `docs/questions.md:11`, `app/services/rbac_service.py:91`, `app/services/rbac_service.py:242`

### 4.6 Aesthetics (frontend/full-stack)

#### 4.6.1 Visual and interaction quality
- **Conclusion: Cannot Confirm Statistically**
- **Rationale**: static structure shows reasonable layout/state hooks, but visual quality and interaction polish require runtime/manual review.
- **Evidence**: `app/templates/base.html:25`, `app/templates/quiz/take.html:19`, `app/static/js/quiz_timer.js:45`
- **Manual verification note**: browser verification needed.

## 5. Issues / Suggestions (Severity-Rated)

### Blocker / High

#### F-001
- **Severity**: High
- **Title**: Temporary delegation scope hierarchy is inconsistently enforced
- **Conclusion**: Fail
- **Evidence**
  - Delegation input validator excludes some documented/implemented scopes (`subdept`, `self`): `app/routes/permissions.py:15`
  - Delegation scope resolver only interprets `scope:cohort:<id>` and `scope:global`: `app/services/rbac_service.py:242`
  - `can_access_cohort()` relies on `_scope_permits_cohort()` (UserPermission rows only) + delegation ID set; non-cohort delegation scopes are not equivalently enforced: `app/services/rbac_service.py:401`, `app/services/rbac_service.py:451`
- **Impact**
  - Scope behavior for temporary delegations can diverge from prompt-required hierarchical model and from documented scope matrix, creating authorization correctness risk.
- **Minimum actionable fix**
  - Make one canonical scope parser/resolver for both `UserPermission` and `TemporaryDelegation`.
  - Extend delegation normalization/validation to all supported scope forms (including `subdept` and any intended `self` semantics).
  - Update `can_access_cohort()` to evaluate delegation scopes through the same hierarchy resolver rather than cohort/global special-casing.
  - Add API tests for delegated `dept/subdept/school/major/class` access allow/deny boundaries.

### Medium / Low

#### F-002
- **Severity**: Medium
- **Title**: Delegation scope test coverage is narrow versus implemented scope matrix
- **Conclusion**: Partial Pass
- **Evidence**: `tests/api/test_admin_api.py:639`, `tests/unit/test_rbac_service.py:250`
- **Impact**: severe scope bugs in non-cohort delegation paths could remain undetected.
- **Minimum actionable fix**: add API tests for delegated `scope:dept`, `scope:subdept`, `scope:school`, `scope:major`, `scope:class` positive and negative cases.

#### F-003
- **Severity**: Low
- **Title**: README local dev example uses weak-looking `SECRET_KEY` sample
- **Conclusion**: Partial Pass
- **Evidence**: `README.md:89`, `app/config.py:29`
- **Impact**: onboarding confusion (example value is rejected and replaced by auto-generated key).
- **Minimum actionable fix**: replace local example with strong random generation command.

## 6. Security Review Summary

- **Authentication entry points**: **Pass**
  - Password strength, lockout, captcha, session timeout, MFA flow present.
  - Evidence: `app/services/auth_service.py:25`, `app/services/auth_service.py:104`, `app/routes/auth.py:145`

- **Route-level authorization**: **Pass**
  - Decorator-based route guards are broadly applied.
  - Evidence: `app/services/decorators.py:9`, `app/services/decorators.py:33`, `app/services/decorators.py:77`

- **Object-level authorization**: **Partial Pass**
  - Many object checks exist, but delegation scope path is inconsistent for non-cohort scopes.
  - Evidence: `app/routes/reports.py:22`, `app/routes/grading.py:19`, `app/services/rbac_service.py:242`

- **Function-level authorization**: **Partial Pass**
  - High-risk actions enforce reauth, but delegation scope semantics remain incomplete.
  - Evidence: `app/services/decorators.py:20`, `app/routes/permissions.py:52`, `app/routes/permissions.py:131`

- **Tenant/user isolation**: **Partial Pass**
  - Cohort isolation is generally enforced; delegated hierarchy scopes are not uniformly enforced.
  - Evidence: `app/services/rbac_service.py:451`, `app/services/rbac_service.py:472`

- **Admin/internal/debug protection**: **Pass**
  - Admin surfaces protected by role/login guards; debug surface is limited.
  - Evidence: `app/routes/admin.py:25`, `app/routes/main.py:34`

## 7. Tests and Logging Review

- **Unit tests**: **Pass**
  - Strong unit coverage including new scope and secret-key tests.
  - Evidence: `tests/unit/test_rbac_service.py:185`, `tests/unit/test_secret_key.py:1`

- **API/integration tests**: **Pass**
  - Broad API coverage for auth, quiz, reports, grading, admin.
  - Evidence: `tests/api/test_auth_api.py:15`, `tests/api/test_reports_api.py:30`, `tests/api/test_admin_api.py:578`

- **Logging categories/observability**: **Pass**
  - Audit logging plus structured client error ingestion exist.
  - Evidence: `app/services/audit_service.py:41`, `app/routes/main.py:34`, `app/static/js/htmx_logger.js:35`

- **Sensitive-data leakage risk in logs/responses**: **Pass**
  - Student ID masking/encryption and one-time credential reveal controls present; previous secret-key concern is remediated.
  - Evidence: `app/services/encryption_service.py:27`, `app/services/report_service.py:149`, `app/config.py:17`

## 8. Test Coverage Assessment (Static Audit)

### 8.1 Test Overview

- Unit tests: present (`tests/unit/`)
- API/integration tests: present (`tests/api/`)
- E2E tests: present (`tests/e2e/`)
- Frameworks: `pytest`, `pytest-playwright`
- Test entry points: `run_tests.sh`, documented pytest commands
- Evidence: `run_tests.sh:27`, `run_tests.sh:33`, `run_tests.sh:37`, `README.md:74`, `requirements-test.txt:2`

### 8.2 Coverage Mapping Table

| Requirement / Risk Point | Mapped Test Case(s) | Key Assertion / Fixture / Mock | Coverage Assessment | Gap | Minimum Test Addition |
|---|---|---|---|---|---|
| Login, captcha, lockout | `tests/api/test_auth_api.py:27`, `tests/api/test_auth_api.py:47` | lockout/captcha assertions | sufficient | none material | n/a |
| Session inactivity timeout | `tests/api/test_auth_api.py:70` | stale session redirects with reason | sufficient | none material | n/a |
| Reauth for high-risk actions | `tests/api/test_admin_api.py:37`, `tests/api/test_auth_api.py:150` | `/reauth` redirect checks | sufficient | none material | n/a |
| Quiz duplicate submission prevention | `tests/api/test_quiz_api.py:61`, `tests/api/test_quiz_api.py:74` | replay rejected, single finalize log | basically covered | true parallelism not proven | add dual-client parallel submit test |
| Hierarchical scope resolver (`dept/subdept/self`) | `tests/unit/test_rbac_service.py:215`, `tests/unit/test_rbac_service.py:250`, `tests/unit/test_rbac_service.py:286` | explicit scope resolution assertions | basically covered | delegation path not equally covered | add delegated-scope resolver integration tests |
| Temporary delegation scope enforcement | `tests/api/test_admin_api.py:639`, `tests/api/test_admin_api.py:686` | tests centered on `scope:cohort` | insufficient | non-cohort delegated scopes untested | add API tests for delegated `dept/subdept/school/major/class` allow+deny |
| Secret-key hardening | `tests/unit/test_secret_key.py:15`, `tests/unit/test_secret_key.py:65` | weak key rejection and non-default checks | sufficient | none material | n/a |
| Report/export authorization + masking | `tests/api/test_reports_api.py:109`, `tests/api/test_reports_api.py:71` | export 403 boundary + plaintext ID absence | sufficient | none material | n/a |

### 8.3 Security Coverage Audit

- **authentication**: sufficiently covered  
  Evidence: `tests/api/test_auth_api.py:15`, `tests/api/test_mfa_api.py:51`
- **route authorization**: sufficiently covered  
  Evidence: `tests/api/test_admin_api.py:115`, `tests/api/test_assignment_api.py:158`
- **object-level authorization**: basically covered  
  Evidence: `tests/api/test_quiz_api.py:117`, `tests/api/test_grading_api.py:100`
- **tenant/data isolation**: basically covered  
  Evidence: `tests/api/test_reports_api.py:44`, `tests/api/test_assignment_api.py:40`
- **admin/internal protection**: sufficiently covered  
  Evidence: `tests/api/test_auth_api.py:253`, `tests/e2e/test_core_flows.py:231`

Remaining severe-undetected risk: delegated non-cohort scope authorization defects can still pass current tests.

### 8.4 Final Coverage Judgment

- **Partial Pass**
- Major auth/authz paths are tested, but delegation-scope hierarchy coverage is incomplete enough that serious authorization defects could still pass the suite.

## 9. Final Notes

- This report is a full re-scan for current state; previously fixed issues were not carried forward as active findings.
- All conclusions are static-only and evidence-based from current code/docs/tests.
