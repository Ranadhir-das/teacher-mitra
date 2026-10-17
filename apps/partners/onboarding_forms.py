from django import forms
from .models import Partner
from .onboarding import FIELDS, DOCUMENT_TYPES
from apps.documents.models import Document


class OnboardingForm(forms.ModelForm):
    class Meta:
        model = Partner
        fields = FIELDS
        widgets = {"address": forms.Textarea(attrs={"rows": 3}), "tax_explanation": forms.Textarea(attrs={"rows": 3})}


class UploadForm(forms.Form):
    document_type = forms.ChoiceField(choices=[(code, label) for code, label in Document.Type.choices if code in DOCUMENT_TYPES])
    file = forms.FileField(help_text="PDF, PNG or JPEG; maximum 10 MB.")


class ReviewForm(forms.Form):
    decision = forms.ChoiceField(choices=[("approve", "Approve"), ("changes", "Request changes"), ("reject", "Reject")])
    feedback = forms.CharField(required=False, max_length=5000, widget=forms.Textarea(attrs={"rows": 3}))
