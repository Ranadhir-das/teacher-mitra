# Partner-to-counsellor workflow

1. An approved partner submits a student through `/partner/leads/create/`. The existing submission service fixes ownership to the current partner, source to PARTNER, and status to NEW. Hidden ownership/status fields are rejected.
2. Admins and team leaders can review partner submissions in the existing Leads list (filter Source = Partner). Review notes use the existing Add note action and appear in the Activity Timeline.
3. Admins assign a counsellor and/or team using Assign. A counsellor assignment changes NEW to ASSIGNED and records both assignment and status history. Team-only routing remains NEW until a counsellor is selected.
4. Team leaders can read all partner submissions, but can modify only leads routed to their own active teams. Counsellors only access leads currently assigned to them.
5. Counsellors use Change status, Add note and Schedule Follow-up on the existing detail page. Status transitions retain the existing workflow. Follow-up lists and actions follow current lead access; reassignment revokes the previous counsellor's access.
6. The timeline includes submission/status history, assignments, notes, follow-up creation and its current completion/cancellation/missed event. Partner logs remain limited to safe submission/status history.

No new models, migrations or separate review entity were introduced. Review is recorded through notes and assignment reasons, not a mandatory approval state for leads. Partner account approval remains separate.

Follow-up service callers must pass `actor` when completing, cancelling or marking a follow-up missed. These operations recheck permissions and lock the lead and follow-up; archived leads are read-only.

The existing FollowUp model holds current state, not a full immutable event ledger of every intermediate edit or missed/rescheduled state. A scheduled entry remains visible after completion; reconstructing older overwritten follow-up states is outside this change.
