from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from .forms import LoginForm, EmployeeCreateForm, EmployeeEditForm
from .models import User, CounsellorHistory
from .permissions import EmployeeManagementMixin, can_edit_employee, can_manage_employees
from .counsellor_permissions import visible_counsellors, can_edit_counsellor, counsellor_teams
from .counsellor_queries import counsellor_workload


def visible_employees(actor):
    return User.objects.exclude(role=User.Role.PARTNER) if can_manage_employees(actor) else visible_counsellors(actor)


def can_edit(actor, employee):
    return can_edit_counsellor(actor, employee) if employee.role == User.Role.COUNSELLOR else can_edit_employee(actor, employee)


class EmployeeSaveMixin:
    def get_success_url(self):
        return reverse_lazy("accounts:employee-detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
            return self.form_invalid(form)
        except IntegrityError:
            form.add_error(None, "Email, username or employee ID is already in use.")
            return self.form_invalid(form)
        messages.success(self.request, "Employee saved successfully.")
        return response


class WebLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        if self.request.user.role == User.Role.PARTNER:
            return reverse_lazy("partner-portal:dashboard")
        return super().get_success_url()


class EmployeeListView(EmployeeManagementMixin, ListView):
    model = User
    template_name = "accounts/employee_list.html"
    context_object_name = "employees"
    paginate_by = 20

    def get_queryset(self):
        queryset = visible_employees(self.request.user).prefetch_related("crm_teams")
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(email__icontains=query) | Q(username__icontains=query) | Q(employee_id__icontains=query) | Q(phone__icontains=query))
        for field, parameter in (("role", "role"), ("account_status", "status")):
            if self.request.GET.get(parameter):
                queryset = queryset.filter(**{field: self.request.GET[parameter]})
        team = self.request.GET.get("team")
        if team:
            queryset = queryset.filter(crm_teams__pk=team) if team.isdecimal() else queryset.none()
        return queryset.distinct()

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        query = self.request.GET.copy()
        query.pop("page", None)
        data.update(query=query.urlencode(), teams=counsellor_teams(self.request.user), status_choices=User.Status.choices,
            role_choices=[choice for choice in User.Role.choices if choice[0] != User.Role.PARTNER] if can_manage_employees(self.request.user) else [(User.Role.COUNSELLOR, "Counsellor")])
        return data


class EmployeeDetailView(EmployeeManagementMixin, DetailView):
    model = User
    template_name = "accounts/employee_detail.html"
    context_object_name = "employee"

    def get_queryset(self):
        return visible_employees(self.request.user)

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["can_edit"] = can_edit(self.request.user, self.object)
        data["can_delete"] = can_manage_employees(self.request.user) and can_edit_employee(self.request.user, self.object) and self.object.pk != self.request.user.pk
        if self.object.role == User.Role.COUNSELLOR:
            workload = counsellor_workload(self.request.user, self.object)
            data.update(workload)
            data.update(counsellor=self.object, can_reset_password=can_manage_employees(self.request.user) and data["can_edit"],
                management_history=self.object.counsellor_history.select_related("actor")[:30],
                lead_page=Paginator(workload["work_leads"], 10).get_page(self.request.GET.get("leads_page")),
                application_page=Paginator(workload["work_applications"].select_related("lead", "course"), 10).get_page(self.request.GET.get("applications_page")),
                followup_page=Paginator(workload["work_followups"].select_related("lead"), 10).get_page(self.request.GET.get("followups_page")))
        return data


class EmployeeCreateView(EmployeeManagementMixin, EmployeeSaveMixin, CreateView):
    model = User
    form_class = EmployeeCreateForm
    template_name = "accounts/employee_form.html"
    success_url = reverse_lazy("accounts:employee-list")

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "actor": self.request.user}

class EmployeeEditView(EmployeeManagementMixin, EmployeeSaveMixin, UpdateView):
    model = User
    form_class = EmployeeEditForm
    template_name = "accounts/employee_form.html"
    success_url = reverse_lazy("accounts:employee-list")

    def get_object(self, queryset=None):
        employee = get_object_or_404(visible_employees(self.request.user), pk=self.kwargs["pk"])
        if not can_edit(self.request.user, employee):
            raise PermissionDenied
        return employee

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "actor": self.request.user}

class EmployeeStatusView(EmployeeManagementMixin, View):
    @transaction.atomic
    def post(self, request, pk):
        employee = get_object_or_404(User.objects.select_for_update().filter(pk__in=visible_employees(request.user).values("pk")), pk=pk)
        if employee.pk == request.user.pk or not can_edit(request.user, employee):
            raise PermissionDenied
        action = request.POST.get("action")
        if action not in ("activate", "deactivate", "block"):
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest("Invalid status action")
        previous_status = employee.account_status
        employee.account_status = {"activate": "ACTIVE", "deactivate": "INACTIVE", "block": "BLOCKED"}[action]
        employee.save(update_fields=["account_status"])
        if employee.role == User.Role.COUNSELLOR and employee.account_status != previous_status:
            CounsellorHistory.objects.create(counsellor=employee, actor=request.user, action="UPDATED",
                changes={"account_status": {"before": previous_status, "after": employee.account_status}})
        messages.success(request, "Employee status updated.")
        return redirect("accounts:employee-detail", pk=pk)


class EmployeeDeleteView(EmployeeManagementMixin, View):
    def target(self, request, pk):
        employee = get_object_or_404(User.objects.exclude(role="PARTNER"), pk=pk)
        if employee.pk == request.user.pk or not can_edit_employee(request.user, employee):
            raise PermissionDenied
        return employee

    def get(self, request, pk):
        employee = self.target(request, pk)
        return render(request, "accounts/delete_confirm.html", {"object_name": employee.name,
            "kind": "employee", "cancel_url": reverse_lazy("accounts:employee-detail", args=[pk])})

    def post(self, request, pk):
        from django.db.models.deletion import ProtectedError
        self.target(request, pk)
        try:
            with transaction.atomic():
                employee = User.objects.select_for_update().get(pk=pk)
                if employee.pk == request.user.pk or not can_edit_employee(request.user, employee):
                    raise PermissionDenied
                employee.delete()
        except ProtectedError:
            messages.error(request, "This employee has linked CRM records or audit history and cannot be deleted. Deactivate the account instead.")
            return redirect("accounts:employee-detail", pk=pk)
        messages.success(request, "Employee deleted.")
        return redirect("accounts:employee-list")
