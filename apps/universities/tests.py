from django.test import TestCase
from django.core.exceptions import ValidationError
from .models import Country


class CountryModelTests(TestCase):
    def test_normalization_and_unique_names_codes(self):
        country = Country(name=" Canada ", code="ca")
        country.full_clean()
        country.save()
        self.assertEqual(str(country), "Canada")
        self.assertEqual(country.code, "CA")
        for data in ({"name": "canada", "code": "XX"}, {"name": "Duplicate code", "code": "ca"}, {"name": "Bad code", "code": "123"}):
            with self.assertRaises(ValidationError):
                Country(**data).full_clean()

    def test_optional_codes_and_deactivation(self):
        for name in ("One", "Two"):
            country = Country(name=name)
            country.full_clean()
            country.save()
        country.is_active = False
        country.save()
        self.assertEqual(Country.objects.filter(is_active=True).count(), 1)


class UniversityCountryTests(TestCase):
    def test_required_country_and_scoped_uniqueness(self):
        from .models import University
        first = Country.objects.create(name="Canada")
        second = Country.objects.create(name="UK")
        University.objects.create(name="Shared University", country=first)
        university = University(name="Shared University", country=second)
        university.full_clean()
        university.save()
        with self.assertRaises(ValidationError):
            University(name="shared university", country=first).full_clean()
        with self.assertRaises(ValidationError):
            University(name="Missing country").full_clean()
        second.is_active = False
        second.save()
        with self.assertRaises(ValidationError):
            University(name="New university", country=second).full_clean()
