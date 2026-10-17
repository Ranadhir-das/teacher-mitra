# TeacherMitra deployment runbook

**Preparation only. No commands in this document have been run on the VPS.** Deploy only after review and explicit release approval. No production secret is supplied by this repository.

## Selected architecture and variables

One Linux VPS: Nginx terminates TLS and serves static/profile files, Gunicorn serves Django WSGI on `127.0.0.1:8001`, PostgreSQL is local/private, and systemd supervises Gunicorn. No asynchronous business requirement was found. This avoids adding Docker/Redis/ASGI infrastructure without evidence it is needed. Capacity is unknown; start at two workers/two threads only after memory checks and measure before increasing.

Templates assume these deployment variables. Substitute **all** affected templates consistently if changed:

| Variable | Template value |
|---|---|
| domains | teachermitra.com, www.teachermitra.com |
| public IP (DNS target only) | 31.97.235.2 |
| service user/group | teachermitra / teachermitra |
| Nginx user | www-data (verify on chosen distribution) |
| release root | /srv/teachermitra/releases/RELEASE_ID |
| current link | /srv/teachermitra/current |
| environment | /etc/teachermitra/teachermitra.env |
| persistent state | /var/lib/teachermitra/{static,media,private_documents,cache} |
| snapshots | /var/backups/teachermitra (root only) |
| certificate challenge root | /var/lib/letsencrypt |
| PostgreSQL | private 127.0.0.1:5432; operator chooses DB/user/password |

Application releases should be immutable, service-writable state separate, and deploy ownership separate from the service account where practical. Nginx must be able to read static/profile images, but **must not** have access to private documents or cache. Parent directories must not be world writable. File-based cache contents are trusted application state; never serve them as media/static.

## Required environment checks (later, on the approved VPS)

Check `/etc/os-release`, `uname -m`, `nproc`, `free -h`, `df -h`, `df -i`, `timedatectl`, listening ports (`ss -lntp`), systemd availability/version, PostgreSQL version, Nginx version, Python 3.14 availability and firewall rules. Inventory existing applications before selecting ports or altering default Nginx sites. Do not assume root login, Ubuntu, Docker, an empty host, or sufficient RAM. If systemd/Linux is unavailable, stop and adapt the reviewed architecture first.

Keep PostgreSQL and Gunicorn bound to loopback. Permit 80/443 for web traffic and restrict administrative SSH appropriately without locking out the operator. Never open 5432 or 8001 publicly. A CDN is not assumed: adding one requires a new trusted-IP/proxy-header design.

## Environment and secrets

Review `deploy/production.env.example`, copy to the private target path with mode 0640 root:teachermitra (or stricter if commands are executed under root). Required keys are SECRET_KEY, DATABASE_URL, all four writable directory paths and DJANGO_SETTINGS_MODULE=config.production. Production does not load the checkout `.env`; systemd loads the private file into the process. `DEBUG=False` is enforced even if an inherited environment sets it true.

During the approved provisioning phase, generate a fresh secret **on the target into the private file**, not into chat, shell history or Git. Example within a root-only provisioning session after creating the file:

```bash
umask 077
python3 - <<'PY'
import secrets
from pathlib import Path
path = Path('/etc/teachermitra/teachermitra.env')
text = path.read_text()
assert text.count('\nSECRET_KEY=\n') == 1, 'Expected exactly one empty key; do not overwrite an existing key'
path.write_text(text.replace('\nSECRET_KEY=\n', '\nSECRET_KEY=' + secrets.token_urlsafe(64) + '\n'))
PY
```

Do not run `cat` on the completed file or print `diffsettings`. Fill DATABASE_URL with the independently provisioned DB credentials; URL-encode the password. Use a non-superuser PostgreSQL role owning only this application database/schema, no CREATEDB/CREATEROLE in production. CI uses a disposable test-only role that may create test databases. For a remote DB, require verified TLS (`sslmode=verify-full` and a trusted CA); loopback deployment does not expose DB traffic publicly.

Configure SMTP only after choosing a provider; SMTP fields are optional for current admin-managed password recovery. Setting SMTP does not create a self-service reset flow. Admin recovery uses `manage.py changepassword EMAIL` or the existing authorized reset screens. Keep a unique production superadmin and documented operator access; do not reuse local demo accounts or shared/chat passwords. Password changes revoke existing sessions and the configured JWT hash checks reject old tokens. Consider VPN/IP restrictions and a separately reviewed MFA integration.

Production `check --deploy` deliberately reports **security.W005** and **security.W021**: HSTS includeSubDomains and preload remain off until every subdomain has been verified. They are not silenced. The runbook uses `--fail-level ERROR`, and configuration tests reject unexpected check messages beyond these two documented warnings. Do not enable preload merely to remove a warning.

The IP is not in production ALLOWED_HOSTS by default: use hostnames with valid TLS. For loopback diagnostics, send `Host: teachermitra.com` and the trusted proxy header locally; do not add wildcard hosts. CORS is empty unless a separate HTTPS browser client is explicitly approved. Native Android clients use HTTPS bearer-token API access and do not need CORS.

## Future first deployment — only after approval

1. Review this entire runbook and fill deployment variables. Install Python/venv support, PostgreSQL/client tools, Nginx and an ACME client using the verified OS procedure. Create the service user without interactive login. Create versioned release directories and independent persistent directories. Give only the service account write access to app state; grant the actual Nginx user read/traverse access to static and public media via a dedicated group/ACL. Private/cache paths should be 0700 teachermitra; public paths may be 0750 with narrowly granted Nginx read access. Ensure the service can read its environment. Do not change existing user data ownership recursively without reviewing the target.
2. Check out the reviewed immutable Git release into a **new** directory. Build that release's own `.venv` using the validated Python 3.14 interpreter:

   ```bash
   python3.14 -m venv .venv
   .venv/bin/python -m pip install -r requirements-production.txt
   .venv/bin/python -m pip check
   ```

3. Provision PostgreSQL database/role interactively; load the private environment without printing it. Templates use systemd EnvironmentFile syntax. For CLI commands, an operator can start a restricted session as the service user and load a reviewed **shell-compatible** version of that environment (`set -a; . /etc/teachermitra/teachermitra.env; set +a`); shell-quote values that need it and never `eval` untrusted files. Use token_urlsafe secrets and URL-encoded DB passwords to avoid quoting ambiguity. Do not run test suites on the production database. Run `bash deploy/scripts/preflight.sh` in the new release. This only checks configuration and prints the migration plan.
4. If existing local SQLite data must be preserved, **stop here until data migration has been rehearsed**. Copying SQLite into PostgreSQL or running migrate does not transfer business data. Use a separately reviewed export/import procedure preserving custom users/password hashes, FK relationships, content types/permissions, audit histories and document paths. Reconcile all model counts and sequences on an isolated database and exercise every role. Do not seed synthetic demo data in production.
5. Ensure a consistent database + upload backup and tested restore point. For an empty first installation, record that no prior data exists; for an existing deployment stop all writers first. Confirm university country mapping requirements using `map_university_countries --list` and the existing mapping command before attempting the enforcing migration. Review partner 0003's pending registration conversion and intended login behavior.
6. In the approved maintenance window, as the service user with the reviewed environment, run in the new release:

   ```bash
   .venv/bin/python manage.py migrate --plan
   .venv/bin/python manage.py migrate --noinput
   .venv/bin/python manage.py migrate --check
   .venv/bin/python manage.py collectstatic --noinput
   .venv/bin/python manage.py check --deploy --fail-level ERROR
   .venv/bin/python manage.py createsuperuser
   ```

   `createsuperuser` is first deployment only and interactive; never put the password in a command, fixture or environment committed to Git. No automatic migration is placed in systemd startup. Stop and restore the maintenance state if a migration fails; do not bypass guards or fake migrations.
7. Review Hostinger DNS records for both domains and the approved public IP. Check both A and AAAA externally; stale IPv6 can break validation. **DNS changes are a separate approved operation.** Install only `http-bootstrap.conf` initially, checking for default-site conflicts. It serves ACME challenges and returns 503 for application paths; it does not redirect HTTP or expose login. Run `nginx -t` before reload.
8. Obtain a certificate covering both hostnames through the chosen ACME client, e.g. `certbot certonly --webroot -w /var/lib/letsencrypt -d teachermitra.com -d www.teachermitra.com` once DNS/firewall are correct. Do not activate the TLS template before certificate files exist. Validate certificate renewal (`certbot renew --dry-run`) and a renewal deploy hook to test/reload Nginx.
9. Install `teachermitra-proxy.conf` under `/etc/nginx/snippets/`, replace the HTTP bootstrap site with the reviewed TLS `teachermitra.conf`, validate using `nginx -t`, then reload. Static/media aliases must match the environment paths. The templates overwrite X-Forwarded-Proto and X-Forwarded-For, not append untrusted client values. Do not expose the loopback upstream directly. Increase HSTS gradually after HTTPS is reliable; keep the Nginx header and Django value aligned. Do not enable includeSubDomains/preload without auditing all subdomains.
10. Point `/srv/teachermitra/current` to the approved release (record the previous target), install the systemd template, run `systemd-analyze verify` and `daemon-reload`, then enable/start the application only after release approval. Use `systemctl restart teachermitra` for release switches so WorkingDirectory and the release-specific virtualenv are re-resolved; HUP alone is not a release switch.
11. Verify `https://teachermitra.com/health/` and `/health/ready/`, both-domain login, CSRF POST, admin static files, role/lead isolation, onboarding upload/review, private document access, profile images and reporting. Check HTTP redirects only after TLS is active. Test hostile Host/X-Forwarded-* requests, private path 404s, >12 MiB request rejection and repeated-login 429s. Do not log or share bearer tokens. Inspect service logs and resource use.

## Subsequent releases and rollback

Build each new release in its own directory/venv. Review migrations for compatibility and take a verified snapshot before schema/data changes. Stop all writers during incompatible migration/static changes; Nginx may return 502/503 while Gunicorn is down. Apply reviewed migrations explicitly, collect static, switch current, then restart. Record release ID and deployment time. Never run auto-migrations in service restart loops.

For code-only compatible rollback, stop writers, point current back to the recorded previous release, re-collect that release's static assets into the persistent static path, restart and verify health/workflows. Static cache TTL is one hour; browser cache invalidation may need release asset versioning. Do not `collectstatic --clear` as a shortcut or delete uploads. Keep both releases and the matching snapshots.

For incompatible schema/data rollback, do not blindly reverse migrations. Stop writers and restore the **matching database + media/private files** into new isolated locations first, verify, then perform a separately approved cutover. This can lose post-snapshot transactions; obtain explicit approval and reconcile with stakeholders. Backup/recovery is not a substitute for a schema-compatibility plan.

## Backups, retention and restoration test

`deploy/scripts/backup.sh` is an explicit root-only maintenance operation. It refuses to run without `TEACHERMITRA_ALLOW_BACKUP_DOWNTIME=1`, stops the application to align DB/files, and restarts it on exit only if previously active. Stop any other writers/jobs too. It uses a protected PostgreSQL service/passfile rather than credentials in process arguments. It writes custom-format pg_dump + media/private tar archives, a release reference and SHA256 checksums into a root-only timestamp directory. It does not delete existing backups or user data.

Install completed pg_service.conf/pgpass with root-only mode 0600. Use matching/newer pg_dump client for the DB major version and a backup role with the required read access. Archives contain personal data: encrypt and copy off-host using your approved backup system; credentials are backed up separately in the secret manager, not these archives. Monitor exit status, file sizes, off-host copy success and backup age.

Optional systemd backup timer is **disabled until reviewed**. Its proposed 02:30 UTC schedule is 08:00 Asia/Kolkata and causes brief application downtime. Choose/approve a suitable window; do not blindly enable it. Retention proposal: 7 daily, 4 weekly, 12 monthly encrypted off-host snapshots with deletion disabled until reviewed. A storage operator must explicitly approve/implement lifecycle deletion; no pruning script is provided.

Restore rehearsal at least monthly and before initial cutover:

1. Select a verified completed snapshot. Run `sha256sum -c SHA256SUMS`, `pg_restore --list database.dump`, and `tar -tzf uploads.tar.gz`. These checks alone do not prove a usable restore.
2. Create a **new disposable PostgreSQL database** and isolated restore media/private directories, no network exposure. Never use `--clean` against an existing database or extract over live files. Inspect archive paths for unexpected absolute/parent traversal entries before extracting.
3. Restore with `pg_restore --no-owner --no-acl --exit-on-error --dbname=service=teachermitra-restore database.dump`, using a protected restore-specific PostgreSQL service configuration pointing only to the disposable DB. Extract uploads into the isolated root, preserving correct filenames/permissions; compare counts/checksums. Do not print sensitive filenames to shared logs.
4. Start the matching release in isolated staging with a new secret and disabled outbound mail/integrations, point environment paths/DB to the restore targets, run `migrate --check` and readiness. Reconcile users, leads, applications, partners and document rows/file existence. Exercise all role restrictions and approved/private downloads. Record restore duration, recovered snapshot age, results and agreed recovery-point/time objectives.
5. Obtain explicit approval before any live restore/cutover. Retain originals until the restored system is accepted. Never automatically delete failed backup `.partial-*` directories; investigate them safely.

## Monitoring and troubleshooting

- `journalctl -u teachermitra` receives minimal JSON Django events and Gunicorn operational output. Connect ERROR events and external HTTPS readiness failures to an operator alerting system; test delivery before launch. No third-party error service or SMTP error-email handler is enabled automatically, avoiding request/credential leakage. Raw exception messages/bodies/queries are omitted; detailed stack investigation belongs in restricted staging with redacted reproduction.
- Apply the journald size/retention example only after reviewing its host-wide impact. Nginx sanitized access format omits query strings, IPs and cookies; its error logs may contain URLs and must remain restricted. Use either the distro's existing Nginx logrotate rule or the supplied non-overlapping rule, never both. Verify distribution-specific ownership and reload path first.
- 502: inspect service status, environment access, loopback binding and DB connectivity. Redirect loop: verify Nginx overwrites X-Forwarded-Proto and upstream is not externally accessible. 400: verify exact hostname. 403 on POST: check HTTPS CSRF origin, cookies and intended role; never disable CSRF/permissions. 413: 12 MiB Nginx request cap vs 10 MiB per-document limit. 429: shared-IP login limiting; review legitimate traffic before tuning.
- Missing static: check collectstatic, alias paths and Nginx traverse/read permissions. Missing private file: check protected storage path and owner, not a public alias. Readiness 503: check DB privately; public response intentionally hides details. Migration failure: inspect plan and guarded country mappings; do not fake it.
- Periodically run existing `clearsessions` and SimpleJWT `flushexpiredtokens` management commands in an operator-approved scheduled job to bound table growth. Review disk, PostgreSQL autovacuum, logs, backups and cache size. No new scheduler has been added to the app.

## Local Windows development and CI

The local `.env`/SQLite/media remain unchanged. Run `./run-local.ps1` or set `$env:DEBUG='True'` and use `.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000`. Production requirements add Linux Gunicorn without changing the development dependency list. Run `check`, `makemigrations --check --dry-run` and `test --noinput` locally. Upload tests can require normal Windows temp permissions outside a restricted tool sandbox.

CI runs SQLite and disposable PostgreSQL tests, production checks with ephemeral non-production secrets, collectstatic and Gunicorn/shell configuration checks. It never uses production credentials or connects to the VPS. A dependency advisory failure must be resolved/reviewed, not ignored. Host-level Nginx/TLS/systemd checks and real storage restore still require the approved target/staging environment.

## Git review and release commands (operator only)

This checkout has no commits yet and substantial existing staged/untracked work. Review application changes as well as deployment files. First inspect without printing private .env/upload content:

```powershell
git status --short
git diff --stat
git diff
git diff --cached --stat
git diff --cached
git add --dry-run .
```

Only after all required files and secret checks have been reviewed:

```powershell
git add .
git diff --cached --check
git diff --cached --stat
git diff --cached
git commit -m "Prepare TeacherMitra CRM for production deployment"
git remote -v
git push -u origin HEAD
```

If `origin` is not configured, obtain the intended repository URL first; no remote is invented here. Do not commit a working tree with unresolved failures, real environment files or unreviewed existing changes. No Git mutation was performed by this preparation task.
