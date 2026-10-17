from django import forms
from .models import Application, Admission
from .permissions import visible_applications


class AdmissionForm(forms.Form):
    application = forms.ModelChoiceField(queryset=Application.objects.none())
    enrollment_number = forms.CharField(max_length=120, required=False)
    admission_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    status = forms.ChoiceField(choices=Admission.Status.choices)
    payment_status = forms.ChoiceField(choices=Admission.PaymentStatus.choices)
    remarks = forms.CharField(required=False, max_length=10000, widget=forms.Textarea(attrs={"rows": 4}))

    def __init__(self, *args, actor, application=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["application"].queryset = visible_applications(actor).filter(lead__is_active=True, status__in=["SUBMITTED", "UNDER_REVIEW", "APPROVED"])
        if application:
            self.fields["application"].queryset = visible_applications(actor).filter(lead__is_active=True, pk=application.pk)
            self.fields["application"].initial = application
            self.fields["application"].disabled = True
