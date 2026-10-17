from dataclasses import dataclass
from typing import Any


@dataclass
class ActivityItem:
    kind: str
    timestamp: Any
    title: str
    description: str = ""
    actor: str = ""
    icon: str = "•"
    object_id: int | None = None


def build_lead_activity(
    *,
    lead,
    notes,
    status_history,
    assignment_history,
    followups,
):
    activities = []

    # Notes
    for note in notes:
        activities.append(
            ActivityItem(
                kind="NOTE",
                timestamp=note.created_at,
                title="Note added",
                description=note.note,
                actor=note.created_by.name,
                icon="📝",
                object_id=note.pk,
            )
        )

    # Status changes
    for event in status_history:
        previous = (
            event.get_previous_status_display()
            if event.previous_status
            else "Created"
        )

        activities.append(
            ActivityItem(
                kind="STATUS",
                timestamp=event.changed_at,
                title="Status changed",
                description=(
                    f"{previous} → "
                    f"{event.get_new_status_display()}"
                    + (
                        f" — {event.note}"
                        if event.note
                        else ""
                    )
                ),
                actor=event.changed_by.name,
                icon="🔄",
                object_id=event.pk,
            )
        )

    # Assignments
    for event in assignment_history:
        previous_counsellor = (
            event.previous_counsellor.name
            if event.previous_counsellor
            else "Unassigned"
        )

        new_counsellor = (
            event.new_counsellor.name
            if event.new_counsellor
            else "Unassigned"
        )

        activities.append(
            ActivityItem(
                kind="ASSIGNMENT",
                timestamp=event.assigned_at,
                title="Lead assigned",
                description=(
                    f"{previous_counsellor} → "
                    f"{new_counsellor}"
                    + (
                        f" — {event.reason}"
                        if event.reason
                        else ""
                    )
                ),
                actor=event.assigned_by.name,
                icon="👤",
                object_id=event.pk,
            )
        )

    # Follow-ups
    for followup in followups:
        activities.append(ActivityItem(
            kind="FOLLOWUP", timestamp=followup.created_at,
            title="Follow-up scheduled",
            description=f"{followup.get_followup_type_display()} for {followup.scheduled_at:%d %b %Y, %H:%M}",
            actor=followup.created_by.name, icon="\U0001f4c5", object_id=followup.pk,
        ))
        if followup.status == "SCHEDULED":
            continue
        if followup.status == "COMPLETED":
            title = "Follow-up completed"
        elif followup.status == "CANCELLED":
            title = "Follow-up cancelled"
        elif followup.status == "MISSED":
            title = "Follow-up missed"
        else:
            title = "Follow-up scheduled"

        description = (
            f"{followup.get_followup_type_display()} "
            f"for {followup.scheduled_at:%d %b %Y, %H:%M}"
        )

        if followup.outcome:
            description += f" — {followup.outcome}"

        activities.append(
            ActivityItem(
                kind="FOLLOWUP",
                timestamp=(
                    followup.completed_at
                    or followup.updated_at
                    or followup.scheduled_at
                ),
                title=title,
                description=description,
                actor=followup.assigned_to.name,
                icon="📅",
                object_id=followup.pk,
            )
        )

    return sorted(
        activities,
        key=lambda item: item.timestamp,
        reverse=True,
    )