# TeacherMitra production readiness audit

Audit date: 2026-10-16. Preparation only; no VPS connection, DNS operation, live migration, production account change, commit or push.

## Scope and baseline (before editing)

The available checkout is `E:\react\aspiring life partners`, with `manage.py` at its root. The IDE's `aspiring-crm/`, `caller-app/` and `test_counselor_login.py` paths are absent. Confirm this checkout is the intended complete release before deploying; the Android app and its production environment are outside this audit.

- Python 3.14.4; Django 5.2.17. Direct requirements: DRF 3.16.1, SimpleJWT 5.5.1, django-environ 0.13.0, django-cors-headers 4.9.0, Pillow 12.3.0, psycopg 3.3.6. Installed dependency consistency passed.
- Django templates + Bootstrap, ordinary synchronous WSGI, REST JWT API, custom email/username User, teams and role permissions. ASGI entry point exists but no Channels, WebSocket consumer or async requirement was found.
- Apps: accounts, dashboard, leads, partners, followups, calls, universities, courses, applications, documents, commissions, reports, notifications. No rebuild or domain-wide UI rebranding is included.
- Settings read untracked local `.env`, require SECRET_KEY, default to SQLite when DATABASE_URL is absent, and accept environment overrides. DEBUG defaults false. Local helper explicitly sets DEBUG true. Existing production cookie and redirect settings already followed DEBUG.
- Baseline checks and migration consistency passed; all local migrations were applied. **238 tests passed** against an isolated temporary test database. Existing local business data was not migrated or altered by this audit.
- Static collection path, media and private storage were tied to the checkout. No production-specific settings, proxy configuration, persistent paths, structured logging, health endpoints, CI, Gunicorn, Docker or systemd configuration existed.
- CORS allowlist default empty, CSRF middleware enabled, session cookies HTTP-only, framing denied, nosniff enabled. JWT access 5 minutes; refresh rotation, blacklist and password-change revocation configured. API login/refresh/signup scoped throttles existed; general API and browser login rate limiting were absent.
- Admin user management is superuser-only; internal permissions are role checked. Counsellors see assigned leads. Team leaders can review partner submissions but mutation uses separate manageable-lead scope. Partner full features use current_partner(ACTIVE); onboarding uses a separate limited-access permission. Middleware also separates session users from the internal CRM.
- Documents are separate private FileFields, not public media. Random filenames; PDF/PNG/JPEG validation by bytes and size (10 MiB); owner/application consistency and PROTECT constraints; downloads scope by accessible application or partner ownership and use no-store/nosniff. PDFs use header/trailer validation, not malware scanning or full PDF sanitization. Do not treat uploaded PDFs as trusted content. The Nginx body cap supplements per-file validation.
- Public media currently contains employee profile images only; Django ImageField validation and employee form size cap are in place. Confirm no student data was manually placed under public media before launch. Profile images are public-by-URL by current product design; moving them behind authentication would be a separate product decision.
- ORM parameterization was used in the reviewed code; no raw dynamic SQL, csrf_exempt application endpoints or shell-executed user input were found. The new readiness SQL is constant `SELECT 1`.
- Existing generic 403/404/500 templates are present. No self-service email password-recovery flow is implemented. Counsellor resets require an administrator, validate passwords, record history and revoke tokens; other account recovery uses Django admin/management commands. Never reuse the temporary local superadmin password previously shared in chat for production.

## Git and secrets

This Git repository currently has **no commits**, a populated staging index, many modified staged files, and many untracked application modules/migrations/templates. A staged-only release would omit existing features. Review the full working tree and stage all required application files intentionally before the first release.

The initial tracked sensitive-name check found only `.env.example`; local `.env`, database, upload files and database backup were not tracked. No literal live credentials were identified in the reviewed source. Known test-only passwords are fixtures and are not production credentials. This is an advisory scan, not proof that arbitrary secrets cannot exist. No Git history can be audited because there are no commits. Private remote-host history and absent sibling projects remain unverified.

Never paste `.env`, `git show` of a suspected secret, token dumps, or full production settings into tickets/logs. If any credential is found in an index or prior remote history, rotate/revoke it first, stop publication, and coordinate an explicit history-cleaning plan. No unstage/reset/history rewriting was performed here.

## Production blockers requiring operator verification

1. VPS OS, systemd, CPU, RAM, disk/inodes, time sync, firewall, existing services/ports, Python and PostgreSQL versions are unknown. No VPS connection was attempted. Templates target a single Linux/systemd host, not an assumed installed platform.
2. Confirm this root checkout is the intended release and includes all current CRM work. Review the pre-existing uncommitted changes independently.
3. Provision database/service users, persistent directories, private environment file and a new independently generated secret only during the approved release phase.
4. Decide whether existing SQLite business data must move to PostgreSQL. `migrate` creates schema, not data transfer. Rehearse transfer and reconcile row counts, relationships, sequences, files, credentials and audit histories on a disposable PostgreSQL database before approving cutover.
5. The universities country-mapping migration deliberately stops if legacy rows lack mappings; run the existing mapping command during rehearsal, never guess countries. Pending-partner migration changes old self-registration login state; review its behavior before live migration.
6. Verify DNS A/AAAA records for both domains, certificate issuance and renewal, then enable the HTTPS config. No HTTP application login is exposed by the bootstrap config. The raw VPS IP is intentionally not an authenticated production hostname.
7. Restore-tested off-host encrypted backups, monitoring/alerts, SMTP decisions and admin recovery procedures must be owned by an operator. MFA is not currently implemented; restrict `/admin/` using a VPN/IP policy if required by your risk assessment. Do not rely on changing its URL as protection.
8. File-based API throttling shares cache across workers on this single host but has normal DRF race limitations; Nginx is the stronger IP admission layer. A multi-node deployment would require a shared cache and reviewed proxy topology. Fail2ban/CDN policies and malware scanning remain optional operational additions.

## Prepared changes

`config/production.py` provides fail-closed PostgreSQL/secret/storage validation, HTTPS security, explicit CORS/CSRF, short sessions, shared file cache, API throttles and JSON-only API rendering. Production ignores the checkout `.env` and requires process environment. Development still uses `config.settings` and the original local database.

`deploy/` contains the chosen Gunicorn/systemd/Nginx architecture, staged certificate bootstrap, loopback upstream, header overwrite, request-size/rate limits, persistent storage paths, controlled logs, backup script and optional timer. It is a set of reviewable templates, not an executed installation. All account and document ownership permissions remain in the existing application.

Health endpoints expose only status. Readiness checks database connectivity without disclosing versions, credentials, exception messages, migration names or user data. Error logs are structured and deliberately omit request bodies, queries and raw exception messages; restricted staging reproduction is required for detailed debugging. Journal ERROR events can feed operator alerting without adding a telemetry vendor dependency.

See [DEPLOYMENT.md](DEPLOYMENT.md) for the separate future release procedure and [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) for sign-off. Verification results are recorded after implementation in the final report.

References: [Django 5.2 deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/), [Django proxy header settings](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header), [Gunicorn deployment](https://gunicorn.org/deploy/).
