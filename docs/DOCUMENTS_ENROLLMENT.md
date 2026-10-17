# Documents and Admission / Enrollment

Open an Application detail page to request or upload documents, inspect document
activity, and create or manage its admission. Documents belong to an existing
Application and its Lead. An Admission belongs to one Application and derives
its Lead, University and Course from that application; these links are not
accepted as editable input. There is at most one admission per application.

## Access and Django admin

All operations reuse the application's current visibility rules: active Admins
and Team Leaders oversee all applications; counsellors work only on leads
currently assigned to them. These roles can upload, verify, reject and delete
documents and manage enrollment within that scope. Partners and inactive users
have no access. Reassignment immediately changes access, including file access.
Archived leads and their documents/admissions are readable but cannot be edited.

Django admin lists and filters Documents, DocumentHistory, Admissions and
AdmissionHistory with the same scope. Add buttons and management links open the
service-backed CRM workflow screens. Raw model edits, bulk deletion and history
edits are disabled, so admin cannot bypass validation, authorization or auditing.
Normal staff access is required to enter Django admin.

## Documents

Types: PHOTO, ID_PROOF, ACADEMIC_CERTIFICATE, MARKSHEET, OTHER.

| Action | Result |
| --- | --- |
| Request without a file | PENDING |
| Upload to new, PENDING, SUBMITTED or REJECTED document | SUBMITTED |
| Verify SUBMITTED document | VERIFIED; reviewer, time and notes stored |
| Reject SUBMITTED document | REJECTED; nonblank reason, reviewer, time and notes stored |
| Resubmit rejected document | SUBMITTED; current review fields reset, prior review retained in history |
| Delete document | File removed after transaction commit; tombstone and history retained |

A verified file cannot be silently replaced. Delete it and request/upload a new
document if replacement is required. Existing versions' filenames and decisions
remain in history; previous file bytes are removed after a successful replacement.

Uploads accept PDF, PNG and JPEG, with a default 10 MB limit. Photos require
images. Empty files, unsupported extensions, mismatched image formats, corrupted
images, missing PDF headers/EOF markers and oversized files are rejected.
Browser-provided MIME types are not trusted. PDF validation checks the container
signature, not every internal PDF object; it is not malware scanning or content
sanitization.

Files use UUID names under `PRIVATE_DOCUMENT_ROOT` (default `private_documents/`),
separate from public `MEDIA_ROOT`, and this directory is gitignored. Do not expose
it as a static/media web-server alias. Storage has no public URL. File view and
download endpoints always authorize the current user, return explicit content
types and dispositions, and use `nosniff`, a restrictive sandbox CSP and private,
no-store cache headers. Pending and deleted documents have no downloadable file.

File writes are cleaned up if their service transaction fails. Old files are
deleted on commit. Filesystem errors during post-commit cleanup are logged by
Django and may require retry/operational cleanup; storage and SQL are not a shared
transaction. These services should remain the outer write boundary for uploads.

## Admissions

Statuses: PENDING, CONFIRMED, CANCELLED.

- Create a pending or confirmed admission for a SUBMITTED, UNDER_REVIEW or
  APPROVED application.
- Confirmation requires an enrollment number and admission date. Future dates
  are rejected. Confirmation records the actor and timestamp.
- PENDING can become CONFIRMED or CANCELLED; CONFIRMED can become CANCELLED.
  Terminal decisions cannot be reopened. Remarks/payment details remain editable.
- Payment status is PENDING, PARTIAL, PAID, WAIVED or REFUNDED. It is tracking
  metadata, not a transaction ledger or a payment gateway, and is not a hard
  confirmation prerequisite.
- Confirmation atomically approves the Application (if needed), advances the
  Lead to ADMISSION_CONFIRMED, and writes admission, application and Lead history.
  Repeating the same save adds no duplicate history or confirmation timestamps.
- Application approval alone now leaves the Lead at APPLICATION_SUBMITTED (or
  its existing later milestone). It does not create an enrollment record.
- An application with an active admission cannot be rejected/cancelled until
  the admission is cancelled first. Existing application terminal rules remain.
- Cancelling one enrollment does not roll back Lead milestones or undo another
  application's admission. The admission record shows the cancellation; the Lead
  remains a historical milestone. No automatic Lost status is inferred.

Existing Lead milestones are preserved by the schema migrations. Earlier
application approvals are not backfilled into admissions because actual
enrollment numbers, dates and payment facts are unknown. Record these facts
through the new workflow for historical enrollments.

## Audit and migrations

Every document request/upload, review, resubmission and deletion records an
actor, timestamp, status change and relevant details. Admission creation, status
changes, payment changes and remarks edits record before/after values. These are
business-mutation histories, not HTTP access logs. Application detail exposes
document and admission history alongside its existing application timeline.

- `applications/0002_admission_admissionhistory_and_more.py`: Admission,
  AdmissionHistory, protected model links, unique application relation and
  admission/payment status checks.
- `documents/0001_initial.py`: Document, DocumentHistory, private file storage,
  protected links, review metadata and document status check.

```powershell
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe manage.py test
```

## Files changed in this stage

- `apps/documents/`: `models.py`, `storage.py`, `validators.py`, `services.py`,
  `forms.py`, `views.py`, `urls.py`, `admin.py`, `tests.py`, `test_support.py`,
  `migrations/0001_initial.py`.
- `apps/applications/`: `models.py`, `services.py`, `admissions.py`,
  `admission_forms.py`, `admission_views.py`, `workflow_admin.py`, `admin.py`,
  `views.py`, `urls.py`, `tests.py`, `test_admissions.py`,
  `migrations/0002_admission_admissionhistory_and_more.py`.
- `templates/documents/`: `form.html`, `detail.html`.
- `templates/applications/`: `detail.html`, `form.html`, `admission_form.html`,
  `enrollment_documents.html`.
- `config/settings.py`, `config/urls.py`, `apps/accounts/context_processors.py`,
  `.gitignore`, `docs/APPLICATIONS_ADMISSIONS.md`, this document.

## Validation and remaining scope

Forty new tests cover upload validation, private storage and file responses,
verification/rejection, deletion and replacement cleanup, rollback, permissions,
reassignment, archive restrictions, enrollment status/payment history, confirmation
synchronization, CSRF, scoped admin management and database constraints. Existing
application tests now assert that approval alone does not confirm enrollment.

No malware scanner, payment gateway, new REST API or university integration is
included. Admission confirmation does not require a particular document checklist;
mandatory types vary by course and no checklist rules were supplied. PostgreSQL
concurrency has not been exercised; SQLite does not enforce row-level locks.
