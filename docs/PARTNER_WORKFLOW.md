# Partner registration and reporting

Apply migrations with `python manage.py migrate` before starting the updated app.

- Public registration: `/partner/signup/` (also linked from login).
- Review queue: `/partners/?status=PENDING`, available to existing Admin / Super Admin roles.
- Open a registration to approve or reject it using CSRF-protected POST actions.
- Approval changes the existing Partner to ACTIVE and enables its linked login. Rejection changes it to REJECTED and disables login.
- Public registrations use their own inactive Partner-role user as `created_by`; they never receive internal CRM permissions.
- Existing status-management screens and APIs synchronize login access when status changes. Saving an unchanged status preserves an explicit login disable.
- Reports: `/partner/reports/`. Totals include all owned referrals, including archived leads. Status counts are current statuses, not historical conversion counts. Lost and Not Interested are combined; other additional CRM statuses remain visible so the distribution reconciles to the total.
- The daily creation chart covers the last 30 calendar days in the configured timezone, including zero-count days. Activity shows the latest ten owned lead status events, without internal notes or staff identities.
- Charts use CSS and server-rendered accessible counts; no external chart service or JavaScript dependency is needed.

No email notification integration is configured. Administrators must communicate approval decisions to applicants through their existing process.

Verification: `python manage.py check`, `python manage.py makemigrations --check --dry-run`, and `python manage.py test --noinput`.
