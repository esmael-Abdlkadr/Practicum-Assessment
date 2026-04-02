# api-spec.md — REST Endpoint Reference

> All endpoints return **HTML** (Jinja2 full pages or HTMX fragments) unless noted as CSV or redirect.  
> Authentication is enforced via server-side session. Unauthenticated requests redirect to `GET /login`.  
> Error responses return HTTP `4xx` with an HTMX-compatible `<div class="alert">` fragment or a redirect.

---

## Base URL

```
http://localhost:5000
```

---

## Authentication (`/`)

### `GET /login`
Returns the login page (full page).

### `POST /login`
Submits credentials.

| Field | Type | Required | Notes |
|---|---|---|---|
| `username` | string | yes | |
| `password` | string | yes | |
| `captcha` | string | conditional | Required after 3 failed attempts |

**Responses:**

| Status | Description |
|---|---|
| 302 `/dashboard` | Credentials valid, no MFA |
| 302 `/login/mfa` | Credentials valid, MFA enabled |
| 200 (fragment) | Invalid credentials — inline error, CAPTCHA if threshold reached |
| 200 (fragment) | Account locked — shows unlock time |

---

### `GET /login/mfa`
Returns the MFA verification page.

### `POST /login/mfa`
Submits TOTP code.

| Field | Type | Required |
|---|---|---|
| `code` | string (6 digits) | yes |

**Responses:** 302 `/dashboard` on success; 200 error fragment on invalid code.

---

### `GET /logout`
Clears session and redirects to `GET /login`.

### `GET /dashboard`
Returns the role-specific dashboard (full page). Requires session.

---

### `GET /reauth`
Returns the re-authentication page (full page).

### `POST /reauth`
Submits password for high-risk action re-auth.

| Field | Type | Required |
|---|---|---|
| `password` | string | yes |

**Responses:** 302 to `next` param on success; 200 error fragment on failure.

---

### `GET /switch-role`
Returns the role-switch form listing available roles.

### `POST /switch-role`
Changes the active role. **Requires re-auth (high-risk action).**

| Field | Type | Required |
|---|---|---|
| `role` | string | yes | One of: `student`, `faculty_advisor`, `corporate_mentor`, `dept_admin` |

**Responses:** 302 `/dashboard` on success; 302 `/reauth` if re-auth expired.

---

## MFA Settings (`/settings/mfa`)

### `GET /settings/mfa`
Returns MFA settings page showing current status.

### `GET /settings/mfa/setup`
Returns MFA setup page with QR code (inline data URI) and secret.

### `POST /settings/mfa/setup`
Initialises TOTP secret (saves to session pending verification).

**Response:** 200 fragment with QR code.

### `POST /settings/mfa/verify-setup`
Confirms TOTP setup by verifying a live code.

| Field | Type | Required |
|---|---|---|
| `code` | string (6 digits) | yes |

**Response:** 200 success fragment on valid code; 200 error fragment on invalid.

### `POST /settings/mfa/disable`
Disables MFA. **Requires re-auth.**

**Response:** 302 `/settings/mfa` on success.

---

## Admin — User Management (`/admin/users`)

> All routes require `dept_admin` role.

### `GET /admin/users`
Returns user list page with search/filter controls.

### `POST /admin/users`
Creates a new user account.

| Field | Type | Required | Notes |
|---|---|---|---|
| `username` | string | yes | Unique |
| `full_name` | string | yes | |
| `email` | string | yes | |
| `role` | string | yes | `student` / `faculty_advisor` / `corporate_mentor` / `dept_admin` |
| `student_id` | string | no | Encrypted at rest |

**Response:** 200 fragment with `<details>` block revealing temporary password (secure reveal).

### `GET /admin/users/<id>/edit`
Returns user edit form fragment.

### `PUT /admin/users/<id>`
Updates user profile fields.

**Response:** 200 updated row fragment.

### `POST /admin/users/<id>/reset-password`
Resets password to a system-generated temporary value.

**Response:** 200 fragment with `<details>` secure-reveal block.

### `POST /admin/users/<id>/activate`
Re-activates a deactivated user account.

### `POST /admin/users/<id>/deactivate`
Deactivates a user account.

### `POST /admin/users/<id>/unlock`
Clears account lockout (`User.locked_until`, `User.failed_attempts`).

### `GET /admin/users/<id>/reveal-student-id`
Returns decrypted student ID. Requires `dept_admin` + re-auth.

**Response:** 200 plaintext fragment.

---

## Admin — Organisation (`/admin/org`)

> All routes require `dept_admin` role.

### `GET /admin/org/schools`
Returns organisation management page (schools, majors, classes, cohorts).

### Schools

| Method | Path | Description |
|---|---|---|
| `POST` | `/admin/org/schools` | Create school (`name`, `code`) |
| `PUT` | `/admin/org/schools/<id>` | Update school |
| `DELETE` | `/admin/org/schools/<id>` | Delete school |

### Majors

| Method | Path | Description |
|---|---|---|
| `POST` | `/admin/org/majors` | Create major (`school_id`, `name`, `code`) |
| `PUT` | `/admin/org/majors/<id>` | Update major |
| `DELETE` | `/admin/org/majors/<id>` | Delete major |

### Classes

| Method | Path | Description |
|---|---|---|
| `POST` | `/admin/org/classes` | Create class (`major_id`, `name`, `year`) |
| `PUT` | `/admin/org/classes/<id>` | Update class |
| `DELETE` | `/admin/org/classes/<id>` | Delete class |

### Cohorts

| Method | Path | Description |
|---|---|---|
| `POST` | `/admin/org/cohorts` | Create cohort (`class_id`, `name`, `internship_term`, `start_date`, `end_date`) |
| `PUT` | `/admin/org/cohorts/<id>` | Update cohort |
| `DELETE` | `/admin/org/cohorts/<id>` | Delete cohort |

### `GET /admin/org/cohorts/<id>/members`
Returns cohort member list fragment.

### `POST /admin/org/cohorts/<id>/members`
Adds a user to the cohort.

| Field | Type | Required |
|---|---|---|
| `user_id` | integer | yes |

### `DELETE /admin/org/cohorts/<id>/members/<user_id>`
Removes a user from the cohort.

---

## Admin — Question Bank (`/admin/questions`)

> Requires `dept_admin` role.

### `GET /admin/questions`
Returns question list with filter controls.

### `POST /admin/questions`
Creates a new question.

| Field | Type | Required | Notes |
|---|---|---|---|
| `question_type` | string | yes | `single_choice` / `multiple_choice` / `true_false` / `fill_in` / `short_answer` |
| `content` | string | yes | Question stem |
| `tags` | string | no | Comma-separated |
| `difficulty` | integer | no | 1–5 |
| `options` | JSON array | conditional | Required for choice types |
| `correct_answer` | string | conditional | Required for auto-graded types |

### `GET /admin/questions/<id>/edit`
Returns question edit form fragment.

### `PUT /admin/questions/<id>`
Updates question. Returns updated row fragment.

### `DELETE /admin/questions/<id>`
Deletes question (fails if used in a published paper).

### `GET /admin/questions/<id>/rubric`
Returns rubric editor for `short_answer` questions.

### `POST /admin/questions/<id>/rubric`
Saves rubric criteria.

---

## Admin — Papers (`/admin/papers`)

> Requires `dept_admin` role.

### `GET /admin/papers`
Returns paper list page.

### `GET /admin/papers/new`
Returns new paper form.

### `POST /admin/papers`
Creates a new paper (draft).

| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | string | yes | |
| `time_limit` | integer | no | Minutes; default 45 |
| `max_attempts` | integer | no | Default 1, max 3 |
| `available_from` | datetime | no | |
| `available_to` | datetime | no | |
| `randomise` | boolean | no | Per-student question shuffle |
| `draw_count` | integer | no | Questions to draw from pool |

### `GET /admin/papers/<id>`
Returns paper builder page (question list + settings).

### `POST /admin/papers/<id>/questions`
Adds a question to the paper.

| Field | Type | Required |
|---|---|---|
| `question_id` | integer | yes |

### `DELETE /admin/papers/<id>/questions/<qid>`
Removes a question from the paper.

### `PUT /admin/papers/<id>/questions/reorder`
Reorders paper questions.

| Field | Type | Required |
|---|---|---|
| `order` | JSON array of integers | yes |

### `POST /admin/papers/<id>/publish`
Publishes the paper (sets `status = published`). Validates at least one question exists.

### `POST /admin/papers/<id>/close`
Closes the paper (sets `status = closed`).

### `GET /admin/papers/student/available`
Returns papers available to the current student (published, within window, cohort-assigned).

---

## Quiz (Student Flow)

> All routes require `student` role.

### `GET /quiz`
Returns quiz list showing available papers.

### `POST /quiz/<paper_id>/start`
Starts a new quiz attempt.

**Pre-conditions checked (403 if violated):**
- Paper status must be `published`.
- Student's cohort must be assigned to this paper.
- Student must not have exceeded `max_attempts`.

**Response:** 302 `GET /quiz/<paper_id>/take`

### `GET /quiz/<paper_id>/take`
Returns the quiz-taking page with timer, questions, and autosave indicators.

### `POST /quiz/<paper_id>/autosave`
Saves current answers without submitting (HTMX trigger every 15 seconds).

| Field | Type |
|---|---|
| `answers` | JSON object `{question_id: answer_value}` |

**Response:** 200 fragment with last-saved timestamp.

### `POST /quiz/<paper_id>/submit`
Finalises the attempt. Duplicate-submit prevention: if `attempt.submitted_at` is set, returns 409.

**Response:** 302 `GET /quiz/<paper_id>/result/<attempt_id>`

### `GET /quiz/<paper_id>/result/<attempt_id>`
Returns the results page showing score and per-question feedback.

### `GET /quiz/<paper_id>/time-check`
Returns remaining seconds for the active attempt.

**Response:** JSON `{"remaining_seconds": 123}`

---

## Assignments

### Admin Routes (require `dept_admin`)

| Method | Path | Description |
|---|---|---|
| `GET` | `/admin/assignments` | List all assignments |
| `GET` | `/admin/assignments/new` | New assignment form |
| `POST` | `/admin/assignments` | Create assignment (`title`, `cohort_id`, `description`, `due_date`) |
| `POST` | `/admin/assignments/<id>/publish` | Publish assignment |
| `POST` | `/admin/assignments/<id>/close` | Close assignment |

### Student Routes

| Method | Path | Description |
|---|---|---|
| `GET` | `/assignments` | List assignments for student's cohort |
| `GET` | `/assignments/<id>` | Assignment detail + submission form |
| `POST` | `/assignments/<id>/save` | Save draft submission |
| `POST` | `/assignments/<id>/submit` | Final submission |

### Grader Routes (Faculty Advisor / Corporate Mentor)

| Method | Path | Description |
|---|---|---|
| `GET` | `/assignments/grading` | List submissions pending grading |
| `GET` | `/assignments/grading/<submission_id>` | Grading detail page |
| `POST` | `/assignments/grading/<submission_id>/grade` | Submit grade + comment |

---

## Grading (Quiz Manual Grading)

> Routes require `faculty_advisor` or `corporate_mentor` and cohort scope.

### `GET /grading`
Returns grader dashboard with pending attempts.

### `GET /grading/paper/<paper_id>`
Returns list of student attempts for a paper.

### `GET /grading/attempt/<attempt_id>`
Returns manual grading view for a single attempt.

### `POST /grading/attempt/<attempt_id>/question/<question_id>/score`
Saves manual score for a `short_answer` or `fill_in` question.

| Field | Type | Required | Notes |
|---|---|---|---|
| `score` | float | yes | Must be within question max points |
| `question_id` | integer | yes | Must belong to the paper (validated server-side) |

**Response:** 200 updated score fragment.

### `POST /grading/attempt/<attempt_id>/question/<question_id>/comment`
Adds a grading comment thread entry.

| Field | Type | Required |
|---|---|---|
| `content` | string | yes |

**Response:** 200 updated comment thread fragment.

---

## Reports

> Routes require `faculty_advisor`, `corporate_mentor`, or `dept_admin` with appropriate scope.  
> `report:export` permission required for CSV export endpoints.

### `GET /reports`
Returns reports index page listing accessible papers.

### `GET /reports/paper/<paper_id>`
Returns score summary page for a paper.

### `GET /reports/paper/<paper_id>/summary`
HTMX fragment: overall score statistics.

### `GET /reports/paper/<paper_id>/students`
HTMX fragment: per-student score table (student IDs masked).

### `GET /reports/paper/<paper_id>/difficulty`
HTMX fragment: item difficulty analysis.

### `GET /reports/paper/<paper_id>/cohort-comparison`
HTMX fragment: cohort-level score comparison.

### `GET /reports/paper/<paper_id>/export`
Redirects to `/reports/paper/<paper_id>/export/summary`.

### `GET /reports/paper/<paper_id>/export/summary`
Downloads score summary as CSV. Requires `report:export` permission.

**Response:** `Content-Type: text/csv`, `Content-Disposition: attachment; filename=summary_<paper_id>.csv`

**CSV columns:** `cohort`, `paper`, `total_students`, `avg_score`, `min_score`, `max_score`, `pass_rate`

### `GET /reports/paper/<paper_id>/export/students`
Downloads per-student scores as CSV. Student IDs are masked (`****XXXX`).

**Response:** `Content-Type: text/csv`

**CSV columns:** `username`, `student_id_masked`, `score`, `max_score`, `submitted_at`

---

## Permissions (`/admin/permissions`)

> All routes require `dept_admin` role. Mutation routes require re-auth (**high-risk action**).

### `GET /admin/permissions/templates`
Returns permission templates list.

### `POST /admin/permissions/templates`
Creates a new permission template. **Requires re-auth.**

| Field | Type | Required |
|---|---|---|
| `name` | string | yes |
| `role` | string | yes |
| `permissions` | string (JSON array) | yes |

### `POST /admin/permissions/users/<user_id>/grant`
Grants a permission (or applies a template) to a user. **Requires re-auth.**

| Field | Type | Required | Notes |
|---|---|---|---|
| `permission` | string | yes | Dot-namespaced permission string |
| `expires_at` | date | no | ISO 8601 |

**Response:** 200 success fragment.

### `GET /admin/permissions/delegations`
Returns temporary delegations list.

### `POST /admin/permissions/delegations`
Creates a temporary delegation. **Requires re-auth.**

| Field | Type | Required | Notes |
|---|---|---|---|
| `delegate_id` | integer | yes | Target user |
| `scope` | string | yes | e.g. `cohort:42` |
| `permissions` | string (JSON array) | yes | |
| `expires_in_days` | integer | no | Default 7; max 30 — returns 400 if exceeded |

### `DELETE /admin/permissions/delegations/<id>`
Revokes a delegation. **Requires re-auth.**

**Response:** 200 updated list fragment.

---

## Cohorts (User-Facing)

### `GET /cohorts`
Returns list of cohorts the current user belongs to or advises.

### `GET /cohorts/<cohort_id>`
Returns cohort detail page.

> Requires `cohort:view` permission or cohort membership.

---

## Admin — Audit Logs (`/admin/audit-logs`)

> Requires `dept_admin` role.

### `GET /admin/audit-logs`
Returns audit log viewer page.

### `GET /admin/audit-logs/search`
Returns filtered audit log fragment.

**Query parameters:**

| Param | Type | Description |
|---|---|---|
| `actor` | string | Filter by username |
| `action` | string | Prefix match on action string |
| `resource_type` | string | e.g. `user`, `paper`, `attempt` |
| `from_date` | date | ISO 8601 |
| `to_date` | date | ISO 8601 |
| `page` | integer | Pagination (default 1) |

**Response:** 200 HTML table fragment.

### `GET /admin/audit-logs/export`
Downloads full or filtered audit log as CSV.

**Response:** `Content-Type: text/csv`

---

## Admin — Anomaly Dashboard (`/admin/anomalies`)

> Requires `dept_admin` role.

### `GET /admin/anomalies`
Returns list of flagged anomalous login events.

### `POST /admin/anomalies/<flag_id>/review`
Marks an anomaly flag as reviewed.

**Response:** 200 updated row fragment.

---

## System

### `GET /health`
Health check endpoint used by Docker healthcheck.

**Response:** `200 OK` with body `{"status": "ok"}`

### `GET /`
Home page — redirects authenticated users to `/dashboard`, unauthenticated to `/login`.

---

## Common Error Response Format

All error fragments returned by HTMX-targeted routes follow this pattern:

```html
<div class="alert alert-danger" role="alert">
  <strong>Error:</strong> Human-readable message here.
</div>
```

HTTP status codes used:

| Code | Meaning |
|---|---|
| 400 | Validation error (bad input) |
| 401 | Not authenticated — redirect to `/login` |
| 403 | Forbidden — insufficient role/scope/permission |
| 404 | Resource not found |
| 409 | Conflict — e.g. duplicate quiz submission |
| 500 | Server error — generic message, no stack trace |
