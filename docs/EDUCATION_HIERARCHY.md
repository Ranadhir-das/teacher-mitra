# Country -> University -> Course

The existing universities and courses apps are the single education catalogue. Countries live in `apps.universities`; University has a required, protected Country FK; Course retains its protected University FK and existing fields. Country is derived through University for courses, applications and admissions. There are no city/state/region fields in the education catalogue. Lead and partner contact-address fields are unrelated and retained.

## Permissions and pages

- `/countries/`, `/universities/`, `/courses/`: active internal users can browse. Existing Admin/Super Admin permission checks control create, edit, activate and deactivate.
- Django admin registers all three masters; destructive deletion remains disabled.
- Counsellors and team leaders retain their existing lead/application access boundaries.
- Active approved partners can only read active choices and select them on their own submissions. No master-data write access is granted.

## Selection behavior

Lead and partner forms share `selected_country`, `selected_university`, `selected_course`. Existing free-text preferences remain available. Country may be selected before a university/course is known. University/course choices cascade in both CRM and Django admin and are restricted again on the server.

Country changes clear university and course in the browser; university changes clear course. Backend model and serializer validation rejects mismatches and newly selected inactive parents, inactive courses, or closed intakes. Existing unchanged selections may be retained when an offering is deactivated. Changing any part of a selection validates the full chain again.

For backwards compatibility, an older client sending only university/course gets its country derived from the university; explicit mismatched country IDs are rejected. Applications use a non-model Country form control and keep only their existing University/Course FKs. Application and admission workflows, history, lead synchronization and restrictions remain intact.

## APIs

Existing JWT authentication is used for master APIs. All list endpoints use the configured DRF page-number pagination (`count`, `next`, `previous`, `results`).

| Resource | Management endpoint | Filters |
| --- | --- | --- |
| Country | `/api/v1/countries/` | `search`, `is_active=true/false` |
| University | `/api/v1/universities/` | `country`, `search`, `is_active` |
| Course | `/api/v1/courses/` | `country`, `university`, `mode`, `intake_status`, `search`, `is_active` |

Management supports list/retrieve, POST create, PUT/PATCH update, and POST `<id>/activate/` or `<id>/deactivate/`. DELETE is not offered. Only authorized internal administrators may write. University responses include `country` and `country_name`; Course responses include `university`, `university_name`, derived `country` and `country_name`.

Shared choices (GET only; JWT or session authentication, active internal users or approved partners):

- `/api/v1/education/countries/`
- `/api/v1/education/countries/<id>/universities/`
- `/api/v1/education/universities/<id>/courses/`

Inactive ancestors hide their descendants; course choices exclude closed intakes. IDs remain the normal numeric primary keys. Use `selected_country`, `selected_university`, `selected_course` with the existing internal lead and partner lead APIs. Invalid combinations return field-specific HTTP 400 responses. The partner boundary middleware only permits the new read-only education routes, not master management.

## Migration and existing data

Four migrations are added:

1. `universities.0002_country`: creates the Country master without guessed seed data.
2. `universities.0003_remove_university_university_name_ci_unique_and_more`: adds a temporarily nullable Country FK, scopes university-name uniqueness to country (case-insensitive), preserves nonempty legacy city/state as unstructured description text, then removes those columns.
3. `universities.0004_require_university_country`: lists unmapped universities and stops with an actionable error if any are missing a country; otherwise enforces NOT NULL.
4. `leads.0004_lead_selected_country`: adds the optional preferred-country FK and backfills it from already-selected universities.

For an existing populated deployment, back up the database and use a maintenance window. Run `python manage.py migrate`; if it stops at the country guard:

- Run `python manage.py map_university_countries --list` to see IDs/names.
- Create the administrator-confirmed Country records via Django admin or `manage.py shell` (call `full_clean()` then `save()`); no guessed or placeholder country is created.
- Map each existing university explicitly with `python manage.py map_university_countries --university ID --country ID`.
- Run `python manage.py migrate` again to enforce the constraint and backfill lead countries.

Mapping is only permitted for unmapped universities and active countries. Existing University/Course primary keys and all application/admission relationships are preserved. Once transactions reference a university, changing its established country is prohibited. Existing unstructured location text is retained for reference but is not a new hierarchy.

The local database had zero universities/courses at inspection. All four migrations were applied successfully, with a SQLite backup in the OS temporary directory. No local records require manual mapping. Add real Country -> University -> Course entries through the existing CRM/admin screens.

## Verification and related fixes

Tests cover case-insensitive country/within-country university uniqueness, optional codes, CRUD, permissions, filters, pagination, dependent forms, valid and invalid partner submissions, inactive entities, application retention, migration guard/data preservation/mapping, and Django admin rendering. Existing test fixtures now supply the required country, retaining their original workflow assertions.

The complete suite exposed two pre-existing issues: the partner report had lost its empty-state message, and the follow-up `mark_missed` action was nested inside `complete`, leaving its route unregistered. The empty-state message and correct method indentation were restored rather than changing the tests.

Run `python manage.py check`, `python manage.py makemigrations --check --dry-run`, `python manage.py test --noinput`, and `node --check static/js/education.js`.
