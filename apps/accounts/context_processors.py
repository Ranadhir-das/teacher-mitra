from .permissions import can_manage_employees
from .counsellor_permissions import can_manage_counsellors


def navigation(request):
    return {"can_manage_counsellors": can_manage_counsellors(request.user), "can_manage_employees": can_manage_employees(request.user), "planned_modules": [
        "Follow-ups", "Calls",
        "Commissions", "Reports", "Settings",
    ]}
