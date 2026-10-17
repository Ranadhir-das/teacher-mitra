from django import forms
from django.contrib.auth.password_validation import validate_password
from apps.leads.models import Lead
from .models import Partner
from .services import PARTNER_FIELDS, PROFILE_FIELDS, SUBMISSION_FIELDS, SIGNUP_FIELDS
from .statuses import PUBLIC_STATUSES


class PartnerForm(forms.ModelForm):
    create_login = forms.BooleanField(required=False, label="Create login account")
    login_email = forms.EmailField(required=False, help_text="Defaults to partner contact email when creating a login.")
    password = forms.CharField(required=False, strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}), label="Initial password")
    password_confirm = forms.CharField(required=False, strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}), label="Confirm initial password")

    class Meta:
        model = Partner
        fields = PARTNER_FIELDS
        widgets = {"address": forms.Textarea(attrs={"rows": 3}), "notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["status"].choices = [("REGISTERED", "Registered") ]
            self.initial["status"] = "REGISTERED"
        if self.instance.pk:
            for field in ("create_login", "login_email", "password", "password_confirm"):
                self.fields.pop(field)

    def clean(self):
        data = super().clean()
        if data.get("create_login"):
            if not data.get("password"):
                self.add_error("password", "Enter an initial password.")
            elif data.get("password") != data.get("password_confirm"):
                self.add_error("password_confirm", "Passwords do not match.")
        return data

    @property
    def sections(self):
        groups = [
            ("Partner information", ("business_name", "partner_type", "contact_person", "email", "phone", "alternate_phone")),
            ("Address", ("address", "city", "state", "pincode")),
            ("Login account", ("create_login", "login_email", "password", "password_confirm")),
            ("Status & internal notes", ("status", "notes")),
        ]
        return [(name, [self[f] for f in fields if f in self.fields]) for name, fields in groups if any(f in self.fields for f in fields)]


class LoginAccountForm(forms.Form):
    login_email = forms.EmailField()
    password = forms.CharField(strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}), label="Initial password")
    password_confirm = forms.CharField(strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}), label="Confirm initial password")

    def clean(self):
        data = super().clean()
        if data.get("password") != data.get("password_confirm"):
            self.add_error("password_confirm", "Passwords do not match.")
        return data


class PartnerStatusForm(forms.Form):
    status = forms.ChoiceField(choices=Partner.Status.choices)


class AccountAccessForm(forms.Form):
    is_active = forms.TypedChoiceField(choices=[("true", "Enable login"), ("false", "Disable login")], coerce=lambda value: value == "true")


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Partner
        fields = PROFILE_FIELDS
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}


from apps.universities.education_forms import EducationFormMixin


class SubmissionForm(EducationFormMixin, forms.ModelForm):
    confirm_duplicate = forms.BooleanField(required=False, label="I reviewed the duplicate warning and confirm this is a separate referral")

    class Meta:
        model = Lead
        fields = SUBMISSION_FIELDS
        labels = {"partner_submitted_notes": "Notes about your referral", "highest_qualification": "Qualification", "desired_course": "Interested course", "preferred_study_mode": "Learning mode"}
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"}), "partner_submitted_notes": forms.Textarea(attrs={"rows": 4})}

    @property
    def sections(self):
        groups = [
            ("Student information", SUBMISSION_FIELDS[:6]),
            ("Education", SUBMISSION_FIELDS[6:10]),
            ("Course requirement", ("selected_country", "selected_university", "selected_course", *SUBMISSION_FIELDS[10:14])),
            ("Additional information", ("partner_submitted_notes", "confirm_duplicate")),
        ]
        return [(name, [self[f] for f in fields]) for name, fields in groups]


class PartnerFilterForm(forms.Form):
    search = forms.CharField(required=False, max_length=200)
    status = forms.ChoiceField(choices=[("", "All statuses"), *Partner.Status.choices], required=False)
    partner_type = forms.ChoiceField(choices=[("", "All types"), *Partner.Type.choices], required=False)
    sort = forms.ChoiceField(choices=[("newest", "Newest"), ("oldest", "Oldest"), ("name", "Business name"), ("leads", "Most leads")], required=False)


class PortalLeadFilterForm(forms.Form):
    search = forms.CharField(required=False, max_length=200)
    status = forms.ChoiceField(choices=[("", "All progress"), *[(key, value[0]) for key, value in PUBLIC_STATUSES.items()]], required=False)
    sort = forms.ChoiceField(choices=[("newest", "Newest"), ("oldest", "Oldest"), ("name", "Student name"), ("updated", "Last updated")], required=False)


class PartnerSignupForm(forms.ModelForm):
    password = forms.CharField(strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}), help_text="Use at least 8 characters; avoid common or entirely numeric passwords.")
    password_confirm = forms.CharField(strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}), label="Confirm password")

    class Meta:
        model = Partner
        fields = SIGNUP_FIELDS

    def clean_email(self):
        from apps.accounts.models import User
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        from apps.accounts.models import User
        data = super().clean()
        if data.get("password") != data.get("password_confirm"):
            self.add_error("password_confirm", "Passwords do not match.")
        if data.get("password"):
            user = User(email=data.get("email", ""), name=data.get("contact_person", ""))
            try:
                validate_password(data["password"], user)
            except forms.ValidationError as exc:
                self.add_error("password", exc)
        return data
