from apps.leads.models import Lead

PUBLIC_STATUSES = {
    "SUBMITTED": ("Submitted", {"NEW"}),
    "CONTACTING": ("Contacting", {"ASSIGNED", "CONTACTED", "NO_RESPONSE"}),
    "COUNSELLING": ("Counselling", {"INTERESTED", "COUNSELLING", "COURSE_SELECTED"}),
    "APPLICATION": ("Application", {"APPLICATION_STARTED", "APPLICATION_SUBMITTED", "PAYMENT_PENDING"}),
    "ADMISSION": ("Admission confirmed", {"ADMISSION_CONFIRMED"}),
    "CLOSED": ("Closed", {"NOT_INTERESTED", "WRONG_NUMBER", "NOT_ELIGIBLE", "LOST"}),
}


def public_status(lead):
    for code, (label, internal) in PUBLIC_STATUSES.items():
        if lead.status in internal:
            return {"code": code, "label": label}
    return {"code": "SUBMITTED", "label": "Submitted"}
