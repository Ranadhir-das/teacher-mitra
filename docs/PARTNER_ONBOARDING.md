# Partner onboarding

Partners register through the existing signup page or `POST /api/v1/partners/signup/` and can immediately log in. Their dashboard remains limited until approval.

The workflow is REGISTERED → ONBOARDING → SUBMITTED → Approved / CHANGES_REQUIRED / REJECTED. Approved retains the existing database value `ACTIVE` for compatibility. Changes required allows editing and resubmission. Rejected partners can view the decision but cannot edit onboarding or manage leads. Suspended/inactive accounts cannot log in.

Partners save profile drafts at `/partner/onboarding/`, upload documents and submit. Required documents are cancelled cheque and ID/address proof; PAN/GST proof is required when applicable, and organization proof for business partner types. Tax non-applicability requires an explanation. Optional additional required types can be configured with `PARTNER_REQUIRED_DOCUMENT_TYPES` using supported onboarding document codes, including `OTHER`.

Administrators use **Partners → Approval / onboarding queue → Review onboarding**. Verify every required document before approving, or provide feedback when requesting changes/rejecting. The Django Partner admin links to the same review screen. Submitted profiles are locked; request changes before editing.

Documents reuse the private Document storage and history system. PDF, JPEG and PNG uploads are limited to 10 MB and validated by content. Downloads require owner or administrator permission. Do not expose `PRIVATE_DOCUMENT_ROOT` through a public media route. Include this directory in protected backups.

API endpoints:

- `GET/PATCH /api/v1/partners/my/onboarding/`
- `POST /api/v1/partners/my/onboarding/documents/` (multipart `document_type`, `file`)
- `GET /api/v1/partners/my/onboarding/documents/<id>/file/`
- `POST /api/v1/partners/my/onboarding/submit/`
- `GET/POST /api/v1/partners/<id>/onboarding/` (admin; `decision`: approve, reject, changes; `feedback`)
- `GET/POST /api/v1/partners/onboarding-documents/<id>/` (admin download/review; `decision`: verify, reject; `reason`)

Apply migrations with `python manage.py migrate`. Existing approved partners retain access. Legacy pending registrations become REGISTERED; previously self-registered inactive logins are enabled for limited onboarding. Internally provisioned disabled logins are left disabled and can be enabled by an administrator. Existing rejected accounts retain their current login activation setting.

Run `python manage.py check`, `python manage.py makemigrations --check --dry-run`, and `python manage.py test --noinput` before deployment.
