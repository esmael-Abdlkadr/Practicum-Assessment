# design.md — System Architecture & Design

## 1. Project Overview

**System:** Practicum Assessment & Access Governance  
**Type:** Full-Stack Web Application (pure_backend API + server-rendered HTMX frontend)  
**Deployment:** Single Docker container, fully offline, no external SaaS dependencies  
**Database:** SQLite 3.39+ (file-based, single-process)

---

## 2. High-Level Architecture

```
Browser
  │
  │  HTTP (full-page GETs + HTMX fragment POSTs)
  ▼
┌──────────────────────────────────────────────┐
│  Flask Application  (port 5000)              │
│                                              │
│  ┌──────────┐   ┌───────────┐  ┌─────────┐  │
│  │  Routes  │──▶│ Services  │─▶│ Models  │  │
│  │ (HTMX)   │   │(Business) │  │  (ORM)  │  │
│  └──────────┘   └───────────┘  └────┬────┘  │
│                                     │        │
│                                SQLAlchemy    │
└─────────────────────────────────────┼────────┘
                                      │
                               ┌──────┴──────┐
                               │  SQLite DB  │
                               │  (data/)    │
                               └─────────────┘
```

**Request flow:**
1. Browser sends a GET (full page) or POST/PUT/DELETE (HTMX fragment swap).
2. `before_request` hook checks session validity, inactivity expiry, and role.
3. Route calls the appropriate service function — no business logic in routes.
4. Service calls the model layer via SQLAlchemy and writes audit logs atomically.
5. Route renders a Jinja2 template (full page or fragment) and returns HTML.
6. HTMX swaps the target DOM element in-place without a full reload.

---

## 3. Directory Structure

```
repo/
├── app/
│   ├── __init__.py          # App factory, blueprints, before_request hooks
│   ├── config.py            # Environment-specific configs
│   ├── extensions.py        # SQLAlchemy, Flask-Session instances
│   ├── models/              # ORM model definitions (one file per entity group)
│   │   ├── user.py
│   │   ├── org.py           # School, Major, Class, Cohort
│   │   ├── paper.py         # Paper, PaperQuestion, CohortPaper
│   │   ├── question.py      # Question, QuestionOption, Rubric
│   │   ├── attempt.py       # Attempt, Answer
│   │   ├── assignment.py    # Assignment, AssignmentSubmission, AssignmentGrade
│   │   ├── grading.py       # GradingComment
│   │   ├── permission.py    # PermissionTemplate, UserPermission, TemporaryDelegation
│   │   ├── audit_log.py     # AuditLog (immutable)
│   │   ├── anomaly_flag.py  # AnomalyFlag
│   │   └── login_attempt.py # LoginAttempt
│   ├── routes/              # Blueprint route handlers (thin — no business logic)
│   │   ├── auth.py          # Login, logout, reauth, role-switch, MFA verify
│   │   ├── mfa.py           # MFA setup/disable
│   │   ├── admin_users.py   # User CRUD, password reset, student ID reveal
│   │   ├── org.py           # School/Major/Class/Cohort CRUD
│   │   ├── questions.py     # Question bank CRUD + rubric editor
│   │   ├── papers.py        # Paper builder, publish, close
│   │   ├── quiz.py          # Student quiz flow (start, take, autosave, submit)
│   │   ├── assignments.py   # Assignment admin + student + grader flows
│   │   ├── grading.py       # Manual grading UI
│   │   ├── reports.py       # Score summaries, item analysis, CSV export
│   │   ├── permissions.py   # Templates, user grants, delegations
│   │   ├── cohort.py        # Cohort detail view
│   │   ├── admin.py         # Audit log viewer, anomaly dashboard
│   │   └── main.py          # Home, health check
│   ├── services/            # Business logic layer
│   │   ├── auth_service.py       # Password hashing, strength check, lockout, CAPTCHA
│   │   ├── session_service.py    # Login, logout, reauth, role-switch
│   │   ├── audit_service.py      # Immutable log writes, purge, anomaly detection
│   │   ├── rbac_service.py       # Permission checks, delegation expiry, nav generation
│   │   ├── decorators.py         # @permission_required, @require_scope, @high_risk_action
│   │   ├── question_service.py   # Question CRUD, type validation
│   │   ├── paper_service.py      # Paper assembly, publish, close
│   │   ├── attempt_service.py    # Quiz start/autosave/submit, duplicate prevention
│   │   ├── grading_service.py    # Auto-grade, manual score, comments
│   │   ├── assignment_service.py # Assignment lifecycle
│   │   ├── report_service.py     # Score summaries, CSV generation
│   │   └── crypto_service.py     # Fernet encrypt/decrypt for sensitive fields
│   ├── templates/           # Jinja2 HTML templates (full pages + HTMX fragments)
│   └── static/              # CSS (app.css, Bootstrap 5), JS (htmx.min.js)
├── tests/
│   ├── conftest.py          # Fixtures: app, client, all-role users, seeded data
│   ├── unit/                # Pure unit tests for service functions
│   └── api/                 # HTTP endpoint tests via Flask test client
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── run_tests.sh
└── README.md
```

---

## 4. Data Model

### 4.1 User & Auth

| Model | Key Fields |
|---|---|
| `User` | `username`, `password_hash`, `role`, `full_name`, `email`, `student_id_enc`, `is_active`, `failed_attempts`, `locked_until`, `mfa_secret`, `mfa_enabled`, `force_password_change` |
| `LoginAttempt` | `user_id`, `ip_address`, `success`, `created_at` |

### 4.2 Organisation Hierarchy

```
School ──< Major ──< Class ──< Cohort ──< CohortMember (user_id)
```

### 4.3 Assessment

```
Paper ──< PaperQuestion ──> Question ──< QuestionOption
  │
  └──< CohortPaper (which cohort can see this paper)
  └──< Attempt ──< Answer
```

### 4.4 Assignment

```
Assignment ──< AssignmentSubmission ──< AssignmentGrade
```

### 4.5 Permissions

```
PermissionTemplate   (reusable sets of permission strings)
UserPermission       (user_id + permission string + optional expiry)
TemporaryDelegation  (delegator → delegate, scope, permissions, expires_at)
```

### 4.6 Audit & Security

```
AuditLog      (immutable: actor, action, resource, old/new value, IP, device fingerprint)
AnomalyFlag   (flagged login pattern, reviewed_at)
```

---

## 5. Authentication & Session Design

| Concern | Implementation |
|---|---|
| Password storage | `bcrypt` salted hash |
| Password strength | ≥12 chars, 3 of 4 character classes |
| Failed-attempt tracking | `User.failed_attempts` + `LoginAttempt` table |
| CAPTCHA trigger | After 3 failed attempts — arithmetic challenge in session |
| Account lockout | 15 minutes after 8 failures (`User.locked_until`) |
| Session backend | Flask-Session filesystem store |
| Session expiry | 30 minutes inactivity (`PERMANENT_SESSION_LIFETIME`) |
| Re-authentication | `@high_risk_action` decorator → redirects to `/reauth` with 5-min TTL |
| Role switching | `POST /switch-role` — requires reauth, validated against allowed roles |
| MFA | Optional TOTP (`pyotp`), QR rendered as inline data URI (`qrcode` lib) |

---

## 6. Authorisation Design

### Roles

| Role | Code |
|---|---|
| Department Admin | `dept_admin` |
| Faculty Advisor | `faculty_advisor` |
| Corporate Mentor | `corporate_mentor` |
| Student | `student` |

### RBAC Enforcement

- `@permission_required("perm:name")` — checks `UserPermission` table; `dept_admin` always passes.
- `@require_scope("cohort", cohort_id)` — verifies caller is a member/advisor of the given cohort.
- `@high_risk_action` — checks `session["reauth_at"]` is within 5 minutes; redirects to `/reauth` otherwise.
- All checks happen at the **route layer** with additional defense-in-depth in the **service layer**.

### Data Scopes

Scope tag | Description
---|---
`self` | Only own records
`cohort:<id>` | Records belonging to a specific cohort
`dept` | Own department and sub-departments
`global` | No restriction (dept_admin only)

---

## 7. Frontend Design

- **Rendering:** Jinja2 server-side templates; Bootstrap 5 for layout and components.
- **Interactivity:** HTMX — POSTs return HTML fragments swapped into target elements (`hx-swap`, `hx-target`).
- **No JavaScript framework** — intentional; HTMX attributes on HTML elements handle all dynamic behaviour.
- **Double-submit prevention:** `hx-disabled-elt="this"` disables submit buttons on first click; spinner (`htmx-indicator`) shows loading state.
- **Autosave (quiz):** HTMX polls `/quiz/<id>/autosave` every 15 seconds using `hx-trigger="every 15s"`.
- **Countdown timer:** JavaScript `setInterval` reads remaining seconds from the server on quiz start and counts down locally; syncs on autosave response.

---

## 8. Audit Logging Design

Every state-changing route calls `audit_service.log()` with:

| Field | Content |
|---|---|
| `actor_id` / `actor_username` | From session (or `SYSTEM` for scheduled jobs) |
| `action` | Dot-namespaced string e.g. `user.login`, `quiz.submit`, `permission.grant` |
| `resource_type` + `resource_id` | Entity being affected |
| `old_value` / `new_value` | JSON snapshots of state before/after |
| `ip_address` | From `request.remote_addr` |
| `device_fingerprint` | Hash of `User-Agent` + `Accept-Language` headers |

**Immutability:** SQLAlchemy `before_update` and `before_delete` event hooks raise `PermissionError`. ORM-level `update()` and `delete()` methods also raise.

**Retention:** Default 3 years (1095 days). `purge_old_logs()` runs at startup and is called periodically via `before_request` (max once per day).

**Anomaly detection:** Rapid consecutive failures or new device fingerprint after established session triggers `AnomalyFlag` creation and surfaces on `/admin/anomalies`.

---

## 9. Security Hardening

| Control | Implementation |
|---|---|
| Sensitive field encryption | Fernet symmetric encryption (`cryptography` lib); key from env var |
| Student ID masking | Template filter shows `****XXXX`; reveal requires `dept_admin` + re-auth |
| IDOR prevention | Service layer checks resource ownership against session user before any action |
| Duplicate submission | `Attempt.submitted_at` checked before allowing a new answer save/submit |
| Delegation max expiry | 30 days hard limit; values > 30 rejected with HTTP 400 |
| Delegation auto-expire | `rbac_service.expire_delegations()` called at startup and hourly |
| No third-party outbound | All libraries are PyPI packages; zero runtime external calls |

---

## 10. Testing Strategy

| Layer | Location | What it covers |
|---|---|---|
| Unit tests | `tests/unit/` | Service functions in isolation (in-memory SQLite) |
| API tests | `tests/api/` | All HTTP endpoints: happy path, auth failures, 400/403/404 |
| Test runner | `run_tests.sh` | Runs `pytest` and prints pass/fail summary |

Key fixtures in `tests/conftest.py`:
- One user per role with a known password.
- Seeded org hierarchy: School → Major → Class → Cohort with members.
- Seeded published paper with cohort assignment.
- `login_as(client, username)` helper for authenticated endpoint tests.
