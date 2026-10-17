from django import forms
from apps.applications.models import Application
from apps.applications.permissions import visible_applications
from .models import Document
from .validators import validate_upload


class DocumentForm(forms.Form):
    application = forms.ModelChoiceField(queryset=Application.objects.none())
    document_type = forms.ChoiceField(choices=Document.Type.choices)
    title = forms.CharField(max_length=200)
    upload = forms.FileField(required=False, help_text="PDF, PNG or JPEG, up to 10 MB. Leave empty to request a document.")

    def __init__(self, *args, actor, application=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["application"].queryset = visible_applications(actor).filter(lead__is_active=True)
        if application:
            self.fields["application"].initial = application
            self.fields["application"].disabled = True

    def clean_upload(self):
        upload = self.cleaned_data.get("upload")
        if upload:
            validate_upload(upload)
        return upload


class DocumentActionForm(forms.Form):
    action = forms.ChoiceField(choices=[("upload", "Upload / resubmit"), ("verify", "Verify"), ("reject", "Reject"), ("delete", "Delete document and file")])
    upload = forms.FileField(required=False)
    reason = forms.CharField(required=False, max_length=5000, widget=forms.Textarea(attrs={"rows": 3}))
    notes = forms.CharField(required=False, max_length=5000, widget=forms.Textarea(attrs={"rows": 3}))
