# Counsellor management

Open **Employees** in the CRM sidebar (`/accounts/employees/`). Admins,
Super Admins and Team Leaders can create counsellors, browse/filter the list,
inspect profiles/workloads, and update permitted accounts. Counsellors are managed
inside the existing Employee list, creation form, edit form and profile. There is
no separate Counsellors section. Use the Role filter to show counsellors.

## Existing models are reused

Counsellors are existing `accounts.User` rows with role `COUNSELLOR`. The historical `Counsellor` proxy uses the same table and is no longer
registered as a separate Django admin section. Team memberships remain `Team.members` / the
User's `crm_teams`; multiple teams remain supported. Leads, Applications,
Admissions and FollowUps are queried from their existing models.

User gains optional username, employee ID, joining date, account status and
profile information. Name, email, phone, password and profile photo remain the
existing User fields. The shared Employee form manages employment details, profile text and the
existing profile-photo upload.
New counsellors require a name, unique email, unique username, unique employee ID
and validated password. Phone is optional; supplied phones use the CRM's existing
7–15 digit normalization. Joining date and profile text are optional.

Email/username uniqueness is case-insensitive; employee IDs are normalized to
uppercase and case-insensitively unique. Usernames use letters, numbers, dots,
hyphens and underscores, and cannot contain `@` (avoids email/username ambiguity).

The creation service hashes the password and creates an immediately login-ready
account with role COUNSELLOR and no staff/superuser privileges. It does not sign
the manager out or impersonate the new user. Both web login and the existing JWT
login support email or username. JWT requests can supply either `email` or
`username`, together with `password`; supplying both identifiers is rejected.

## Role boundaries

| Actor | Counsellor management |
| --- | --- |
| Super Admin | All counsellors, including privileged accounts |
| Admin | All ordinary counsellors; existing employee restrictions protect staff/superusers |
| Team Leader | Counsellors in active teams they lead; must choose an owned team on creation |
| Counsellor / Partner | No counsellor-management access |
| Inactive or blocked account | Cannot sign in |

Team Leaders cannot transfer accounts outside their teams, remove every team,
reset passwords, or change role/staff/superuser flags. A counsellor shared with
another leader's team remains visible but requires an administrator for changes,
since status/profile changes affect the whole account. Inactive team memberships
are also protected from cross-team edits. Admins can retain existing inactive
memberships but cannot newly assign inactive teams.

Team membership changes do not move leads or rewrite assignment history. Existing
lead-assignment workflows remain responsible for reassignment. Deactivation and
blocking also preserve assignments so an administrator can explicitly reassign
outstanding work.

## Status and passwords

Statuses are ACTIVE, INACTIVE and BLOCKED. ACTIVE maps to `User.is_active=True`;
the other statuses map to False. This keeps existing session and JWT activity
checks effective. The User save path synchronizes legacy `is_active` edits with
the new status field. The Employee status action supports blocking and records
counsellor status changes in management history. Existing partner-account activation was updated to keep
these fields consistent as well. Application code must use these service/save
paths instead of raw bulk status updates.

Administrators can set a new password from a counsellor profile. Password
confirmation and Django password validators apply. A reset invalidates Django
session authentication hashes and existing JWT access tokens; outstanding refresh
tokens are blacklisted. No password or password hash is written into management
history. The new password must be communicated securely outside this workflow;
this implementation does not email credentials.

Management writes use transactions, current permission checks and field
allowlists. `CounsellorHistory` captures creation, profile/status/team changes and
password-reset events; no-op profile saves do not add history. Existing generic
employee and superuser User-admin operations remain available and are not
retroactively included in this focused history.

## Profile and dashboard

Counsellor profiles show contact and employment fields, teams, last login,
profile information, assigned leads, applications, follow-ups, performance
statistics, recent activity and the latest 30 management events. Workload sections
are paginated independently (10 per page). The counsellor list has name/email/
phone/username/employee-ID search, team/status filters, role filtering, and 20 records per page.

All profile workload queries intersect the subject's assignments with the
viewer's existing Lead/Application/FollowUp access. Knowing a counsellor's ID or
team does not grant additional Lead access. Reassignment changes visibility
immediately.

Counsellor dashboards include assigned leads, up to 10 outstanding follow-ups
scheduled today in the configured timezone, up to 10 pending applications and
the latest 15 accessible activity entries. Pending means DRAFT, STARTED,
SUBMITTED or UNDER_REVIEW. Today's follow-ups excludes COMPLETED/CANCELLED.
Recent activity includes lead status changes, lead notes, application changes
and follow-up updates. Links lead to the existing full lists/details.

Statistics are a **current workload snapshot**, not historical employee-credit
attribution:

- Lead/application counts use currently assigned active leads accessible to the viewer.
- Follow-up counts also require the counsellor to be the task assignee.
- Overdue counts include outstanding tasks scheduled before now.
- Confirmed admissions count distinct currently assigned leads with CONFIRMED admissions.
- Conversion is those confirmed leads divided by assigned active leads, or 0
  for an empty workload. Reassignment and archival therefore change the figures.

## Django admin

The existing superuser-only User admin includes the employment fields. There is
no separate Counsellors admin list. CounsellorHistory remains a read-only audit
list with the same team scope. CRM Employees is the shared management interface
for Admins and Team Leaders; its counsellor writes retain service validation,
password rules and permission checks.

## Migration and deployment

`accounts/0004_counsellorhistory_counsellor_user_account_status_and_more.py`
adds the new User fields, case-insensitive uniqueness/status constraints,
Counsellor proxy and CounsellorHistory. It backfills INACTIVE for existing
disabled users. Existing passwords, roles, team memberships and assignments are
preserved. Existing users retain email login; missing employee IDs/usernames can
be supplied when editing their counsellor profiles. The migration does not invent
joining dates or employee identifiers.

The authentication backend changes to EmailOrUsernameBackend. Existing browser
sessions using the former backend need to sign in again after deployment.

```powershell
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe manage.py test
```

## Employee integration

The Employee forms now expose username, employee ID, joining date, status,
profile information and teams. Employee profiles include counsellor workload,
performance, recent activity, account history and password-reset actions. The
Employee list supports search plus role/status/team filters. Team Leaders see
only counsellors in their teams, and their Employee forms lock role to COUNSELLOR.
Global Admin-only employee privileges are unchanged.

The standalone counsellor list/form/detail templates and URLs were removed.
Shared workload, statistics and activity partials remain for Employee profiles
and the counsellor dashboard. No database changes were needed for this UI
integration; the previously applied User fields and account migration are reused.

Integration changes touch `apps/accounts/forms.py`, `views.py`, `permissions.py`,
`urls.py`, `admin.py`, the reduced `counsellor_forms.py` / `counsellor_views.py`,
account tests, `templates/base.html`, Employee templates and the shared
`employee_workload.html` partial. Login, data isolation and the personal
counsellor dashboard remain in place.

## Remaining scope

No management REST CRUD endpoints, invitation emails, historical performance
attribution or automatic lead reassignment are added. Production database
concurrency has not been exercised; local validation uses SQLite.
