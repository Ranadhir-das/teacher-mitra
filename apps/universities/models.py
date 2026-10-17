from django.db import models
from django.db.models.functions import Lower


class Country(models.Model):
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=2, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="country_name_ci_unique"),
            models.UniqueConstraint(Lower("code"), condition=~models.Q(code=""), name="country_code_ci_unique"),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        self.name = self.name.strip()
        self.code = self.code.strip().upper()
        if not self.name:
            raise ValidationError({"name": "Country name is required."})
        if self.code and (len(self.code) != 2 or not self.code.isascii() or not self.code.isalpha()):
            raise ValidationError({"code": "Use a two-letter country code, or leave blank."})

    def __str__(self):
        return self.name


class University(models.Model):
    name = models.CharField(max_length=200)
    country = models.ForeignKey(Country, on_delete=models.PROTECT, related_name="universities")
    website = models.URLField(blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [models.UniqueConstraint(Lower("name"), "country", name="university_country_name_ci_unique")]

    def __str__(self):
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError
        self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": "University name is required."})
        if not self.country_id:
            raise ValidationError({"country": "Select a country."})
        old = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        if not old or old.country_id != self.country_id:
            if not self.country.is_active:
                raise ValidationError({"country": "Choose an active country."})
            if old and old.country_id is not None and (self.selected_leads.exists() or self.applications.exists() or self.admissions.exists()):
                raise ValidationError({"country": "A university used by leads or applications cannot move countries."})
