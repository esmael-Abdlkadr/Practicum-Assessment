## Scope Model Design Decision

**Question:** The original prompt specifies a full hierarchical data-scope model:
self / own department / sub-departments / global scope, plus school/major/class/cohort axes.
How was this implemented?

**My Understanding:** The prompt describes a governance system with layered access: a user
may have access scoped to themselves, their own cohort, their school/major/class hierarchy,
their department, or globally across all departments.

**Solution:** The implemented scope model provides a full hierarchical policy engine via
`rbac_service.resolve_scope()` and the `_scope_permits_cohort()` resolver. Each user's
effective scope is determined by their `UserPermission` rows (scope strings) combined with
their `CohortMember` memberships. The supported scope levels are:

| Scope String           | Access Granted                                                |
|------------------------|---------------------------------------------------------------|
| `scope:global`         | All active cohorts across the entire system                   |
| `scope:dept`           | All cohorts in the user's own department(s) and sub-depts     |
| `scope:subdept:<id>`   | All cohorts under a specific sub-department                   |
| `scope:school:<id>`    | All cohorts in a school                                       |
| `scope:major:<id>`     | All cohorts under a major                                     |
| `scope:class:<id>`     | All cohorts under a class                                     |
| `scope:cohort:<id>`    | A single specific cohort                                      |
| `scope:self`           | Only cohorts where the user is a direct member                |

The hierarchy is resolved consistently across:
- **Menu visibility / UI data**: `get_nav_for_role()` + `get_accessible_cohorts()` filter
  navigation and dashboard data to only what the user's scope permits.
- **Endpoint-level access checks**: `@require_scope("cohort")` and `@require_scope("student")`
  decorators call `can_access_cohort()` / `can_access_student()`, which evaluate the full
  scope hierarchy including department/sub-department resolution.
- **Report and grading views**: `get_accessible_cohorts()` gates which papers and student
  data are visible in reports, grading, and assignment interfaces.

Role-based defaults:
- `dept_admin` has implicit global access (bypasses scope checks).
- `faculty_advisor` and `corporate_mentor` access cohorts via `CohortMember` assignment
  plus any explicit scope grants (e.g. `scope:dept`, `scope:school:<id>`).
- `student` accesses only their own data (`assessment:view:self` permission).

Additional access can be granted via:
- `PermissionTemplate` bundles applied by admins.
- `TemporaryDelegation` records with scoped, time-limited access.

The `resolve_scope()` function provides a deterministic, testable resolver that converts
any combination of scope strings into a concrete set of cohort IDs.
