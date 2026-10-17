from django import forms


class CounsellorPasswordForm(forms.Form):
    password1 = forms.CharField(label="New password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "class": "form-control"}))
    password2 = forms.CharField(label="Confirm new password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "class": "form-control"}))

    def clean(self):
        data = super().clean()
        if data.get("password1") != data.get("password2"):
            self.add_error("password2", "Passwords do not match.")
        return data
