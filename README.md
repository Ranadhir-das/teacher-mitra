# Aspiring Life Partners

Production preparation for **TeacherMitra / teachermitra.com** is documented in
[the deployment runbook](docs/DEPLOYMENT.md), [readiness audit](docs/PRODUCTION_AUDIT.md),
and [release checklist](docs/DEPLOYMENT_CHECKLIST.md). These are preparation templates;
no production deployment is authorized or performed. Existing product behavior and branding remain intact.

An education consultancy CRM foundation built with Django templates and a versioned REST API. Stages 1 and 2 implement accounts, authentication, employee management, and the Lead/Student CRM. Applications, documents, commissions, follow-ups, calls and the Android/React Native caller app remain deferred.

## Architecture

```text
manage.py
requirements.txt         Direct dependencies, pinned
.env.example             Safe configuration template
run-local.ps1            Windows local server helper
config/                  Settings, web/API URL configuration, router, ASGI/WSGI
apps/
  accounts/              Custom user, Team, forms, permissions, views, admin
    api/                 Serializers, API permissions, views, URLs
    migrations/          Custom-user and Team migrations
    tests.py             Model, web, permission and JWT integration tests
  dashboard/             Scoped lead metrics, status distribution, recent leads and sources
  leads/                 Lead/Tag/audit models, services, workflow, filters, forms
    api/                 Lead serializers, permissions and viewsets
    management/commands/seed_demo.py
    tests.py             Stage 2 web/API, audit, scope and workflow tests
  followups/
  calls/
  universities/
  courses/
  applications/
  documents/
  commissions/
  reports/
  notifications/
templates/               Shared shell, reusable cards, accounts and error pages
static/                  Project CSS/JS and vendored Bootstrap 5.3.8
media/                   Local profile-photo uploads (ignored by Git)
```

Apps own their domain behavior. `config` composes their routes. Future viewsets can be registered in `config/routers.py`; API code stays in each app's `api/` package. The Team model defines a leader and counsellor membership. Students are the same Lead records with ADMISSION_CONFIRMED status, shown at /students/. Application/admission transaction models remain deferred.

## Installation

Python 3.14 was used for local verification. Django 5.2.17 is from the 5.2 LTS series, which supports Python 3.14 from 5.2.8 onward: [Django release notes](https://docs.djangoproject.com/en/5.2/releases/5.2/).

From this directory:

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

**macOS / Linux (Bash/Zsh):**
```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

For this delivered workspace, the virtual environment, dependencies, private `.env`, and migrated SQLite database already exist. Do not overwrite your existing `.env`.

If Windows blocks `ensurepip`, use the installed system pip to finish the environment:

```powershell
python -m pip --python .\.venv\Scripts\python.exe install pip
.\.venv\Scripts\python -m pip install -r requirements.txt
```

Optional activation: `.\.venv\Scripts\Activate.ps1` (Windows) or `source .venv/bin/activate` (macOS/Linux). Commands below use the interpreter directly, so activation is not required. On macOS/Linux use `./.venv/bin/python` or `./run-local.sh`.

Generate a secret for a fresh installation and put the result in `.env` as `SECRET_KEY`:

```powershell
.\.venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Never commit `.env`, database files, credentials, or user-uploaded media. This workspace's secret was generated randomly and stored only in the ignored local `.env`. There are no default passwords. Stage 2 synthetic demo accounts have unusable passwords when first created; see Demo data below.

## Environment configuration

| Variable | Purpose/default |
| --- | --- |
| `SECRET_KEY` | Required, no hard-coded fallback |
| `DEBUG` | Defaults to false; `.env.example` enables local development |
| `ALLOWED_HOSTS` | Comma-separated hosts; localhost and 127.0.0.1 by default |
| `DATABASE_URL` | Optional; defaults to project-local SQLite |
| `TIME_ZONE` | Asia/Kolkata |
| `CORS_ALLOWED_ORIGINS` | Explicit browser client origins; empty by default |
| `CSRF_TRUSTED_ORIGINS` | Explicit trusted web origins; empty by default |

Process environment variables take precedence over `.env`. This machine has an inherited `DEBUG=release`, so set `$env:DEBUG='True'` for local commands or use `run-local.ps1`. Do not use that local helper for deployment. With debug disabled, secure session/CSRF cookies and HTTPS redirection are enabled.

Native mobile clients do not require CORS. If a separate browser frontend is introduced, configure only its known origins. Session forms use Django CSRF protection; APIs use bearer tokens, not cookie sessions.

## Database and first account

**Windows (PowerShell):**
```powershell
$env:DEBUG = 'True'
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py createsuperuser
.\.venv\Scripts\python manage.py runserver 127.0.0.1:8000
```

**macOS / Linux (Bash/Zsh):**
```bash
export DEBUG=True
./.venv/bin/python manage.py migrate
./.venv/bin/python manage.py createsuperuser
./run-local.sh
```

Enter your own email, name and password at the superuser prompts. Then visit <http://127.0.0.1:8000/accounts/login/>. Alternatively run `.\run-local.ps1` (Windows) or `./run-local.sh` (macOS/Linux) after creating the superuser.

SQLite is the local default. The User and Team migrations, Lead/Tag/history/note migration, Django authentication/session/admin tables, and JWT blacklist tables have been applied.

For PostgreSQL, create a database and set `DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME` in your environment. The psycopg driver is installed. Run `migrate` against that database and create its first superuser. Switching databases does not copy SQLite data; data migration is a separate operation. PostgreSQL was not available for integration testing in this stage.

## Users and permissions

The custom `accounts.User` uses email for authentication and includes name, phone, profile image, role, active status, join date and last login. Passwords use Django's password hashing and validation. Email is normalized to lowercase, with a case-insensitive database uniqueness constraint. Photos are validated by Pillow-backed form validation and limited to 5 MB in employee forms.

| Role | Workspace access |
| --- | --- |
| `SUPER_ADMIN` | Dashboard and employee management, including super-admin role assignment |
| `ADMIN` | Dashboard; manage counsellors, team leaders and regular admins |
| `TEAM_LEADER` | Dashboard and lead access within permitted active teams |
| `COUNSELLOR` | Dashboard and assigned leads only |

Admins cannot create/modify super-admin accounts or modify staff/superuser accounts. Employee forms never accept Django staff/superuser flags or arbitrary permission grants. Self-deactivation and self-role changes are blocked. Django admin's User management is restricted to Django superusers. `createsuperuser` creates an active Django superuser with the `SUPER_ADMIN` role; assigning that business role alone does not grant Django admin access.

Reusable web and DRF permission helpers use the current database user. Roles are `TextChoices`, so adding one is a deliberate code/migration change plus corresponding policy tests; Django groups and permissions remain available for later finer-grained access.

Employees can be listed, searched, paginated, viewed, created, edited and activated/deactivated. Status changes and logout require POST. An inactive user cannot sign in, use existing sessions, use issued API access tokens or refresh tokens. Password changes can be performed by a superuser through Django admin. Self-service password reset is deferred.

## Web URLs

| URL | Purpose |
| --- | --- |
| `/` | Protected dashboard |
| `/accounts/login/` | Session sign-in |
| `/accounts/logout/` | POST session logout |
| `/accounts/employees/` | Employee directory and search |
| `/accounts/employees/new/` | Create employee |
| `/accounts/employees/<id>/` | Employee profile |
| `/accounts/employees/<id>/edit/` | Edit employee |
| `/accounts/employees/<id>/status/` | POST `action=activate` or `action=deactivate` |
| `/admin/` | Django administration |

The dashboard shows active-account counts for administrators and live lead statistics limited to the viewer's access. Leads and Students are functional navigation entries; future sidebar modules remain labelled Planned. The shell includes responsive navigation, a profile menu, dismissible messages, and custom 403/404/500 templates. Django's technical 404/500 responses are visible when DEBUG is enabled.

## REST API v1

| Method | Endpoint | Authentication/body |
| --- | --- | --- |
| POST | `/api/v1/auth/login/` | JSON `email`, `password`; returns `access`, `refresh` |
| POST | `/api/v1/auth/refresh/` | JSON `refresh`; returns rotated access/refresh pair |
| POST | `/api/v1/auth/logout/` | Bearer access token plus JSON `refresh`; returns 204 |
| GET | `/api/v1/auth/me/` | Bearer access token; read-only current-user profile |

Authenticated requests send `Authorization: Bearer <access>`. Login and refresh are public by necessity and throttled to 10 requests/minute using DRF's configured cache. Other API views default to authenticated-only. `/api/v1/` is the router root, with leads and tags registered.

Access tokens last 5 minutes; refresh tokens last 1 day. Refresh rotation blacklists the previous refresh token. Logout verifies ownership and blacklists the supplied refresh token. Already-issued access tokens remain valid until expiry, unless the account is deactivated or its password changes. The client must discard both tokens on logout. Schedule `python manage.py flushexpiredtokens` daily when deploying. See [Simple JWT blacklist documentation](https://django-rest-framework-simplejwt.readthedocs.io/en/stable/blacklist_app.html).

## Future caller app

A later React Native/Android app will consume this same versioned API over HTTPS, store tokens in platform-secure storage, refresh access tokens and discard them on logout. Calls, follow-up synchronization, device permissions, background execution and offline queues will be separate future-stage work. No Android app, call capture, call models or caller APIs are implemented now.

## Checks and tests

```powershell
$env:DEBUG = 'True'
.\.venv\Scripts\python manage.py check
.\.venv\Scripts\python manage.py makemigrations --check --dry-run
.\.venv\Scripts\python manage.py test
.\.venv\Scripts\python manage.py collectstatic --noinput
.\.venv\Scripts\python -m pip check
```

The test suite retains all 21 Stage 1 authentication/account tests and adds Stage 2 lead model, workflow, scope, web/API and audit tests. See the Stage 2 documentation for coverage. Tests use a disposable database and explicitly disable HTTPS redirects for test-client requests.

Bootstrap CSS/JS and its MIT license are vendored under `static/vendor`, so the interface does not depend on runtime CDN availability. `collectstatic` collects these assets for deployment. Local `runserver` serves static files and profile photos only in debug mode.

## Deployment boundaries

This is a local development foundation, not a completed production deployment. Before deployment configure HTTPS, real hosts/origins, a production WSGI/ASGI server, PostgreSQL, backups, a shared cache/edge login rate limits, static serving and suitable media storage/access rules. Review proxy trust and HSTS for the actual deployment topology. `runserver` is not a production server. Dashboard/API behavior is tested; browser visual QA and PostgreSQL integration remain unverified in this environment.

Stages 1 and 2 are implemented. Applications, reports, notifications, document workflows, commissions, follow-ups, calls and the caller app await subsequent requirements.


## Stage 2: Lead and Student CRM

Detailed routes, payloads, permission rules, demo instructions, workflow and migration notes are in [docs/STAGE2.md](docs/STAGE2.md).

Quick start for this existing workspace:

```powershell
$env:DEBUG = 'True'
.\.venv\Scripts\python manage.py migrate
# Optional for a fresh database; safe to repeat:
.\.venv\Scripts\python manage.py seed_demo
# If you have not yet created your own login:
.\.venv\Scripts\python manage.py createsuperuser
.\run-local.ps1
```

Open `/leads/` for the CRM, `/students/` for admission-confirmed leads, and `/` for the dashboard. The local database has 20 synthetic demo leads. Demo accounts are not login credentials; sign in with your own superuser. A superuser can manage Team leaders/members at `/admin/accounts/team/`.
