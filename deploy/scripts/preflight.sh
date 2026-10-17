#!/usr/bin/env bash
# Read-only checks. Environment must already be loaded securely.
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${DJANGO_SETTINGS_MODULE:?Load the production environment first}"
if [[ "$DJANGO_SETTINGS_MODULE" != config.production ]]; then
    echo 'Expected config.production' >&2
    exit 1
fi
.venv/bin/python manage.py check --deploy --fail-level ERROR
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py migrate --plan
.venv/bin/python -m pip check
# Deliberately does not migrate, collect static files, or start services.
