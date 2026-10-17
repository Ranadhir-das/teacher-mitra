from django import forms
from django.utils import timezone

from .models import FollowUp


class FollowUpForm(forms.ModelForm):

    scheduled_at = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={
                "type": "datetime-local",
                "class": "form-control",
            }
        ),
        input_formats=[
            "%Y-%m-%dT%H:%M",
        ],
    )

    class Meta:
        model = FollowUp
        fields = [
            "followup_type",
            "scheduled_at",
            "assigned_to",
            "notes",
        ]

        widgets = {
            "followup_type": forms.Select(
                attrs={"class": "form-select"}
            ),
            "assigned_to": forms.Select(
                attrs={"class": "form-select"}
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Add follow-up notes..."
                }
            ),
        }

    def clean_scheduled_at(self):
        value = self.cleaned_data["scheduled_at"]

        if value < timezone.now():
            raise forms.ValidationError(
                "Follow-up time cannot be in the past."
            )

        return value


class FollowUpCompleteForm(forms.ModelForm):

    class Meta:
        model = FollowUp
        fields = [
            "outcome",
            "notes",
        ]

        widgets = {
            "outcome": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: Student requested a callback tomorrow",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Add completion notes..."
                }
            ),
        }
        