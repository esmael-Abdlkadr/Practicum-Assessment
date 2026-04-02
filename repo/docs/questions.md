## Scope Model Design Decision

**Question:** The original prompt specifies a full hierarchical data-scope model:
self / own department / sub-departments / global scope, plus school/major/class/cohort axes.
How was this implemented?

**My Understanding:** The prompt describes a governance system with layered access: a user
may have access scoped to themselves, their own cohort, their school/major/class hierarchy,
their department, or globally across all departments.

**Solution:** The implemented scope model uses a cohort-based access control approach:
- `dept_admin` has global read/write access to all data.
- `faculty_advisor` and `corporate_mentor` access only the cohorts they are explicitly
  assigned to via `CohortMember`.
- `student` can only access their own attempts and assignments.
- Fine-grained permission templates and temporary delegations allow admins to grant
  additional named permissions (e.g., `cohort:view`, `report:export`, `role:faculty_advisor`)
  to individual users.

The full dept/sub-dept/global scope hierarchy (e.g., "advisor sees all cohorts under their
department but not another department's cohorts") was not implemented as a distinct policy
engine. The cohort assignment model covers the primary use case described in the prompt
(advisors and mentors see only their assigned cohorts). A full department-hierarchy resolver
would require an additional org-unit-to-user mapping table and policy evaluation layer,
which was scoped out in favour of delivering the complete assessment and quiz workflow.
