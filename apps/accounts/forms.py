from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm, UserChangeForm
from .models import User, Team
from .permissions import is_super_admin, can_manage_employees
from django.db import transaction
from django.db.models import Q
from .counsellor_permissions import counsellor_teams
from .counsellor_services import FIELDS, save_counsellor

EMPLOYEE_FIELDS = ("name", "email", "phone", "profile_photo", "role", "username", "employee_id", "joining_date", "account_status", "profile_information")


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Email or username", widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}))

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.role == User.Role.PARTNER:
            from apps.partners.models import Partner
            from apps.partners.permissions import LOGIN_STATUSES
            if not Partner.objects.filter(user=user, status__in=LOGIN_STATUSES).exists():
                raise forms.ValidationError("Your partner account is awaiting approval or is inactive.", code="inactive")

    def clean_username(self):
        return self.cleaned_data["username"].lower()


class EmployeeFormMixin:
    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.fields["teams"] = forms.ModelMultipleChoiceField(queryset=counsellor_teams(actor), required=not can_manage_employees(actor))
        self.fields["joining_date"].widget = forms.DateInput(attrs={"type": "date"})
        self.fields["account_status"].required = False
        self.fields["role"].required = False
        if self.instance.pk:
            self.initial["teams"] = self.instance.crm_teams.all()
            if can_manage_employees(actor):
                self.fields["teams"].queryset = Team.objects.filter(Q(is_active=True) | Q(pk__in=self.instance.crm_teams.values("pk")))
        self.fields["role"].choices = [choice for choice in User.Role.choices if choice[0] != User.Role.PARTNER]
        if not is_super_admin(actor):
            self.fields["role"].choices = [choice for choice in self.fields["role"].choices if choice[0] != User.Role.SUPER_ADMIN]
        if self.instance.pk == actor.pk:
            self.fields["role"].disabled = True
            self.fields["account_status"].disabled = True
        if not can_manage_employees(actor):
            self.fields["role"].choices = [(User.Role.COUNSELLOR, "Counsellor")]
            self.fields["role"].initial = User.Role.COUNSELLOR
            self.fields["role"].disabled = True

    def clean_account_status(self):
        return self.cleaned_data.get("account_status") or self.instance.account_status

    def clean_role(self):
        return self.cleaned_data.get("role") or self.instance.role

    def clean(self):
        data = super().clean()
        if data.get("role") == User.Role.COUNSELLOR:
            for field in ("username", "employee_id"):
                if not (data.get(field) or "").strip():
                    self.add_error(field, "This field is required for counsellors.")
        return data

    @transaction.atomic
    def save(self, commit=True):
        if self.cleaned_data["role"] == User.Role.COUNSELLOR and commit and (not self.instance.pk or User.objects.filter(pk=self.instance.pk, role=User.Role.COUNSELLOR).exists()):
            target = save_counsellor(self.actor, {field: self.cleaned_data[field] for field in FIELDS},
                teams=self.cleaned_data["teams"], password=self.cleaned_data.get("password1") if not self.instance.pk else None,
                pk=self.instance.pk)
            if "profile_photo" in self.changed_data:
                target.profile_photo = self.cleaned_data.get("profile_photo") or ""
                target.save(update_fields=["profile_photo"])
            self.instance = target
            return target
        target = super().save(commit=commit)
        if commit:
            # Team memberships describe counsellors; management roles use Team.leader.
            target.crm_teams.clear()
        return target

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_profile_photo(self):
        photo = self.cleaned_data.get("profile_photo")
        if photo and photo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Profile photos must be 5 MB or smaller.")
        return photo


class EmployeeCreateForm(EmployeeFormMixin, UserCreationForm):
    class Meta:
        model = User
        fields = EMPLOYEE_FIELDS


class EmployeeEditForm(EmployeeFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = EMPLOYEE_FIELDS


class AdminUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("email", "name", "role")


class AdminUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"
