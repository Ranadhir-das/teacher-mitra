# Applications and admissions

The Applications & Admissions navigation entry opens `/applications/`. Each lead
also links to its applications and a creation form prefilled from its selected
university, course and academic details. The existing student/Lead, university
and course models are reused. Admission confirmation now uses the separate
enrollment record described in [Documents and Enrollment](DOCUMENTS_ENROLLMENT.md).

## Permissions

- Active Admin and Super Admin users can manage all applications.
- Active Team Leaders can manage all applications, explicitly implementing the
  application-wide oversight requirement. Existing Lead page and mutation
  permissions are unchanged; cross-team application detail does not link to an
  inaccessible Lead page.
- Active counsellors can create, view and update applications only while the
  lead is assigned to them. Reassignment immediately changes access, including
  access to application history. Creator identity does not grant lasting access.
- Partners and inactive users have no application access. Archived leads retain
  readable history but cannot receive new applications or application edits.
- Django admin additionally requires normal staff access. The same scoped forms,
  service authorization, validation and audit writes apply there. Deletion is
  disabled; history is read-only and records are protected by foreign keys.

## Workflow

New applications start in DRAFT or STARTED.

| Current status | Allowed next statuses |
| --- | --- |
| DRAFT | STARTED, CANCELLED |
| STARTED | SUBMITTED, CANCELLED |
| SUBMITTED | UNDER_REVIEW, APPROVED, REJECTED, CANCELLED |
| UNDER_REVIEW | APPROVED, REJECTED, CANCELLED |
| APPROVED, REJECTED, CANCELLED | None |

Details and remarks remain editable after a decision, with an audit event.
The lead cannot be changed. The offering can change only before submission.
New offerings must belong to the selected university, be active, and have an
open or upcoming intake. Existing applications remain editable after catalogue
deactivation. Courses used by applications cannot move to another university.

Submission defaults to today's local date when moving to SUBMITTED. Historical
submission dates can be supplied; future dates and dates on Draft/Started
applications are rejected. Clearing an existing submission date preserves it.
Reference is optional and not globally unique, because universities can use
overlapping references; each application also has a unique internal numeric ID.
Academic details are a text snapshot, prefilled from the lead when creating via
its link; later Lead edits do not overwrite the application's academic record.

## Lead synchronization and auditing

| Application progress | Lead status |
| --- | --- |
| STARTED | APPLICATION_STARTED |
| SUBMITTED, UNDER_REVIEW | APPLICATION_SUBMITTED |
| APPROVED | APPLICATION_SUBMITTED (enrollment confirmation is separate) |
| DRAFT, REJECTED, CANCELLED | Unchanged |

Synchronization only advances these milestones. PAYMENT_PENDING and
ADMISSION_CONFIRMED are never regressed by a less advanced application. Rejecting
or cancelling one application does not mark the whole lead Lost or undo another
application's progress. This is milestone tracking, not a recalculation of lead
status from currently open applications.

`apps.applications.services.save_application` is the write entry point for CRM
and admin. It validates a field allowlist, checks current lead access, locks the
lead before the application, saves field snapshots and status history, and
updates Lead status/history in one transaction. No-op saves add no audit noise.
Timeline events capture the actor, time, previous/new status and before/after
values for all changed application fields. Direct ORM bulk updates bypass the
service and must not be used for application workflow mutations.

## Migration and validation

`applications/0001_initial.py` creates Application and ApplicationStatusHistory,
with protected references to existing models and a database status constraint.
It depends on the existing catalogue migrations and Lead migration 0003.

```powershell
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe manage.py test
```

Application tests cover permissions and reassignment, browser routes and forms,
CSRF, admin writes/isolation, status progression, dates, catalogue validation,
audit snapshots, rollback, protected records, search/pagination, and multiple
applications sharing a lead.

## Scope and limitations

This stage implements CRM pages and Django admin, without a new REST endpoint,
university submission integration or payment processing. Document uploads and
enrollment are covered in [Documents and Enrollment](DOCUMENTS_ENROLLMENT.md).
Payment-dependent confirmation and reopening terminal decisions would require
additional business rules.
SQLite does not enforce row-level `select_for_update` locking; simultaneous-write
behavior should be exercised against the production database before relying on
multi-worker concurrency guarantees. Tests here use the configured test database.
