# Preparation verification and change manifest

2026-10-16, Windows development checkout. **No production deployment was performed.**

## Checks executed

| Check | Result |
|---|---|
| Baseline Python/Django | Python 3.14.4, Django 5.2.17 |
| Baseline system/migration consistency | Passed; existing local migrations applied, no missing model migrations |
| Baseline suite | 238 tests passed |
| Final full suite after DRF upgrade | **247 tests passed** |
| Final production-specific suite | 9 tests passed, including unexpected deployment-warning guard |
| Final Django system check | Passed, no issues |
| Final makemigrations --check --dry-run | No changes detected; no migrations created |
| pip check | No broken requirements |
| Initial pip-audit 2.10.1 | DRF 3.16.1 flagged PYSEC-2026-3827 and PYSEC-2026-3828; fixed versions include 3.17.2 |
| Re-audit resolved Windows requirements | No known vulnerabilities found after upgrading DRF to 3.17.2 |
| Separate Linux-only Gunicorn 26.2.0 direct-package audit | No known vulnerabilities found; transitive Linux resolution remains covered by CI |
| Production check --deploy | No errors; intentional W005/W021 warnings remain visible (HSTS subdomains/preload disabled pending audit) |
| Production static collection | Passed into temporary external directory |
| Production anonymous login + liveness | HTTP 200 + 200 using Django test client, trusted HTTPS header and allowed host |
| Production generic 500 template | HTTP 500 rendered without traceback |
| Storage/proxy/secret guards | Tests reject weak/missing secret, SQLite, wildcard hosts, insecure origins and overlapping/private-in-release paths |
| Readiness DB failure behavior | 503 with generic status; secret-bearing exception text not exposed |
| Logging | Test confirms raw messages, exception details and interpolated tokens are omitted |
| Python configuration syntax | Parsed successfully, Gunicorn config loopback/header assertions passed |
| Targeted source and staging-index credential pattern scans | No findings; no values printed; fixture passwords excluded |
| Tracked sensitive filenames | No environment secrets, DBs, keys, logs or backups found tracked |
| Whitespace check for files modified by this task | Passed (Git printed Windows line-ending notices) |
| Whole existing working-tree whitespace check | Pre-existing whitespace findings in apps/dashboard/views.py, static/js/app.js and templates/accounts/employee_detail.html; left unchanged |

Audits are point-in-time and pattern based, not a guarantee of absence of vulnerabilities or secrets. Installed dependencies were updated locally only for the DRF fix. `pip-audit` was installed separately in ignored `.audit-venv`; its scratch input is under ignored `.audit-tools`. Existing business database, uploads, .env and backups were not modified. Tests used temporary databases/storage.

## Checks not executed

- PostgreSQL integration and real SQLite-to-PostgreSQL data transfer: no local PostgreSQL/Docker executable or verified target DB. CI contains a disposable PostgreSQL job; it has not run on the remote repository yet.
- Nginx `-t`, systemd verification, Gunicorn runtime check, Bash syntax/shellcheck and logrotate syntax: required native tools are absent on this Windows host. Python syntax of Gunicorn configuration was checked. Gunicorn runtime and Bash checks are configured in Linux CI; Nginx/systemd/logrotate must be validated in approved Linux staging/target context.
- VPS capacity/OS/firewall/service ownership, DNS, real TLS and renewal, real SMTP, production accounts, production migration/cutover and backup/restore exercise: intentionally untouched under the preparation-only boundary.
- No self-service reset/MFA feature added; existing administrator-controlled password management remains. Detailed external alert delivery needs an operator-selected monitoring destination. Malware scanning is not part of the current document validator.
- Git history scan: repository has no commits; remote/private history is unknown. No commit/push/stage/reset/rebase was performed.

## Files modified by this task

- `.env.example`, `.gitignore`, `README.md`, `requirements.txt` (DRF 3.17.2).
- `config/settings.py`: controlled local env loading, configurable persistent paths and same-site/referrer settings.
- `config/urls.py`, `config/views.py`: safe liveness/readiness routes.
- `apps/accounts/middleware.py`: health routes permitted across session boundary.
- `apps/partners/onboarding_views.py`: sandbox CSP added to private attachment response.

## Files created by this task

- `.gitattributes`, `.github/workflows/django.yml`, `requirements-production.txt`.
- `config/production.py`, `config/logging.py`, `config/test_production.py`.
- `deploy/production.env.example`, `deploy/gunicorn.conf.py`.
- `deploy/nginx/http-bootstrap.conf`, `deploy/nginx/teachermitra.conf`, `deploy/nginx/teachermitra-proxy.conf`.
- `deploy/systemd/teachermitra.service`, `deploy/systemd/teachermitra-backup.service`, `deploy/systemd/teachermitra-backup.timer`.
- `deploy/scripts/preflight.sh`, `deploy/scripts/backup.sh`.
- `deploy/pg_service.conf.example`, `deploy/pgpass.example`, `deploy/journald.conf.example`, `deploy/logrotate.conf`.
- `docs/PRODUCTION_AUDIT.md`, `docs/DEPLOYMENT.md`, `docs/DEPLOYMENT_CHECKLIST.md`, this verification report.

Other modified/staged/untracked files predate this preparation task. Review them separately; many existing CRM modules and migrations are untracked and required for a complete release. Confirm the intended source checkout because the IDE-referenced sibling projects are absent here.
