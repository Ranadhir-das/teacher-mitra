# Universities and courses

Run `python manage.py migrate` before opening the updated application.

Internal navigation now includes Universities (`/universities/`) and Courses (`/courses/`). Admin and Super Admin users create, edit and activate/deactivate entries. Active internal team leaders and counsellors can browse details and search/filter the paginated lists. Partners cannot access the internal catalogue. Django admin also registers both models with role checks and no destructive delete action.

Each course belongs to a university and represents an offering with degree/program, duration in months, total tuition and currency, eligibility, study mode, intake label, intake status and active status. A university can have multiple modes/intakes of the same course. Deactivating a university does not erase or change its courses, but prevents new lead selections from that university.

On an accessible lead, choose Edit lead -> Course requirement -> Selected university / Selected course. The server rejects mismatched universities and courses, inactive new selections and closed intakes. Open and upcoming intakes can be selected. The existing lead PATCH API accepts these two IDs with the same validation. Selection changes add an internal activity note.

Existing free-text university/course preferences are retained and are not automatically matched or overwritten. Existing selections remain visible and do not block later lead progression if an offering is subsequently deactivated or closed. Foreign keys protect catalogue entries referenced by leads. An offering already selected by a lead cannot be moved to another university.

Migrations:
- universities/0001_initial
- courses/0001_initial
- leads/0003_lead_selected_course_lead_selected_university

No separate catalogue REST endpoints, admissions integration, fee-payment calculation, historical fee snapshots or automatic legacy preference matching are included. Fees are informational total tuition; the currency field accepts a three-letter code. Course selection remains optional so existing lead records and status workflows continue working.
