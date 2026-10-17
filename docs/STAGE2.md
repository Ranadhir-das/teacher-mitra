# Stage 2: Lead/Student CRM

This stage extends the existing project without replacing the custom User, authentication, roles, employee pages or API namespace. No dependency changes were required.

## Models and migrations

- `accounts.Team`: name, leader, counsellor members and active flag. Configure teams in Django admin as a superuser. The custom User model remains unchanged in Stage 2.
- `leads.Lead`: personal, education, course preferences, contact details, budget, source, status, priority, counsellor/team ownership, creator/editor timestamps, last contact, tags, general notes and active/archive flag.
- `leads.Tag`: case-insensitive unique names, normalized to uppercase.
- `leads.LeadAssignment`: previous/new counsellor and team, actor, time and reason.
- `leads.LeadStatusHistory`: previous/new status, actor, time and note.
- `leads.LeadNote`: note text, author and timestamps. Notes are append-only in this stage.

Migrations: `accounts/0002_team.py` and `leads/0001_initial.py`. They add tables and indexes without recreating users or deleting existing data. Run `python manage.py migrate` normally. No fake migrations or manual database changes are needed.

Indexes cover name, both phones, email, city/state, status, priority, source, creation/update dates and active state; foreign keys are indexed, with composite indexes for counsellor/team ownership queries. Status and priority have database check constraints. Shared queryset helpers use `select_related` and `prefetch_related`; a test verifies list query count does not grow with each lead.

University/Course models do not exist yet. `desired_course`, `desired_specialization` and `preferred_university` preserve the student's free-text preferences. A later migration can add nullable catalogue foreign keys alongside these fields, backfill known matches, and retain unmatched text without breaking the current API.

Students are a filtered view of Lead records with `ADMISSION_CONFIRMED` status, not a second copy of student data. Application-related status labels are supported; application/payment/admission transaction modules are not implemented.

## Permission policy

| User | Visibility | Create | Edit/status/notes/tags | Assign | Archive/restore |
| --- | --- | --- | --- | --- | --- |
| Super admin / Admin | All leads | Yes | Yes | Any lead; active counsellors only | Yes |
| Team leader | Leads explicitly owned by their active teams | In their permitted teams | Within their teams | Within their permitted teams; counsellor must be a team member | Only with explicit archive permission |
| Counsellor | Leads assigned to themselves | No | Their active leads | No by default | No by default |

Archived records remain readable within the same ownership scope but are read-only until restored. An inactive Team revokes its leader's team scope. A counsellor's access is based on the actual lead assignment. Unassigned/no-team leads are admin-only. Unknown roles fail closed.

`leads.reassign_lead` may be explicitly granted through Django permissions. It allows a counsellor to reassign an accessible lead only within its existing active team, of which the actor must be a member. It does not widen lead visibility. `leads.archive_lead` similarly permits archival only within the actor's existing scope. Employee-management rules from Stage 1 are unchanged.

All list, detail, write, history, note, dashboard and bulk paths enforce the same scoped querysets on the server. Out-of-scope detail IDs return 404, while forbidden actions on visible records return 403. Filters never widen scope. `/my/` further restricts the already-scoped queryset to the authenticated assignee, including for admins.

The regular edit form and PATCH endpoint accept only the documented editable personal/education/preference/source/priority/general-note fields and tags. Ownership, status, creator, timestamps and archive state use separate service actions. Unknown API input fields are rejected instead of silently ignored.

## Workflow and audit

`apps/leads/services.py` is the write boundary shared by web, API and demo seeding. Transactions combine lead changes with their audit records. Updates lock the lead row on databases supporting `SELECT FOR UPDATE`. Bulk actions lock IDs in stable order and roll back the entire operation when any record is unavailable or any transition fails.

Use these services for future importers and management commands; direct ORM `update()`, bulk writes or `save()` bypass application workflow/audit behavior. Django admin Lead/history/note pages are read-only so they cannot bypass it. Permanent lead deletion is not exposed; protected audit relations preserve history.

Every creation records an initial NEW event. Assigning a counsellor to a NEW lead also records NEW -> ASSIGNED. Removing a counsellor from an ASSIGNED lead records ASSIGNED -> NEW. Reassignments and team-only changes record previous/new ownership. No-op assignments/status requests do not invent history entries. Archival/restoration adds an attributed system note and updates the editor/time.

Non-admin transitions are defined in `apps/leads/workflow.py`:

```text
NEW -> ASSIGNED
ASSIGNED -> CONTACTED / NO_RESPONSE / WRONG_NUMBER
CONTACTED -> INTERESTED / NO_RESPONSE / WRONG_NUMBER / NOT_INTERESTED / NOT_ELIGIBLE
INTERESTED -> COUNSELLING / NOT_INTERESTED / LOST
COUNSELLING -> COURSE_SELECTED / NOT_ELIGIBLE / LOST
COURSE_SELECTED -> APPLICATION_STARTED / LOST
APPLICATION_STARTED -> APPLICATION_SUBMITTED / LOST
APPLICATION_SUBMITTED -> PAYMENT_PENDING / ADMISSION_CONFIRMED / LOST
PAYMENT_PENDING -> ADMISSION_CONFIRMED / LOST
NO_RESPONSE / WRONG_NUMBER / NOT_INTERESTED / NOT_ELIGIBLE -> CONTACTED / LOST
```

LOST and ADMISSION_CONFIRMED are terminal for non-admins. Admins may make exceptional transitions to any valid status; ASSIGNED still requires a counsellor. Enter a note to explain an exceptional change. Moving to CONTACTED updates `last_contacted_at`. This is not call tracking; no call or follow-up module is added.

## Validation and duplicates

Name and phone are required. Phone punctuation is removed and 7-15 digits are required. Country codes are not guessed: a local-format number and an international-format number may not match, so use a consistent country-code convention when importing records. Email is validated and lowercased; optional birth dates cannot be in the future. Passing years must be 1950 through next year. Budget cannot be negative. A bare score means a percentage (0-100); CGPA uses an explicit scale such as `8.2/10` or `3.5/4`.

Creation and changes to phone/email warn about matches in primary phone, alternate phone or case-insensitive email, including archived records. There is no automatic merge or deletion and no hard uniqueness constraint on lead contacts. Admins and team leaders can acknowledge the warning with `confirm_duplicate=true`; counsellors must ask an administrator to resolve a conflicting contact edit. Warnings show up to 10 matches within the user's scope, never names/contact details of private records outside that scope. Concurrent creates can still race because duplicate detection is advisory rather than a uniqueness constraint.

## Web pages

| URL | Function |
| --- | --- |
| `/leads/` | Search, filter, sort, paginate, select leads |
| `/students/` | Admission-confirmed leads, same access rules |
| `/leads/new/` | Sectioned create form |
| `/leads/<id>/` | Details, tags, chronological notes and both histories |
| `/leads/<id>/edit/` | Edit permitted information |
| `/leads/<id>/assign/` | Assignment form and confirmation |
| `/leads/<id>/status/` | Allowed transitions and explanatory note |
| `/leads/<id>/note/` | Add note |
| `/leads/<id>/archive/` | Confirm archive or restore |
| `/leads/bulk/` | POST selected IDs to a review screen, then explicitly confirm |
| `/leads/tags/` | Admin create/list tags |
| `/leads/tags/<id>/` | Admin rename tag |
| `/` | Scoped live lead counts, recent leads, status chart and top sources |

Bulk assignment and bulk status changes accept 1-100 selected leads. The first POST only displays a review form; the second confirmed POST applies the action. Each changed lead receives its own audit entry. Failed batches make no partial changes. There is no bulk permanent deletion.

The UI reuses the existing Bootstrap shell, colors and components. It includes breadcrumbs, badges, role-aware actions, responsive forms/tables, empty states, pending-submit feedback, flash messages and server-rendered confirmation screens. Tag renames update existing relationships; no duplicate tags are created.

## API

All endpoints use the existing JWT bearer authentication. Session authentication is still reserved for the web UI.

| Method | Endpoint | Behavior |
| --- | --- | --- |
| GET / POST | `/api/v1/leads/` | Scoped paginated list / create |
| GET / PATCH | `/api/v1/leads/<id>/` | Detail / permitted field edits |
| DELETE | `/api/v1/leads/<id>/` | Soft archive; returns 204 |
| POST | `/api/v1/leads/<id>/restore/` | Restore archived lead |
| GET | `/api/v1/leads/my/` | Only the authenticated user's assigned leads |
| POST | `/api/v1/leads/<id>/assign/` | Assign or unassign counsellor/team |
| POST | `/api/v1/leads/<id>/status/` | Validated status transition |
| GET / POST | `/api/v1/leads/<id>/notes/` | Paginated chronological notes / add note |
| GET | `/api/v1/leads/<id>/history/` | Chronological `assignments` and `statuses` arrays |
| GET | `/api/v1/tags/` | Available tags and IDs |

Examples:

```json
POST /api/v1/leads/
{
  "full_name": "Example Student",
  "phone": "12025550180",
  "email": "student@example.invalid",
  "desired_course": "Online MBA",
  "priority": "HIGH",
  "lead_source": "WEBSITE",
  "assigned_counsellor": 4,
  "assigned_team": 1,
  "tags": [1, 2]
}
```

Counsellor/team/tag IDs in examples must be replaced with actual authorized IDs. Creation always starts at NEW and moves to ASSIGNED when a counsellor is selected; use the status action for later workflow changes.

```json
POST /api/v1/leads/15/assign/
{"assigned_counsellor": 4, "assigned_team": 1, "reason": "Team allocation"}

POST /api/v1/leads/15/status/
{"status": "CONTACTED", "note": "Student responded"}

POST /api/v1/leads/15/notes/
{"note": "Requested course details."}

PATCH /api/v1/leads/15/
{"desired_course": "MCA", "priority": "URGENT", "tags": [2]}
```

Assignment requires both `assigned_counsellor` and `assigned_team` keys; explicit `null` unassigns/clears the value, subject to role rules. PATCH uses tag IDs to replace the tag set; omitting `tags` preserves it. Read responses return nested `{id, name}` counsellors and tags, plus human-readable `status_display`, `priority_display`, `source_display`, team name, dates and active status. Staff flags, passwords and auth details are not exposed.

Duplicate requests return HTTP 409 with `code: possible_duplicate`, a detail message, authorized match summaries and the confirmation field name. Authorized users can resend the request with `confirm_duplicate: true`. Other validation failures return 400, missing/invalid auth 401, denied actions 403 and unavailable records 404. List responses use DRF's `count`, `next`, `previous`, `results` envelope.

### Shared search and filter parameters

Web and list/my API endpoints share the same filters:

- `search`: name, phone, alternate phone or email; common phone punctuation is normalized.
- `status`, `priority`, `lead_source`: exact enum values.
- `assigned_to`: permitted counsellor ID.
- `created_from`, `created_to`: inclusive YYYY-MM-DD dates in the configured timezone.
- `city`, `state`: case-insensitive exact matches.
- `activity`: `active` (default), `archived`, `all`.
- `sort`: `newest` (default), `oldest`, `name`, `priority` (urgent first), `updated`.
- `page` and `page_size`: 20 (default), 50 or 100 records per page.

Filters compose and ordering/pagination run in the database. Invalid API filters produce 400; the web form shows validation errors and an empty result set. Example:

```text
/api/v1/leads/?status=INTERESTED&assigned_to=5&lead_source=FACEBOOK&sort=updated&page_size=50
```

## Demo data

```powershell
.\.venv\Scripts\python manage.py seed_demo
```

The idempotent command creates 20 clearly labelled synthetic students, 2 teams, 2 team leaders, 4 counsellors, 1 demo admin and 8 tags. It uses `example.invalid` emails and fictional 202-555-01xx phone numbers. It includes diverse priorities/sources, all initial statuses, notes, creation/status histories, initial assignments and a reassignment example. It runs in one transaction and skips already-seeded leads without resetting changes.

New demo users have unusable passwords. Use your own superuser to inspect them. To intentionally sign in as a demo role for local review, set its password through `python manage.py changepassword <demo-email>`; no fixed demo password is stored or printed. Demo data is for local development, not production. There is no command that wipes real records.

## Verification and limitations

Latest local verification: **66 tests passed** (21 Stage 1 tests and 45 Stage 2 tests). Django system checks reported no issues, migration drift check reported no changes, static collection succeeded, and `pip check` reported no broken requirements. The development server was restarted and 10 authenticated web pages plus 8 authenticated list/filter API requests returned HTTP 200. Demo admin scope returned 20 leads; the tested demo counsellor returned only their 4 assigned leads, including `/my/`.

Run the full suite with `python manage.py test`, plus `check`, `makemigrations --check --dry-run`, `collectstatic --noinput` and `python -m pip check`. Tests use a disposable database.

Stage 2 coverage includes valid/invalid fields, enum constraints, normalized contact matching, explicit duplicate confirmation, private duplicate redaction, all role scopes, cross-ID URL access, team restrictions, delegation, assignment/no-op/unassignment history, workflow exceptions/invalid transitions, notes, tags, archival/restoration, bulk confirmation/rollback, web forms/CSRF, JWT-authenticated API CRUD/actions, malformed JSON, search/filter/sort/pagination, dashboard/student scope, query efficiency, read-only audit admin and idempotent demo creation. All Stage 1 tests remain in the suite.

Local SQLite migrations and tests are verified. PostgreSQL integration and browser visual QA are not verified in this environment. SQLite does not provide PostgreSQL-style row locks; production concurrency validation should use PostgreSQL. Substring search is practical at this stage; ordinary B-tree indexes do not accelerate every `icontains` search, so consider PostgreSQL trigram/full-text indexes when data size warrants it. Complete per-lead histories are returned by the history endpoint; very long-lived records may need history pagination later.

Team membership is configured in Django admin by a superuser; no separate team-management CRM screen is included. Sources and workflow choices are extended through code and migrations. No Android caller, follow-up/call execution, application processing, document handling or commission calculation was built in Stage 2.
